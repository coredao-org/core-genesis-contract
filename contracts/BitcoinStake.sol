// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ICandidateHub.sol";
import "./lib/Address.sol";
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

  uint256 public constant BTC_DECIMAL = 1e8;

  // Reward of per btc per validator per round
  // validator => (round => preBtcReward)
  mapping(address => mapping(uint256 => uint256)) public rewardPerBTCMap;

  // Key: candidator
  // value: btc amount;
  // TODO need call setNewRound()
  mapping (address => uint256) candidators;

  // The latest round tag
  uint256 public lastRoundTag;

  // Initial round
  uint256 public initRound;

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed agent, address indexed delegator, bytes script, uint256 outputIndex, uint256 amount);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveAgent(address candidate);

  function init() external onlyNotInit {
    initRound = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    lastRoundTag = initRound - 1;
  }

  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 amount,  uint256 outputIndex) override external onlyBtcAgent returns (address delegator, uint256 fee) {
    require(script[0] == bytes1(uint8(0x04)) && script[5] == bytes1(uint8(0xb1)), "not a valid redeem script");

    uint32 lockTime = parseLockTime(script);
    address agent;
    (delegator, agent, fee) = parseAndCheckPayload(payload);

    IPledgeAgent(PLEDGE_AGENT_ADDR).delegateBtc(txid, lockTime, delegator, agent, amount);

    emit delegatedBtc(txid, agent, delegator, script, outputIndex, amount);
  }

  function undelegate(bytes32 txid, bytes memory stxos, bytes29 voutView) override external onlyBtcAgent {
    // TODO clear the stake tx.
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
      m[roundTag] = historyReward + rewardList[i] * BTC_DECIMAL / candidators[validator];
    }
    
    lastRoundTag = roundTag;
  }

  function getStakeAmounts(address[] calldata candidates) external override returns (uint256[] memory amounts) {
    return IPledgeAgent(PLEDGE_AGENT_ADDR).getBTCAmount(candidates);
  }

  function getLastRoundBTCAmounts(address[] calldata validators) external view override returns (uint256[] memory amounts) {
    uint256 validatorSize = validators.length;
    amounts = new uint256[](validatorSize);
    for (uint256 i = 0; i < validatorSize; ++i) {
      amounts[i] = candidators[validators[i]];
    }
    return amounts;
  }

  function claimReward() external {
    // (rewardPerBTC[roundTag-1] - rewardPerBTC[xxx]) * btcamount / BTC_DECIMAL;

  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param roundTag The new round tag
  function setNewRound(address[] calldata validators, uint256 roundTag) external override{
    uint256[] memory amounts = IPledgeAgent(PLEDGE_AGENT_ADDR).getBTCAmount(validators);
    
    uint256 length = validators.length;
    for (uint256 i = 0; i < length; i++) {
      candidators[validators[i]] = amounts[i];
    }
  }

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
