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
  mapping(address => Candidate) public candidateMap;

  // This field is used to store reward of delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => Reward) public rewardMap;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // This field keeps the amount of expired BTC staking value for each round
  // Key: round
  // Value: expire info of exch round.
  mapping(uint256 => ExpireInfo) round2expireInfoMap;

  TLP[] public tlpRates;

  bool public isActive;

  struct BtcTx {
    uint64 amount;
    uint32 outputIndex;
    uint64 blockTimestamp;
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
    uint256 stakedAmount;
    uint256 realAmount;
    uint256[] continuousRewardEndRounds;
  }

  struct ExpireInfo {
    address[] candidateList;
    mapping(address => uint256) amountMap;
  }

  struct TLP {
    uint256 tl;
    uint256 tp;
  }

  struct Reward {
    uint256 reward;
    uint256 unclaimedReward;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, bytes script, uint256 amount);
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

  /*********************** Init ********************************/
  function init() external onlyNotInit {
    roundTag = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    btcConfirmBlock = SatoshiPlusHelper.INIT_BTC_CONFIRM_BLOCK;
  }

  function initHardforkRound(address[] memory candidates, uint256[] memory amounts, uint256[] memory realAmounts) external onlyPledgeAgent {
    uint256 s = candidates.length;
    for (uint256 i = 0; i < s; ++i) {
      Candidate storage c = candidateMap[candidates[i]];
      c.stakedAmount = amounts[i];
      c.realAmount = realAmounts[i];
    }
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
    uint32 lockTime = parseLockTime(script);
    {
      (bool txChecked, uint64 blockTimestamp) = ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index);
      require(txChecked, "btc tx isn't confirmed");
      // compatible for migrated data.
      if (bt.amount > 0 && bt.blockTimestamp == 0) {
        bt.blockTimestamp = blockTimestamp;
        return;
      }
      require(bt.amount == 0, "btc tx is already delegated.");
      uint256 endRound = lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
      require(endRound > roundTag + 1, "insufficient locking rounds");
      bt.lockTime = lockTime;
      bt.blockTimestamp = blockTimestamp;
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
    candidateMap[candidate].realAmount += btcAmount;

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
    (bool txChecked, ) = ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index);
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
      m[roundTag] = historyReward + rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / c.stakedAmount;
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
      amounts[i] = candidateMap[candidates[i]].realAmount;
    }
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  function claimReward(address delegator) external override onlyBtcAgent returns (uint256 reward, uint256 rewardUnclaimed) {
    bool expired;
    bytes32[] storage txids = delegatorMap[delegator].txids;
    for (uint256 i = txids.length; i != 0; i--) {
      (, expired) = collectReward(txids[i - 1], false);
      if (expired) {
        if (i != txids.length) {
          txids[i - 1] = txids[txids.length - 1];
        }
        txids.pop();
      }
    }
    reward = rewardMap[delegator].reward;
    rewardUnclaimed = rewardMap[delegator].unclaimedReward;
    if (reward != 0) {
      delete rewardMap[delegator];
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
      candidateMap[validator].stakedAmount = candidateMap[validator].realAmount;
    }
    roundTag = round;
  }

  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    // the expired BTC staking values will be removed
    address candidate;
    for (uint256 r = roundTag + 1; r <= round; ++r) {
      ExpireInfo storage expireInfo = round2expireInfoMap[r];
      uint256 l = expireInfo.candidateList.length;
      if (l == 0) continue;
      for (uint256 j = l; j != 0; --j) {
        candidate = expireInfo.candidateList[j - 1];
        candidateMap[candidate].realAmount -= (expireInfo.amountMap[candidate] - 1);
        expireInfo.candidateList.pop();
        delete expireInfo.amountMap[candidate];
      }
      delete round2expireInfoMap[r];
    }
  }

  /*********************** External methods **************************/

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
    collectReward(txid, false);

    Candidate storage c = candidateMap[candidate];
    c.realAmount -= amount;
    round2expireInfoMap[endRound].amountMap[candidate] -= amount;

    // Set candidate to targetCandidate
    dr.candidate = targetCandidate;
    dr.round = roundTag + 1;
    addExpire(dr, bt.lockTime, amount);

    Candidate storage tc = candidateMap[targetCandidate];
    tc.realAmount += amount;

    emit transferredBtc(txid, candidate, targetCandidate, msg.sender, bt.amount);
  }

  function calculateReward(bytes32[] calldata txids) external returns (uint256 amount) {
    uint256 reward;
    for (uint256 i = txids.length; i != 0; i--) {
      (reward, ) = collectReward(txids[i - 1], true);
      amount += reward;
    }
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

      addExpire(dr, uint32(lockTime), uint64(amount));

      emit migrated(txid);
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

    if(Memory.compareStrings(key, "tlpRates")) {
      uint256 i;
      uint256 lastLength = tlpRates.length;
      uint256 currentLength = value.indexUint(0, 1);

      require(((currentLength << 2) + 1) == value.length, "invalid param length");

      for (i = currentLength; i < lastLength; i++) {
        tlpRates.pop();
      }

      for (i = 0; i < currentLength; i++) {
        uint256 startIndex = (i << 2) + 1;
        uint256 tl = value.indexUint(startIndex, 2);
        require(tl <= SatoshiPlusHelper.DENOMINATOR, "invalid param tl");
        uint256 tp =  value.indexUint(startIndex + 2, 2);
        require(tp <= SatoshiPlusHelper.DENOMINATOR, "invalid param tl");
        TLP memory lp = TLP({
          tl: tl,
          tp: tp
        });

        if (i >= lastLength) {
          tlpRates.push(lp);
        } else {
          tlpRates[i] = lp;
        }
      }
    } else if (Memory.compareStrings(key, "isActive")) {
      uint256 newIsActive = value.toUint256(0);
      if (newIsActive > 1) {
        revert OutOfBounds(key, newIsActive, 0, 1);
      }
      isActive = newIsActive == 1;
    } else {
      require(false, "unknown param");
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

  function getRoundAccuredReward(address candidate, uint256 round) internal returns (uint256 reward) {
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
    uint256 targetRound;
    uint256 t;
    while (a <= b) {
      m = (a + b) / 2;
      t = c.continuousRewardEndRounds[m];
      // tr should never be equal to round because the above reward value is zero.
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
      reward = accuredRewardPerBTCMap[candidate][targetRound];
      accuredRewardPerBTCMap[candidate][round] = reward;
    }
    return reward;
  }

  function collectReward(bytes32 txid, bool pop) internal returns (uint256 reward, bool expired) {
    BtcTx storage bt = btcTxMap[txid];
    DepositReceipt storage dr = receiptMap[txid];
    uint256 drRound = dr.round;
    require(dr.round != 0, "invalid deposit receipt");
    uint256 lastRound = roundTag - 1;
    uint256 unlockRound1 = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL - 1;
    if (drRound < lastRound && drRound < unlockRound1) {
      uint256 minRound = lastRound < unlockRound1 ? lastRound : unlockRound1;
      // Calculate reward
      reward = (getRoundAccuredReward(dr.candidate, minRound) - getRoundAccuredReward(dr.candidate, drRound)) * bt.amount / SatoshiPlusHelper.BTC_DECIMAL;
      
      uint256 rewardUnclaimed = 0;
      if (isActive && tlpRates.length != 0) {
        // TLP Rates is configured
        uint256 delegateMonth = (bt.lockTime - bt.blockTimestamp) / 86400 / 30;
        uint256 p =  SatoshiPlusHelper.DENOMINATOR;
        for (uint256 j = tlpRates.length; j != 0; j--) {
          if (delegateMonth >= tlpRates[j].tl) {
            p = tlpRates[j].tp;
            break;
          }
        }
        uint256 rewardClaimed = reward * p / SatoshiPlusHelper.DENOMINATOR;
        rewardUnclaimed = reward - rewardClaimed;
        reward = rewardClaimed;
      }
      
      dr.round = minRound;
      if (reward != 0) {
        rewardMap[dr.delegator].reward += reward;
      }
      if (rewardUnclaimed != 0) {
        rewardMap[dr.delegator].unclaimedReward += rewardUnclaimed;
      }
    }
    // Remove txid and deposit receipt
    if (unlockRound1 < roundTag) {
      if (pop) {
        bytes32[] storage txids = delegatorMap[dr.delegator].txids;
        for (uint i = txids.length; i != 0; --i) {
          if (txids[i - 1] == txid) {
            if (i != txids.length) {
              txids[i - 1] = txids[txids.length - 1];
            }
            txids.pop();
            break;
          }
        }
      }
      emit btcExpired(txid, dr.delegator);
      delete receiptMap[txid];
      return (reward, true);
    }
    return (reward, false);
  }
}
