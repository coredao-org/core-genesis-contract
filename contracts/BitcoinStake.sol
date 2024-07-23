// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IBitcoinStake.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ILightClient.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IStakeHub.sol";
import "./lib/BytesLib.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";


// This contract will implement the btc stake.
// It will move old data from PledgeAgent.
// Relayers will commited lock/unlock btc tx to Core chain
contract BitcoinStake is IBitcoinStake, System, IParamSubscriber, ReentrancyGuard {
  using BitcoinHelper for *;
  using TypedMemView for *;
  using BytesLib for *;

  // This field records each btc staking tx, and it will never be clean.
  // key: bitcoin tx id
  // value: bitcoin stake record.
  mapping(bytes32 => BtcTx) public btcTxMap;

  // Reward of per btc per validator per round
  // validator => (round => preBtcReward)
  mapping(address => mapping(uint256 => uint256)) public accuredRewardPerBTCMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

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

  // This field is used to store reward of delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // This field keeps the amount of expired BTC staking value for each round
  // Key: round
  // Value: expire info of exch round.
  mapping(uint256 => FixedExpireInfo) round2expireInfoMap;

  struct BtcTx {
    uint64 amount;
    uint32 outputIndex;
    uint32 lockTime;
    uint32 usedHeight;
  }

  // Delegator
  struct Delegator {
    bytes32[] txids;
  }

  // The deposit receipt between delegate and candidate.
  struct DepositReceipt {
    address candidate;
    address delegator;
    uint256 round; // delegator can claim reward after this round
  }

  // The Candidate information.
  struct Candidate {
    // This value is set in setNewRound
    uint256 fixAmount;
    uint256 flexAmount;
    // It is changed when delegate/undelegate/tranfer
    uint256 realFixAmount;
    uint256 realFlexAmount;
    uint256[] continuousRewardEndRounds;
  }

  struct FixedExpireInfo {
    address[] candidateList;
    mapping(address => uint256) amountMap;
    mapping(address => uint256) existMap;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes script, uint256 amount);
  event btcFix2Flex(bytes32 indexed txid, address indexed candidate, address indexed delegator, uint256 amount);
  event undelegatedBtc(bytes32 indexed outpointHash, uint32 indexed outpointIndex, bytes32 usedTxid);
  event migrated(bytes32 indexed txid);
  event transferredBtc(
    bytes32 indexed txid,
    address sourceCandidate,
    address targetCandidate,
    address delegator,
    uint256 amount
  );
  event btcExpired(bytes32 indexed txid, address indexed delegator);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveCandidate(address candidate);

  modifier onlyPledgeAgent() {
    require(msg.sender == PLEDGE_AGENT_ADDR, "the sender must be pledge agent contract");
    _;
  }

  function init() external onlyNotInit {
    roundTag = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    btcConfirmBlock = SatoshiPlusHelper.INIT_BTC_CONFIRM_BLOCK;
  }

  function initHardforkRound(address[] memory candidates, uint256[] memory amounts, uint256[] memory realAmounts) external onlyPledgeAgent {
    uint256 s = candidates.length;
    for (uint256 i = 0; i < s; ++i) {
      Candidate storage c = candidateMap[candidates[i]];
      c.fixAmount = amounts[i];
      c.realFixAmount = realAmounts[i];
    }
  }

  /// Bitcoin delegate, it is called by relayer
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
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  /// @param script it is a redeem script of the locked up output
  function delegate(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index, bytes memory script) external override nonReentrant {
    require(script[0] == bytes1(uint8(0x04)) && script[5] == bytes1(uint8(0xb1)), "not a valid redeem script");
    bytes32 txid = btcTx.calculateTxId();
    BtcTx storage bt = btcTxMap[txid];
    uint32 lockTime = parseLockTime(script);
    {
      require(bt.amount == 0, "btc tx is already delegated.");
      require(
          ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index),
          "btc tx isn't confirmed");
      uint256 endRound = lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
      require(endRound > roundTag + 1, "insufficient locking rounds");
      bt.lockTime = lockTime;
    }

    DepositReceipt storage dr = receiptMap[txid];
    address delegator;
    address candidate;
    uint64 btcAmount;
    {
      (,,bytes29 voutView,) = btcTx.extractTx();
      uint32 outputIndex;
      uint256 fee;
      (btcAmount, outputIndex, delegator, candidate, fee) = parseVout(voutView, script);
      require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");
      bt.amount = btcAmount;
      bt.outputIndex = outputIndex;

      if (fee != 0) {
        fee *= SatoshiPlusHelper.CORE_DECIMAL;
        IStakeHub(STAKE_HUB_ADDR).addNotePayable(delegator, msg.sender, fee);
      }
    }

    delegatorMap[delegator].txids.push(txid);
    candidateMap[candidate].realFixAmount += btcAmount;

    dr.delegator = delegator;
    dr.candidate = candidate;
    dr.round = roundTag;

    addExpire(dr, lockTime, btcAmount);
    emit delegatedBtc(txid, candidate, delegator, script, btcAmount);    
  }

  /// Bitcoin undelegate, it is called by relayer
  ///
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  function undelegate(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external override nonReentrant {
    bytes32 txid = btcTx.calculateTxId();
    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index), "btc tx isn't confirmed");
    (,bytes29 _vinView, ,) = btcTx.extractTx();

    // parse vinView and update btcTxMap
    _vinView.assertType(uint40(BitcoinHelper.BTCTypes.Vin));
    // Finds total number of outputs
    uint _numberOfInputs = uint256(_vinView.indexCompactInt(0));
    uint256 count;
    uint32 _outpointIndex;
    bytes32 _outpointHash;
    for (uint i = 0; i < _numberOfInputs; ++i) {
      (_outpointHash, _outpointIndex) = _vinView.extractOutpoint(i);
      BtcTx storage bt = btcTxMap[_outpointHash];
      if (bt.amount != 0 && bt.outputIndex == _outpointIndex) {
        bt.usedHeight = blockHeight;
        ++count;
        emit undelegatedBtc(_outpointHash, _outpointIndex, txid);
        // TODO
        // In a future version with fixed | flexible term.
        // It should clear receiptMap, delegatorMap, and update other fields
      }
    }
    require(count != 0, "no btc tx undelegated.");
  }

  /// Receive round rewards from BitcoinAgent. It is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList) external override onlyBtcAgent {
    uint256 length = validators.length;

    uint256 historyReward;
    uint256 lastRewardRound;
    uint256 l;
    address validator;
    for (uint256 i = 0; i < length; i++) {
      if (rewardList[i] == 0) {
        continue;
      }
      historyReward = 0;
      validator = validators[i];
      mapping(uint256 => uint256) storage m = accuredRewardPerBTCMap[validator];
      Candidate storage c = candidateMap[validator];
      l = c.continuousRewardEndRounds.length;
      if (l != 0) {
        lastRewardRound = c.continuousRewardEndRounds[l - 1];
        historyReward = m[lastRewardRound];
      }
      // Calculate reward of per btc per validator per round
      m[roundTag] = historyReward + rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / c.fixAmount;
      if (lastRewardRound + 1 == roundTag) {
        c.continuousRewardEndRounds[l - 1] = roundTag;
      } else {
        c.continuousRewardEndRounds.push(roundTag);
      }
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

  function getRoundRewardPerBTC(address candidate, uint256 round) internal view returns (uint256 reward) {
    reward = accuredRewardPerBTCMap[candidate][round];
    if (reward != 0) {
      return reward;
    }
    // if there's no field with the round,
    // use binary search to get the previous nearest round.
    Candidate storage c = candidateMap[candidate];
    uint256 b = c.continuousRewardEndRounds.length;
    if (b == 0) {
      return 0;
    }
    b -= 1;
    uint256 a;
    uint256 m;
    uint256 tr;
    while (a <= b) {
      m = (a + b) / 2;
      tr = c.continuousRewardEndRounds[m];
      // tr should never be equal to round because the above reward value is zero.
      if (tr < round) {
        reward = accuredRewardPerBTCMap[candidate][tr];
        a = m + 1;
      } else if (m == 0) {
        return 0;
      } else {
        b = m - 1;
      }
    }
    return reward;
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  function claimReward(address delegator) external override onlyBtcAgent returns (uint256 reward) {
    reward = rewardMap[delegator];
    if (reward != 0) {
      rewardMap[delegator] = 0;
    }
    bytes32[] storage txids = delegatorMap[delegator].txids;
    for (uint256 i = txids.length; i != 0; i--) {
      bytes32 txid = txids[i - 1];
      BtcTx storage bt = btcTxMap[txid];
      DepositReceipt storage dr = receiptMap[txid];
      uint256 unlockRound = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
      if (dr.round < roundTag - 1 && dr.round < unlockRound) {
        uint256 minRound = roundTag - 1 < unlockRound ? roundTag - 1 : unlockRound;
        // Calculate reward
        uint256 txReward = (getRoundRewardPerBTC(dr.candidate, minRound) - getRoundRewardPerBTC(dr.candidate, dr.round)) * bt.amount / SatoshiPlusHelper.BTC_DECIMAL;
        reward += txReward;
        dr.round = minRound;
      }

      // Remove txid and deposit receipt
      if (unlockRound <= roundTag) {
        if (i != txids.length) {
          txids[i - 1] = txids[txids.length - 1];
        }
        txids.pop();
        emit btcExpired(txid, delegator);
        delete receiptMap[txid];
      }
    }
    return reward;
  }

  function transferBtc(bytes32 txid, address targetCandidate) external {
    BtcTx storage bt = btcTxMap[txid];
    DepositReceipt storage dr = receiptMap[txid];
    uint64 amount = bt.amount;
    require(amount != 0, "btc tx not found");
    require(dr.delegator == msg.sender, "not the delegator of this btc receipt");
    address candidate = dr.candidate;
    require(dr.candidate != targetCandidate, "can not transfer to the same validator");
    uint256 endRound = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
    require(endRound > roundTag + 1, "insufficient locking rounds");

    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
      revert InactiveCandidate(targetCandidate);
    }

    Candidate storage c = candidateMap[candidate];
    c.realFixAmount -= amount;
    round2expireInfoMap[endRound].amountMap[candidate] -= amount;

    // Calculate reward
    uint256 reward = (accuredRewardPerBTCMap[dr.candidate][roundTag - 1] - accuredRewardPerBTCMap[dr.candidate][dr.round]) * bt.amount / SatoshiPlusHelper.BTC_DECIMAL;
    if (reward != 0) {
      rewardMap[msg.sender] += reward;
    }

    // Set candidate to targetCandidate
    dr.candidate = targetCandidate;
    dr.round = roundTag;

    addExpire(dr, bt.lockTime, amount);
    Candidate storage tc = candidateMap[targetCandidate];
    tc.realFixAmount += amount;

    emit transferredBtc(txid, candidate, targetCandidate, msg.sender, bt.amount);
  }

  // Upgrade function.
  // move btc delegate information from pledge agent.
  function migrateDelegateInfo(bytes32[] calldata txids) external{
    uint256 txLength = txids.length;
    bytes32 txid;
    for (uint256 i = 0; i < txLength; i++) {
      txid = txids[i];
      (bool success, bytes memory data) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("cleanDelegateInfo(bytes32)", txid));
      require(success, "call PLEDGE_AGENT_ADDR.cleanDelegateInfo failed.");
      (address candidate, address delegator, uint256 amount, uint256 round, uint256 lockTime) = abi.decode(data, (address,address,uint256,uint256,uint256));
      BtcTx storage bt = btcTxMap[txid];
      if (bt.amount != 0) {
        continue;
      }

      // Set receiptMap
      DepositReceipt storage dr = receiptMap[txids[i]];
      dr.candidate = candidate;
      dr.delegator = delegator;
      dr.round = round;
      bt.amount = uint64(amount);
      bt.lockTime = uint32(lockTime);

      // Set delegatorMap
      Delegator storage d = delegatorMap[delegator];
      d.txids.push(txid);

      // Set candidateMap
      Candidate storage c = candidateMap[candidate];
      if (round < roundTag) {
        c.fixAmount += amount;
        (success,) = BTC_AGENT_ADDR.call(abi.encodeWithSignature("updateStakeAmount(address,uint256)", candidate, c.fixAmount));
        require (success, "call BTC_AGENT_ADDR.updateStakeAmount failed.");
      }
      c.realFixAmount += amount;

      addExpire(dr, uint32(lockTime), uint64(amount));

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
    address candidate;
    for (uint256 r = roundTag + 1; r <= round; ++r) {
      FixedExpireInfo storage expireInfo = round2expireInfoMap[r];
      for (uint256 j = expireInfo.candidateList.length; j != 0; --j) {
        candidate = expireInfo.candidateList[j - 1];
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

  function addExpire(DepositReceipt storage receipt, uint32 lockTime, uint64 amount) internal {
    uint256 endRound = uint256(lockTime) / SatoshiPlusHelper.ROUND_INTERVAL;
    FixedExpireInfo storage expireInfo = round2expireInfoMap[endRound];
    if (expireInfo.existMap[receipt.candidate] == 0) {
      expireInfo.candidateList.push(receipt.candidate);
      expireInfo.existMap[receipt.candidate] = 1;
    }
    expireInfo.amountMap[receipt.candidate] += amount;
  }



  /// Parses the target output and the op_return of a transaction
  /// @dev  Finds the BTC amount that payload size is less than 80 bytes
  /// @param _voutView      The vout of a Bitcoin transaction
  /// @return btcAmount   Amount of BTC to stake
  /// @return outputIndex The output index of target output.
  /// @return delegator   The one who delegate the Bitcoin
  /// @return candidate   A candidate node address.
  /// @return fee         The value pay for relayer.
  function parseVout(
      bytes29 _voutView,
      bytes memory _script
  ) internal pure returns (uint64 btcAmount, uint32 outputIndex, address delegator, address candidate, uint256 fee) {
    _voutView.assertType(uint40(BitcoinHelper.BTCTypes.Vout));
    bytes29 _outputView;
    bytes29 _scriptPubkeyView;
    bytes29 _scriptPubkeyWithLength;
    bytes29 _arbitraryData;

    // Finds total number of outputs
    uint _numberOfOutputs = uint256(_voutView.indexCompactInt(0));

    for (uint index = 0; index < _numberOfOutputs; index++) {
      _outputView = _voutView.indexVout(index);
      _scriptPubkeyView = _outputView.scriptPubkey();
      _scriptPubkeyWithLength = _outputView.scriptPubkeyWithLength();
      _arbitraryData = _scriptPubkeyWithLength.opReturnPayload();

      // Checks whether the output is an arbitarary data or not
      if(_arbitraryData == TypedMemView.NULL) {
          // Output is not an arbitrary data
          if (
              (_scriptPubkeyView.len() == 23 && 
              _scriptPubkeyView.indexUint(0, 1) == 0xa9 &&
              _scriptPubkeyView.indexUint(1, 1) == 0x14 &&
              _scriptPubkeyView.indexUint(22, 1) == 0x87 &&
              bytes20(_scriptPubkeyView.indexAddress(2)) == ripemd160(abi.encode(sha256(_script)))) ||
              (_scriptPubkeyView.len() == 34 && 
              _scriptPubkeyView.indexUint(0, 1) == 0 &&
              _scriptPubkeyView.indexUint(1, 1) == 32 &&
              _scriptPubkeyView.index(2, 32) == sha256(_script))
          ) {
              btcAmount = _outputView.value();
              outputIndex = uint32(index);
          }
      } else {
          // Returns the whole bytes array
          (delegator, candidate, fee) = parsePayloadAndCheckProtocol(_arbitraryData);
      }
    }
    require(btcAmount != 0, "staked value is zero");
  }

  function parsePayloadAndCheckProtocol(bytes29 payload) internal pure returns (address delegator, address candidate, uint256 fee) {
    require(payload.len() >= 48, "payload length is too small");
    require(payload.indexUint(0, 4) == SatoshiPlusHelper.BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == SatoshiPlusHelper.CHAINID, "wrong chain id");
    uint32 version = uint32(payload.indexUint(4, 1));
    require(version == SatoshiPlusHelper.BTC_STAKE_VERSION, "unsupport sat+ version in btc staking");
    candidate = payload.indexAddress(27);
    fee = payload.indexUint(47, 1);
    delegator = payload.indexAddress(7);
  }
}
