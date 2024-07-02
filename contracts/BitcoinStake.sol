// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ICandidateHub.sol";
import "./lib/Address.sol";
import "./lib/BytesLib.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./System.sol";


// Bitcoin Stake is planned to move from PledgeAgent to this independent contract.
// This contract will implement the current deposit.
// The reward of current deposit can be claimed after the UTXO unlocked.
// At v1.1.10, this contract only implement delegate transform & claim reward.
// The relayer should also transfer unlock tx to Core chain via BitcoinAgent.verifyBurnTx
contract BitcoinStake is IBitcoinStake, System, IParamSubscriber {
  using TypedMemView for *;
  using BytesLib for *;

  uint256 public constant BTC_DECIMAL = 1e8;

  // Reward of per btc per validator per round
  // validator => (round => preBtcReward)
  mapping(address => mapping(uint256 => uint256)) public rewardPerBTCMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  // The latest round tag
  uint256 public lastRoundTag;

  // Initial round
  uint256 public initRound;

  // Key: delegator address.
  // Value: Delegator infomation
  mapping(address => Delegator) delegatorMap;

  // Key: candidator
  // value: Candidate information;
  mapping(address => Candidate) candidateMap;

  // Key: txid of bitcoin
  // value: delegator address.
  mapping(bytes32 => address) txidMap;

  // Delegator
  struct Delegator {
    DepositReceipt[] receipts;
  }

  // The deposit receipt between delegate and candidate.
  struct DepositReceipt {
    bytes32 btctxid;
    uint256  outputIndex;
    address candidate;
    uint256 amount;
    uint256 round;
    uint256 locktime;
  }

  // The Candidate amount.
  struct Candidate {
    // This value is set in setNewRound
    uint256 amount;
    // It is changed when delegate/undelegate/tranfer
    uint256 realAmount;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes script, uint256 outputIndex, uint256 amount);
  event undelegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes32 outpointHash, uint256 outpointIndex, uint256 amount);

  function init() external onlyNotInit {
    initRound = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    roundTag = initRound;
    lastRoundTag = initRound - 1;
  }

  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 amount, uint256 outputIndex) override external onlyBtcAgent returns (address delegator, uint256 fee) {
    require(script[0] == bytes1(uint8(0x04)) && script[5] == bytes1(uint8(0xb1)), "not a valid redeem script");

    uint32 lockTime = parseLockTime(script);
    require(lockTime > block.timestamp, "lockTime should be a tick in future.");
    address candidate;
    (delegator, candidate, fee) = parseAndCheckPayload(payload);

    delegatorMap[delegator].receipts.push(DepositReceipt(txid, outputIndex, candidate, amount, roundTag, lockTime));
    candidateMap[candidate].realAmount += amount;
    txidMap[txid] = delegator;

    emit delegatedBtc(txid, candidate, delegator, script, outputIndex, amount);
  }

  function undelegate(bytes32 txid, bytes memory stxoBytes, bytes29 voutView) override external onlyBtcAgent {
    uint256 length = stxoBytes.length;
    require(length % 36 == 0, "outpoint size mismatch");
    bytes32 outpointHash;
    uint32 outputIndex;
    address delegator;
    uint256 size;
    for (uint256 i = 0; i < length; i += 36) {
      outpointHash = stxoBytes.toBytes32(i);
      outputIndex = stxoBytes.toUint32(i+32);
      delegator = txidMap[outpointHash];
      if (delegator == address(0)) {
        continue;
      }
      size = delegatorMap[delegator].receipts.length;
      for (uint256 j = 0; j < size; ++j) {
        DepositReceipt storage dr = delegatorMap[delegator].receipts[j];
        if (dr.btctxid == outpointHash && dr.outputIndex == outputIndex) {
          candidateMap[dr.candidate].realAmount -= dr.amount;
          emit undelegatedBtc(txid, dr.candidate, delegator, outpointHash, outputIndex, dr.amount);
          if (j + 1 != size) {
            dr = delegatorMap[delegator].receipts[size - 1];
          }
          delegatorMap[delegator].receipts.pop();
          break;
        }
      }
    }
  }

  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 roundTag) external override payable onlyBtcAgent {
    uint256 length = validators.length;

    for (uint256 i = 0; i < length; i++) {
      if (rewardList[i] == 0) {
        continue;
      }
      // Iterate to find the validator history reward amount
      uint256 historyReward = 0;
      address validator = validators[i];
      mapping(uint256 => uint256) storage m = rewardPerBTCMap[validator];
      for (uint256 j = roundTag - 1; j > initRound; j--) {
        if(m[j] != 0) {
          historyReward = m[j];
          break;
        }
      }

      // Calculate reward of per btc per validator per round
      m[roundTag] = historyReward + rewardList[i] * BTC_DECIMAL / candidateMap[validator].amount;
    }
    
    lastRoundTag = roundTag;
  }

  function getStakeAmounts(address[] calldata candidates) external override returns (uint256[] memory amounts) {
    // TODO consider the round of hardfork.
    uint256 length = candidates.length;
    amounts = new uint256[](length);
    for (uint256 i = 0; i < length; i++) {
      amounts[i] = candidateMap[candidates[i]].realAmount;
    }
  }

  function getLastRoundBTCAmounts(address[] calldata validators) external view override returns (uint256[] memory amounts) {
    uint256 validatorSize = validators.length;
    amounts = new uint256[](validatorSize);
    for (uint256 i = 0; i < validatorSize; ++i) {
      amounts[i] = candidateMap[validators[i]].amount;
    }
  }

  function claimReward(uint256 roundTag) external {
    // (rewardPerBTC[roundTag-1] - rewardPerBTC[xxx]) * btcamount / BTC_DECIMAL;
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override{
    uint256 length = validators.length;
    address validator;
    for (uint256 i = 0; i < length; i++) {
      validator = validators[i];
      candidateMap[validator].amount = candidateMap[validator].realAmount;
    }
    roundTag = round;
  }

  // TODO add a function for move btc delegate infor from pledge agent.

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }

    emit paramChange(key, value);
  }

  function parseLockTime(bytes memory script) internal pure returns (uint32) {
    uint256 t;
    assembly {
        let loc := add(script, 0x21)
        t := mload(loc)
    }
    return uint32(t.reverseUint256() & 0xFFFFFFFF);
  }

  function parseAndCheckPayload(bytes29 payload) internal pure returns (address delegator, address agent, uint256 fee) {
    require(payload.len() >= 48, "payload length is too small");
    delegator= payload.indexAddress(7);
    agent = payload.indexAddress(27);
    fee = payload.indexUint(47, 1);
  }
}
