// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/ICandidateHub.sol";
import "./lib/Address.sol";
import "./lib/BytesLib.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";


// Bitcoin Stake is planned to move from PledgeAgent to this independent contract.
// This contract will implement the current deposit.
// The reward of current deposit can be claimed after the UTXO unlocked.
// At v1.1.10, this contract only implement delegate transform & claim reward.
// The relayer should also transfer unlock tx to Core chain via BitcoinAgent.verifyBurnTx
contract BitcoinStake is IBitcoinStake, System, IParamSubscriber {
  using TypedMemView for *;
  using BytesLib for *;

  // Reward of per btc per validator per round
  // validator => (round => preBtcReward)
  mapping(address => mapping(uint256 => uint256)) public accuredRewardPerBTCMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  // Initial round
  uint256 public initRound;

  // receiptMap keeps all deposite receipts of BTC on CORE
  // Key: txid of bitcoin
  // value: DepositReceipt.
  mapping(bytes32 => DepositReceipt) public receiptMap;

  // Key: delegator address.
  // Value: Delegator infomation
  mapping(address => Delegator) delegatorMap;

  // Key: candidator
  // value: Candidate information;
  mapping(address => Candidate) candidateMap;

  // This field keeps the amount of expired BTC staking value for each round
  // Key: round
  // Value: expire info of exch round.
  mapping(uint256 => FixedExpireInfo) round2expireInfoMap;

  // Delegator
  struct Delegator {
    bytes32[] txids;
  }

  // The deposit receipt between delegate and candidate.
  struct DepositReceipt {
    uint256 outputIndex;
    address candidate;
    address delegator;
    uint256 amount;
    uint256 round;
    uint256 lockTime;
  }

  // The Candidate amount.
  struct Candidate {
    // This value is set in setNewRound
    uint256 fixAmount;
    uint256 flexAmount;
    // It is changed when delegate/undelegate/tranfer
    uint256 realFixAmount;
    uint256 realFlexAmount;
  }

  struct FixedExpireInfo {
    address[] candidateList;
    mapping(address => uint256) amountMap;
    mapping(address => uint256) existMap;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes script, uint256 outputIndex, uint256 amount);
  event undelegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes32 outpointHash, uint256 outpointIndex, uint256 amount);
  event migrated(bytes32 indexed txid);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveCandidate(address candidate);

  function init() external onlyNotInit {
    initRound = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    roundTag = initRound;
  }

  /// Bitcoin delegate, it is called by relayer via BitcoinAgent.verifyMintTx
  ///
  /// User workflow to delegate BTC to Core blockchain
  ///  1. A user creates a bitcoin transaction, locks up certain amount ot Bitcoin in one of the transaction output for certain period.
  ///     The transaction should also have an op_return output which contains the staking information, such as the validator and reward addresses. 
  ///  2. Transmit the transaction to Core blockchain by calling the below method `verifyMintTx`.
  ///  3. The user can claim rewards using the reward address set in step 1 during the staking period.
  ///  4. The user can spend the timelocked UTXO using the redeem script when the lock expires.
  ///     the redeem script should start with a time lock. such as:
  ///         <abstract locktime> OP_CLTV OP_DROP <pubKey> OP_CHECKSIG
  ///         <abstract locktime> OP_CLTV OP_DROP OP_DUP OP_HASH160 <pubKey Hash> OP_EQUALVERIFY OP_CHECKSIG
  ///         <abstract locktime> OP_CLTV OP_DROP M <pubKey1> <pubKey1> ... <pubKeyN> N OP_CHECKMULTISIG
  ///
  /// @param txid the bitcoin tx hash
  /// @param payload bytes from OP_RETURN, it is used to parse/verify detail context
  ///                under satoshi+ protocol
  /// @param script it is used to verify the target txout
  /// @param amount amount of the target txout
  /// @param outputIndex The index of the target txout.
  /// @return delegator a Coredao address who delegate the Bitcoin
  /// @return fee pay for relayer's fee.
  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 amount, uint256 outputIndex) override external onlyBtcAgent returns (address delegator, uint256 fee) {
    DepositReceipt storage receipt = receiptMap[txid];
    require(receipt.amount == 0, "btc tx confirmed");
    require(script[0] == bytes1(uint8(0x04)) && script[5] == bytes1(uint8(0xb1)), "not a valid redeem script");

    uint32 lockTime = parseLockTime(script);
    require(lockTime > block.timestamp, "lockTime should be a tick in future.");
    address candidate;
    (delegator, candidate, fee) = parseAndCheckPayload(payload);

    delegatorMap[delegator].txids.push(txid);
    candidateMap[candidate].realFixAmount += amount;

    receipt.outputIndex = outputIndex;
    receipt.candidate = candidate;
    receipt.delegator = delegator;
    receipt.amount = amount;
    receipt.round = roundTag;
    receipt.lockTime = lockTime;

    addExpire(receipt);

    emit delegatedBtc(txid, candidate, delegator, script, outputIndex, amount);
  }

  /// Bitcoin undelegate, it is called by relayer via BitcoinAgent.verifyBurnTx
  ///
  /// @param txid the bitcoin tx hash
  /// @param outpoints outpoints from tx inputs.
  /// @param voutView tx outs as bytes29.
  function undelegate(bytes32 txid, BitcoinHelper.OutPoint[] memory outpoints, bytes29 voutView) external override onlyBtcAgent {
    // TODO implement in furtue. In version with fixed | flexible term.
  }

  /// Receive round rewards from BitcoinAgent. It is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList) external override payable onlyBtcAgent {
    uint256 length = validators.length;

    for (uint256 i = 0; i < length; i++) {
      if (rewardList[i] == 0) {
        continue;
      }
      // Iterate to find the validator history reward amount
      uint256 historyReward = 0;
      address validator = validators[i];
      mapping(uint256 => uint256) storage m = accuredRewardPerBTCMap[validator];
      for (uint256 j = roundTag - 1; j > initRound; j--) {
        if(m[j] != 0) {
          historyReward = m[j];
          break;
        }
      }

      // Calculate reward of per btc per validator per round
      m[roundTag] = historyReward + rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / candidateMap[validator].fixAmount;
    }
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of amounts of all special candidates in this round
  function getStakeAmounts(address[] calldata candidates) external override view returns (uint256[] memory amounts) {
    uint256 length = candidates.length;
    amounts = new uint256[](length);
    for (uint256 i = 0; i < length; i++) {
      amounts[i] = candidateMap[candidates[i]].realFixAmount;
    }
  }

  /// Claim reward for delegator
  /// @return rewardAmount Amount claimed
  function claimReward() external override returns (uint256 rewardAmount) {
    // Delegator storage delegator = delegatorMap[msg.sender];
    rewardAmount = 0;
    bytes32[] storage txids = delegatorMap[msg.sender].txids;
    for (uint256 i = txids.length; i !=0; i--) {
      bytes32 txid = txids[i-1];
      DepositReceipt storage depositReceipt = receiptMap[txid];
      uint256 unlockRound = depositReceipt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
      
      if (depositReceipt.round < roundTag && unlockRound > roundTag) {
        // Calculate reward
        uint256 reward = (accuredRewardPerBTCMap[depositReceipt.candidate][roundTag - 1] - accuredRewardPerBTCMap[depositReceipt.candidate][depositReceipt.round]) * depositReceipt.amount / SatoshiPlusHelper.BTC_DECIMAL;
        rewardAmount += reward;
        depositReceipt.round = roundTag;
      }

      // Remove txid and deposit receipt
      if (unlockRound <= roundTag) {
        if (i != txids.length) {
          txids[i - 1] = txids[txids.length - 1];
        }
        txids.pop();
        delete receiptMap[txid];
      }  
    }

    // Send reward to delegator
    if (rewardAmount != 0) {
      Address.sendValue(payable(msg.sender), rewardAmount);
    }
  }

  function transferBtc(bytes32 txid, address targetCandidate) external {
    DepositReceipt storage depositReceipt = receiptMap[txid];
    require(depositReceipt.amount != 0, "btc tx not found");
    require(depositReceipt.delegator == msg.sender, "not the delegator of this btc receipt");
    require(depositReceipt.candidate != targetCandidate, "can not transfer to the same validator");
    require(depositReceipt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL > roundTag + 1, "insufficient locking rounds");

    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
      revert InactiveCandidate(targetCandidate);
    }

    // Calculate reward
    uint256 reward = (accuredRewardPerBTCMap[depositReceipt.candidate][roundTag - 1] - accuredRewardPerBTCMap[depositReceipt.candidate][depositReceipt.round]) * depositReceipt.amount / SatoshiPlusHelper.BTC_DECIMAL;
    if (reward != 0) {
      Address.sendValue(payable(msg.sender), reward);
    }

    // Set candidate to targetCandidate
    depositReceipt.candidate = targetCandidate;
    depositReceipt.round = roundTag;
  }

  // Upgrade function.
  // move btc delegate information from pledge agent.
  function migrateDelegateInfo(bytes32[] calldata txids) external{
    uint256 txLength = txids.length;
    bytes32 txid;
    for (uint256 i = 0; i < txLength; i++) {
      txid = txids[i];
      (bool success, bytes memory data) = PLEDGE_AGENT_ADDR.call{gas: 50000}(abi.encodeWithSignature("cleanDelegateInfo(bytes32)", txid));
      require (success, "PLEDGE_AGENT_ADDR.cleanDelegateInfo failed.");
      (address candidate, address delegator, uint256 amount, uint256 round, uint256 lockTime) = abi.decode(data, (address,address,uint256,uint256,uint256));
      if (receiptMap[txid].amount != 0) {
        continue;
      }

      // Set receiptMap
      DepositReceipt storage depositReceipt = receiptMap[txids[i]];
      depositReceipt.outputIndex = 0;
      depositReceipt.candidate = candidate;
      depositReceipt.delegator = delegator;
      depositReceipt.amount = amount;
      depositReceipt.round = round;
      depositReceipt.lockTime = lockTime;

      // Set delegatorMap
      Delegator storage d = delegatorMap[delegator];
      d.txids.push(txid);

      // Set candidateMap
      Candidate storage c = candidateMap[candidate];
      if (round < roundTag) {
        c.fixAmount += amount;
      }
      c.realFixAmount += amount;

      addExpire(depositReceipt);

      emit migrated(txid);
    }
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override{
    uint256 length = validators.length;
    address validator;
    for (uint256 i = 0; i < length; i++) {
      validator = validators[i];
      candidateMap[validator].fixAmount = candidateMap[validator].realFixAmount;
    }
    roundTag = round;
  }

  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    // the expired BTC staking values will be removed
    uint256 j;
    for (uint256 r = roundTag + 1; r <= round; ++r) {
      FixedExpireInfo storage expireInfo = round2expireInfoMap[r];
      j = expireInfo.candidateList.length;
      while (j != 0) {
        j--;
        address candidate = expireInfo.candidateList[j];
        candidateMap[candidate].realFixAmount -= expireInfo.amountMap[candidate];
        expireInfo.candidateList.pop();
        delete expireInfo.amountMap[candidate];
        delete expireInfo.existMap[candidate];
      }
      delete round2expireInfoMap[r];
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

  function addExpire(DepositReceipt storage receipt) internal {
    uint256 endRound = receipt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
    FixedExpireInfo storage expireInfo = round2expireInfoMap[endRound];
    if (expireInfo.existMap[receipt.candidate] == 0) {
      expireInfo.candidateList.push(receipt.candidate);
      expireInfo.existMap[receipt.candidate] = 1;
    }
    expireInfo.amountMap[receipt.candidate] += receipt.amount;
  }
}
