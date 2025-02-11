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
import "./lib/RLPDecode.sol";
import "./System.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";


/// This contract handles non-custodial BTC staking. 
/// Relayers submit BTC stake/redeem transactions to Core chain here.
contract BitcoinStake is IBitcoinStake, System, IParamSubscriber, ReentrancyGuard {
  using BitcoinHelper for *;
  using TypedMemView for *;
  using BytesLib for *;
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.Iterator;
  using RLPDecode for RLPDecode.RLPItem;

  // This field records each btc staking tx, and it will never be cleared.
  // key: bitcoin tx id
  // value: bitcoin stake record
  mapping(bytes32 => BtcTx) public btcTxMap;

  // accrued reward per btc of a validator on a given round
  // validator => (round => perBTCReward)
  mapping(address => mapping(uint256 => uint256)) public accruedRewardPerBTCMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  // receiptMap keeps all deposite receipts of BTC on Core
  // key: txid of bitcoin
  // value: DepositReceipt
  mapping(bytes32 => DepositReceipt) public receiptMap;

  // key: delegator address
  // Value: Delegator infomation
  mapping(address => Delegator) delegatorMap;

  // key: candidate address
  // value: Candidate information
  mapping(address => Candidate) public candidateMap;

  // This field is used to store reward of delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => Reward) public rewardMap;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // This field keeps the amount of expired BTC staking value for each round
  // key: round
  // value: expire info of exch round
  mapping(uint256 => ExpireInfo) round2expireInfoMap;

  // Time grading applied to BTC stakers
  LockLengthGrade[] public grades;

  // whether the time grading is enabled
  bool public gradeActive;

  struct BtcTx {
    uint64 amount;
    uint32 outputIndex;
    uint64 blockTimestamp;
    uint32 lockTime;
    uint32 usedHeight;
  }

  struct Delegator {
    bytes32[] txids;
  }

  struct DepositReceipt {
    address candidate;
    address delegator;
    uint256 round; // delegator can claim reward after this round
  }

  struct Candidate {
    uint256 stakedAmount;
    uint256 realtimeAmount;
    uint256[] continuousRewardEndRounds;
  }

  struct ExpireInfo {
    address[] candidateList;
    mapping(address => uint256) amountMap;
  }

  struct LockLengthGrade {
    uint64 lockDuration; // In second
    uint32 percentage; // [0 ~ DENOMINATOR]
  }

  struct Reward {
    uint256 reward;
    uint256 unclaimedReward;
    uint256 accStakedAmount;
  }

  /*********************** events **************************/
  event delegated(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes script, uint32 outputIndex, uint64 amount, uint256 fee);
  event undelegated(bytes32 indexed outpointHash, uint32 indexed outpointIndex, bytes32 usedTxid);
  event transferredBtc(
    bytes32 indexed txid,
    address sourceCandidate,
    address targetCandidate,
    address delegator,
    uint256 amount
  );
  event btcExpired(bytes32 indexed txid, address indexed delegator);
  event claimedRewardPerTx(bytes32 indexed txid, uint256 reward, bool expired, uint256 accStakedAmount, uint256 unclaimedReward);
  event storedRewardPerTx(bytes32 indexed txid, uint256 reward, bool expired, uint256 accStakedAmount, uint256 unclaimedReward);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveCandidate(address candidate);

  /*********************** Init ********************************/
  function init() external onlyNotInit {
    roundTag = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    btcConfirmBlock = SatoshiPlusHelper.INIT_BTC_CONFIRM_BLOCK;
    alreadyInit = true;
  }

  /*********************** External functions ********************************/
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
    require(bt.amount == 0, "btc tx is already delegated.");
    uint32 lockTime = _parseLockTime(script);
    uint64 blockTimestamp;
    {
      bool txChecked;
      (txChecked, blockTimestamp) = ILightClient(LIGHT_CLIENT_ADDR).checkTxProofAndGetTime(txid, blockHeight, btcConfirmBlock, nodes, index);
      require(txChecked, "btc tx isn't confirmed");
      uint256 endRound = lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
      require(endRound > roundTag + 1, "insufficient locking rounds");
    }

    DepositReceipt storage dr = receiptMap[txid];
    address delegator;
    address candidate;
    uint64 btcAmount;
    {
      (,,bytes29 voutView,) = btcTx.extractTx();
      uint32 outputIndex;
      (btcAmount, outputIndex, delegator, candidate) = _parseVout(voutView, script);
      require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");
      IStakeHub(STAKE_HUB_ADDR).onStakeChange(delegator);
      bt.lockTime = lockTime;
      bt.blockTimestamp = blockTimestamp;
      bt.amount = btcAmount;
      bt.outputIndex = outputIndex;
      emit delegated(txid, candidate, delegator, script, outputIndex, btcAmount, 0);
    }

    delegatorMap[delegator].txids.push(txid);
    candidateMap[candidate].realtimeAmount += btcAmount;

    dr.delegator = delegator;
    dr.candidate = candidate;
    dr.round = roundTag;

    _addExpire(dr, lockTime, btcAmount);
  }

  /// Bitcoin undelegate, it is called by relayer
  ///
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  function undelegate(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external override nonReentrant {
    bytes32 txid = btcTx.calculateTxId();
    bool txChecked = ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index);
    require(txChecked, "btc tx isn't confirmed");
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
        require(bt.usedHeight == 0, "btc output is already undelegated.");
        bt.usedHeight = blockHeight;
        ++count;
        emit undelegated(_outpointHash, _outpointIndex, txid);      }
    }
    require(count != 0, "no btc tx undelegated.");
  }

  /// Receive round rewards from BitcoinAgent. It is triggered at the beginning of turn round.
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList) external override onlyBtcAgent {
    uint256 length = validators.length;
    uint256 l;
    address validator;
    for (uint256 i = 0; i < length; i++) {
      if (rewardList[i] == 0) {
        continue;
      }
      uint256 historyReward;
      uint256 lastRewardRound;
      validator = validators[i];
      mapping(uint256 => uint256) storage m = accruedRewardPerBTCMap[validator];
      Candidate storage c = candidateMap[validator];
      if (c.stakedAmount == 0) {
        continue;
      }
      l = c.continuousRewardEndRounds.length;
      if (l != 0) {
        lastRewardRound = c.continuousRewardEndRounds[l - 1];
        historyReward = m[lastRewardRound];
      }
      // Add new accrued reward of per btc on the validator for this round
      m[roundTag] = historyReward + rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / c.stakedAmount;
      if (lastRewardRound + 1 == roundTag) {
        c.continuousRewardEndRounds[l - 1] = roundTag;
      } else {
        c.continuousRewardEndRounds.push(roundTag);
      }
    }
  }

  /// Get staked BTC amount
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of amounts of all candidates in this round
  function getStakeAmounts(address[] calldata candidates) external override view returns (uint256[] memory amounts) {
    uint256 length = candidates.length;
    amounts = new uint256[](length);
    for (uint256 i = 0; i < length; i++) {
      amounts[i] = candidateMap[candidates[i]].realtimeAmount;
    }
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @param settleRound the settlement round
  /// @param claim claim or store claim
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  /// @return accStakedAmount accumulated stake amount (multiplied by days), used for grading calculation
  function claimReward(address delegator, uint256 settleRound, bool claim) external override onlyBtcAgent returns (uint256 reward, uint256 rewardUnclaimed, uint256 accStakedAmount) {
    reward = rewardMap[delegator].reward;
    rewardUnclaimed = rewardMap[delegator].unclaimedReward;
    accStakedAmount = rewardMap[delegator].accStakedAmount;
    if (reward != 0 || accStakedAmount != 0) {
      delete rewardMap[delegator];
    }

    bool expired;
    uint256 rewardPerTx;
    uint256 rewardUnclaimedPerTx;
    uint256 accStakedAmountPerTx;
    bytes32[] storage txids = delegatorMap[delegator].txids;
    for (uint256 i = txids.length; i != 0; i--) {
      (rewardPerTx, expired, rewardUnclaimedPerTx, accStakedAmountPerTx) = _collectReward(txids[i - 1], settleRound);
      reward += rewardPerTx;
      rewardUnclaimed += rewardUnclaimedPerTx;
      accStakedAmount += accStakedAmountPerTx;
      if (claim) {
        emit claimedRewardPerTx(txids[i - 1], rewardPerTx, expired, accStakedAmountPerTx, rewardUnclaimedPerTx);
      } else {
        emit storedRewardPerTx(txids[i - 1], rewardPerTx, expired, accStakedAmountPerTx, rewardUnclaimedPerTx);
      }

      if (expired) {
        if (i != txids.length) {
          txids[i - 1] = txids[txids.length - 1];
        }
        txids.pop();
      }
    }
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyBtcAgent {
    uint256 length = validators.length;
    address validator;
    for (uint256 i = 0; i < length; i++) {
      validator = validators[i];
      candidateMap[validator].stakedAmount = candidateMap[validator].realtimeAmount;
    }
    roundTag = round;
  }

  /// Prepare for the new round
  /// @param round The new round tag
  function prepare(uint256 round) external override onlyStakeHub {
    // the expired BTC staking values will be removed
    address candidate;
    for (uint256 r = roundTag + 1; r <= round; ++r) {
      ExpireInfo storage expireInfo = round2expireInfoMap[r];
      uint256 l = expireInfo.candidateList.length;
      if (l == 0) continue;
      for (uint256 j = l; j != 0; --j) {
        candidate = expireInfo.candidateList[j - 1];
        candidateMap[candidate].realtimeAmount -= (expireInfo.amountMap[candidate] - 1);
        expireInfo.candidateList.pop();
        delete expireInfo.amountMap[candidate];
      }
      delete round2expireInfoMap[r];
    }
  }

  /*********************** External methods **************************/

  /// transfer BTC delegate to a new validator
  /// @param txid the staked BTC transaction to transfer
  /// @param targetCandidate the new validator to stake to
  function transfer(bytes32 txid, address targetCandidate) external nonReentrant {
    BtcTx storage bt = btcTxMap[txid];
    DepositReceipt storage dr = receiptMap[txid];
    uint64 amount = bt.amount;
    require(amount != 0, "btc tx not found");
    require(dr.delegator == msg.sender, "not the delegator of this btc receipt");

    address candidate = dr.candidate;
    require(candidate != targetCandidate, "can not transfer to the same validator");
    uint256 endRound = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
    require(endRound > roundTag + 1, "insufficient locking rounds");

    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
      revert InactiveCandidate(targetCandidate);
    }
    IStakeHub(STAKE_HUB_ADDR).onStakeChange(dr.delegator);

    Candidate storage c = candidateMap[candidate];
    c.realtimeAmount -= amount;
    round2expireInfoMap[endRound].amountMap[candidate] -= amount;

    // Set candidate to targetCandidate
    dr.candidate = targetCandidate;
    dr.round = roundTag;
    _addExpire(dr, bt.lockTime, amount);

    Candidate storage tc = candidateMap[targetCandidate];
    tc.realtimeAmount += amount;

    emit transferredBtc(txid, candidate, targetCandidate, msg.sender, bt.amount);
  }

  function getGrades() external view returns (LockLengthGrade[] memory) {
    return grades;
  }

  function getTxIdsByDelegator(address delegator) external view returns(bytes32[] memory) {
    return delegatorMap[delegator].txids;
  }

  function getContinuousRewardEndRoundsByCandidate(address candidate) external view returns(uint256[] memory) {
    return candidateMap[candidate].continuousRewardEndRounds;
  }

  function getExpireValue(uint256 round, address agent) external view returns (uint256){
    ExpireInfo storage expireInfo = round2expireInfoMap[round];
    return expireInfo.amountMap[agent];
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "grades")) {
      uint256 lastLength = grades.length;

      RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
      uint256 currentLength = items.length;
      if (currentLength == 0) {
         revert MismatchParamLength(key);
      }

      for (uint256 i = currentLength; i < lastLength; i++) {
        grades.pop();
      }
      uint256 lockDuration;
      uint256 percentage;
      for (uint256 i = 0; i < currentLength; i++) {
        RLPDecode.RLPItem[] memory itemArray = items[i].toList();
        lockDuration = RLPDecode.toUint(itemArray[0]);
        // limit lockDuration 4000 rounds.
        if (lockDuration > 4000) {
          revert OutOfBounds('lockDuration', percentage, 0, 4000);
        }
        percentage = RLPDecode.toUint(itemArray[1]);
        if (percentage == 0 || percentage > SatoshiPlusHelper.DENOMINATOR) {
          revert OutOfBounds('percentage', percentage, 1, SatoshiPlusHelper.DENOMINATOR);
        }

        lockDuration *= SatoshiPlusHelper.ROUND_INTERVAL;
        if (i >= lastLength) {
          grades.push(LockLengthGrade(uint64(lockDuration), uint32(percentage)));
        } else {
          grades[i] = LockLengthGrade(uint64(lockDuration), uint32(percentage));
        }
      }
      // check lockDuration & percentage in order.
      for (uint256 i = 1; i < currentLength; i++) {
        require(grades[i-1].lockDuration < grades[i].lockDuration, "lockDuration disorder");
        require(grades[i-1].percentage < grades[i].percentage, "percentage disorder");
      }
      require(grades[0].lockDuration == 0, "lowest lockDuration must be zero");
    } else if (Memory.compareStrings(key, "gradeActive")) {
      if (value.length != 1) {
        revert MismatchParamLength(key);
      }
      uint8 newGradeActive = value.toUint8(0);
      if (newGradeActive > 1) {
        revert OutOfBounds(key, newGradeActive, 0, 1);
      }
      gradeActive = newGradeActive == 1;
    } else {
      revert UnsupportedGovParam(key);
    }

    emit paramChange(key, value);
  }

  /// parse locktime from the redeem script
  /// @param script the redeem script of BTC stake transaction
  function _parseLockTime(bytes memory script) internal pure returns (uint32) {
    uint256 t;
    assembly {
        let loc := add(script, 0x21)
        t := mload(loc)
    }
    return uint32(t.reverseUint256() & 0xFFFFFFFF);
  }

  /// add BTC stake transaction expiration record
  /// @param receipt the receipt object parsed from the BTC stake transaction
  /// @param lockTime the CLTV locktime of the BTC stake transaction
  /// @param amount the amount of the BTC stake transaction
  function _addExpire(DepositReceipt storage receipt, uint32 lockTime, uint64 amount) internal {
    uint256 endRound = uint256(lockTime) / SatoshiPlusHelper.ROUND_INTERVAL;
    ExpireInfo storage expireInfo = round2expireInfoMap[endRound];
    uint256 existAmount = expireInfo.amountMap[receipt.candidate];
    if (existAmount == 0) {
      expireInfo.candidateList.push(receipt.candidate);
      existAmount = 1;
    }
    expireInfo.amountMap[receipt.candidate] = existAmount + amount;
  }

  /// Parses the target output and the op_return of a transaction
  /// @dev  Finds the BTC amount that payload size is less than 80 bytes
  /// @param _voutView      The vout of a Bitcoin transaction
  /// @param _script      redeem script of the locked up output
  /// @return btcAmount   Amount of BTC to stake
  /// @return outputIndex The output index of target output.
  /// @return delegator   The one who delegate the Bitcoin
  /// @return candidate   A candidate node address.
  function _parseVout(
      bytes29 _voutView,
      bytes memory _script
  ) internal pure returns (uint64 btcAmount, uint32 outputIndex, address delegator, address candidate) {
    _voutView.assertType(uint40(BitcoinHelper.BTCTypes.Vout));
    bytes29 _outputView;
    bytes29 _scriptPubkeyView;
    bytes29 _scriptPubkeyWithLength;
    bytes29 _arbitraryData;

    // Finds total number of outputs
    uint _numberOfOutputs = uint256(_voutView.indexCompactInt(0));
    bool opreturn;

    for (uint index = 0; index < _numberOfOutputs; index++) {
      _outputView = _voutView.indexVout(index);
      _scriptPubkeyView = _outputView.scriptPubkey();
      _scriptPubkeyWithLength = _outputView.scriptPubkeyWithLength();
      _arbitraryData = _scriptPubkeyWithLength.opReturnPayload();

      // Checks whether the output is an arbitrary data or not
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
          (delegator, candidate) = _parsePayloadAndCheckProtocol(_arbitraryData);
          opreturn = true;
      }
    }
    require(btcAmount != 0, "staked value is zero");
    require(opreturn, "no opreturn");
  }

  /// parse the payload and do sanity check for SAT+ bytes
  /// @param payload the BTC transaction payload
  function _parsePayloadAndCheckProtocol(bytes29 payload) internal pure returns (address delegator, address candidate) {
    require(payload.len() >= 48, "payload length is too small");
    require(payload.indexUint(0, 4) == SatoshiPlusHelper.BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == SatoshiPlusHelper.CHAINID, "wrong chain id");
    uint32 version = uint32(payload.indexUint(4, 1));
    require(version == SatoshiPlusHelper.BTC_STAKE_VERSION, "unsupported sat+ version in btc staking");
    candidate = payload.indexAddress(27);
    delegator = payload.indexAddress(7);
  }

  /// get accrued rewards of a validator candidate on a given round
  /// @param candidate validator candidate address
  /// @param round the round to calculate rewards
  /// @return reward the amount of rewards
  function _getRoundAccruedReward(address candidate, uint256 round) internal returns (uint256 reward) {
    reward = accruedRewardPerBTCMap[candidate][round];
    if (reward != 0) {
      return reward;
    }

    // there might be no rewards for a candidate on a given round if it is unelected or jailed, etc
    // the accrued reward map will only be updated when reward is distributed to the candidate on that round
    // in that case, the accrued reward for round N == a round smaller but also closest to N
    // here we use binary search to get that round efficiently
    Candidate storage c = candidateMap[candidate];
    uint256 b = c.continuousRewardEndRounds.length;
    if (b == 0) {
      return 0;
    }
    b -= 1;
    uint256 a;
    uint256 m;
    uint256 targetRound;
    uint256 t;
    while (a <= b) {
      m = (a + b) / 2;
      t = c.continuousRewardEndRounds[m];
      if (t < round) {
        targetRound = t;
        a = m + 1;
      } else if (m == 0) {
        return 0;
      } else {
        b = m - 1;
      }
    }

    if (targetRound != 0) {
      reward = accruedRewardPerBTCMap[candidate][targetRound];
      accruedRewardPerBTCMap[candidate][round] = reward;
    }
    return reward;
  }

  /// Exposed for staking API to do readonly calls, restricted to onlyBtcAgent() for safety reasons.
  /// @param txid the BTC stake transaction id
  /// @param drRound the start round
  /// @param settleRound the settlement round
  /// @return reward reward of the BTC stake transaction
  /// @return expired whether the stake is expired
  /// @return rewardUnclaimed unclaimed reward of the BTC stake transaction
  /// @return accStakedAmount accumulated stake amount (multiplied by days), used for grading calculation
  function viewCollectReward(bytes32 txid, uint256 drRound, uint256 settleRound) external onlyBtcAgent returns (uint256 reward, bool expired, uint256 rewardUnclaimed, uint256 accStakedAmount) {
    return _collectReward(txid, drRound, settleRound);
  }

  function _collectReward(bytes32 txid, uint256 settleRound) internal returns (uint256 reward, bool expired, uint256 rewardUnclaimed, uint256 accStakedAmount) {
    DepositReceipt storage dr = receiptMap[txid];
    return _collectReward(txid, dr.round, settleRound);
  }

  /// collect rewards for a given BTC stake transaction & time grading is applied
  /// @param txid the BTC stake transaction id
  /// @param drRound the start round
  /// @param settleRound the settlement round
  /// @return reward reward of the BTC stake transaction
  /// @return expired whether the stake is expired
  /// @return rewardUnclaimed unclaimed reward of the BTC stake transaction
  /// @return accStakedAmount accumulated stake amount (multiplied by days), used for grading calculation
  function _collectReward(bytes32 txid, uint256 drRound, uint256 settleRound) internal returns (uint256 reward, bool expired, uint256 rewardUnclaimed, uint256 accStakedAmount) {
    BtcTx storage bt = btcTxMap[txid];
    DepositReceipt storage dr = receiptMap[txid];
    require(drRound != 0, "invalid deposit receipt");
    require(settleRound < roundTag, "invalid settle round");
    uint256 unlockRound1 = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL - 1;
    if (drRound < settleRound && drRound < unlockRound1) {
      uint256 minRound = settleRound < unlockRound1 ? settleRound : unlockRound1;
      // full reward
      reward = (_getRoundAccruedReward(dr.candidate, minRound) - _getRoundAccruedReward(dr.candidate, drRound)) * bt.amount / SatoshiPlusHelper.BTC_DECIMAL;
      accStakedAmount = bt.amount * (minRound - drRound);

      // apply time grading to BTC rewards
      if (gradeActive && grades.length != 0) {
        uint64 lockDuration = bt.lockTime - bt.blockTimestamp;
        uint256 p = grades[0].percentage;
        for (uint256 j = grades.length - 1; j != 0; j--) {
          if (lockDuration >= grades[j].lockDuration) {
            p = grades[j].percentage;
            break;
          }
        }
        uint256 rewardClaimed = reward * p / SatoshiPlusHelper.DENOMINATOR;
        rewardUnclaimed = reward - rewardClaimed;
        reward = rewardClaimed;
      }

      dr.round = minRound;
    }

    if (unlockRound1 <= settleRound) {
      emit btcExpired(txid, dr.delegator);
      delete receiptMap[txid];
      return (reward, true, rewardUnclaimed, accStakedAmount);
    }
    return (reward, false, rewardUnclaimed, accStakedAmount);
  }
}
