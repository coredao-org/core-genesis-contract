// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IRelayerHub.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";

/// This contract manages user delegate BTC.
/// Including both BTC independent delegate and LST delegate.
contract BitcoinAgent is IAgent, System, IParamSubscriber {
  using BitcoinHelper for *;
  using TypedMemView for *;

  uint64 public constant INIT_MIN_BTC_VALUE = 1e4;
  uint32 public constant INIT_BTC_CONFIRM_BLOCK = 3;
  uint32 public constant BTC_STAKING_VERSION = 1;
  uint32 public constant BTCLST_STAKING_VERSION = 2;

  // Key: candidate
  // value: btc amount;
  mapping (address => StakeAmount) public candidateMap;

  // key: bitcoin tx id
  // value: bitcoin receipt.
  mapping(bytes32 => BtcReceipt) public btcReceiptMap;

  // minimum acceptable value for a BTC staking transaction
  uint64 public minBtcValue;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // key: delegator, value: fee
  mapping(address => uint256) public liabilities;
  // key: relayer, value: fee
  mapping(address => uint256) public creditors;

  struct BtcReceipt {
    uint32 version;
    uint32 outputIndex;
    uint32 height;
    uint32 usedHeight;
  }

  struct StakeAmount {
    uint256 lstStakeAmount;
    uint256 stakeAmount;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);
  event verifiedMintTx(bytes32 indexed txid, uint32 version, uint32 blockHeight, uint32 outputIndex, uint256 fee);
  event verifiedBurnTx(bytes32 indexed txid, uint32 version, uint32 blockHeight, uint32 outputIndex);

  function init() external onlyNotInit {
    minBtcValue = INIT_MIN_BTC_VALUE;
    btcConfirmBlock = INIT_BTC_CONFIRM_BLOCK;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    IBitcoinStake(BTC_STAKE_ADDR).prepare(round);
    IBitcoinStake(BTCLST_STAKE_ADDR).prepare(round);
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round
  /// @param validatorList List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validatorList, uint256[] calldata rewardList, uint256 /*roundTag*/) external override onlyStakeHub {
    uint256 validatorSize = validatorList.length;
    require(validatorSize == rewardList.length, "the length of validatorList and rewardList should be equal");

    uint256[] memory rewards = new uint256[](validatorSize);
    uint256 avgReward;
    uint256 rewardValue;
    StakeAmount memory sa;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      sa = candidateMap[validatorList[i]];
      avgReward = rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / (sa.lstStakeAmount + sa.stakeAmount);
      rewards[i] = avgReward * sa.lstStakeAmount / SatoshiPlusHelper.BTC_DECIMAL;
      rewardValue += rewards[i];
    }
    IBitcoinStake(BTCLST_STAKE_ADDR).distributeReward(validatorList, rewards);
    rewardValue = 0;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      rewards[i] = rewardList[i] - rewards[i];
      rewardValue += rewards[i];
    }
    IBitcoinStake(BTC_STAKE_ADDR).distributeReward(validatorList, rewards);
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  ///
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmounts(address[] calldata candidates, uint256 /*roundTag*/) external override returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    uint256[] memory lstAmounts = IBitcoinStake(BTCLST_STAKE_ADDR).getStakeAmounts(candidates);
    amounts = IBitcoinStake(BTC_STAKE_ADDR).getStakeAmounts(candidates);

    for (uint256 i = 0; i < candidateSize; ++i) {
      amounts[i] += lstAmounts[i];
      totalAmount += amounts[i];
      candidateMap[candidates[i]].lstStakeAmount = lstAmounts[i];
      candidateMap[candidates[i]].stakeAmount = amounts[i];
    }
  }


  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    IBitcoinStake(BTC_STAKE_ADDR).setNewRound(validators, round);
    IBitcoinStake(BTCLST_STAKE_ADDR).setNewRound(validators, round);
  }

  /// Claim reward for delegator
  /// @return reward Amount claimed
  function claimReward() external override onlyStakeHub returns (uint256 reward) {
    reward = IBitcoinStake(BTC_STAKE_ADDR).claimReward();
    reward += IBitcoinStake(BTCLST_STAKE_ADDR).claimReward();
    return reward;
  }

  /*********************** External methods ***************************/
  /// Delegate BTC to Core network
  ///
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  /// @param script in v1, it is a redeem script of the locked up output
  ///               in v2, it is the decoded pk script's address in hash format.
  function verifyMintTx(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index, bytes memory script) external {

    bytes32 txid = btcTx.calculateTxId();

    BtcReceipt storage br = btcReceiptMap[txid];
    require(br.height == 0, "btc tx confirmed");

    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index), "btc tx not confirmed");

    uint32 version;
    uint256 fee;
    address delegator;
    uint32 outputIndex;
    {
      (,,bytes29 voutView,) = btcTx.extractTx();
      uint64 value;
      bytes29 payload;
      (value, payload, outputIndex) = voutView.parseToScriptValueAndData(script);
      require(value >= minBtcValue, "staked value does not meet requirement");
      address candidate;
      (version, delegator, candidate, fee) = parsePayloadAndCheckProtocol(payload);

      require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");

      if (version == BTC_STAKING_VERSION) {
        IBitcoinStake(BTC_STAKE_ADDR).delegate(txid, delegator, candidate, script, value);
      } else {
        IBitcoinStake(BTCLST_STAKE_ADDR).delegate(txid, delegator, candidate, script, value);
      }
    }


    if (fee != 0) {
      fee *= SatoshiPlusHelper.CORE_DECIMAL;
      liabilities[delegator] += fee;
      creditors[msg.sender] += fee;
    }
    br.height = blockHeight;
    br.outputIndex = outputIndex;
    br.version = version;
    emit verifiedMintTx(txid, version, blockHeight, outputIndex, fee);
  }

  function verifyBurnTx(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external {
    bytes32 txid = btcTx.calculateTxId();
    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index), "btc tx not confirmed");
    (,bytes29 _vinView, bytes29 voutView,) = btcTx.extractTx();

    (bytes32[] memory outpointHashs, bool version1, bool version2) = parseVin(_vinView, blockHeight);

    if (version1) {
      IBitcoinStake(BTC_STAKE_ADDR).undelegate(txid, outpointHashs, voutView);
    }
    if (version2) {
      IBitcoinStake(BTCLST_STAKE_ADDR).undelegate(txid, outpointHashs, voutView);

      // TODO voutView exchange set to btcReceiptMap.
    }
  }

  function updateStakeAmount(address candidate, uint256 stakeAmount) external onlyBtcStake {
    candidateMap[candidate].stakeAmount = stakeAmount;
  }

  /*********************** Internal method ********************************/
  function parsePayloadAndCheckProtocol(bytes29 payload) internal pure returns (uint32 version, address delegator, address candidate, uint256 fee) {
    require(payload.len() >= 7, "payload length is too small");
    require(payload.indexUint(0, 4) == SatoshiPlusHelper.BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == SatoshiPlusHelper.CHAINID, "wrong chain id");
    version = uint32(payload.indexUint(4, 1));
    require(version == BTC_STAKING_VERSION || version == BTCLST_STAKING_VERSION, "unsupport sat+ version");
    if (version == BTC_STAKING_VERSION) {
      require(payload.len() >= 48, "payload length is too small");
      candidate = payload.indexAddress(27);
      fee = payload.indexUint(47, 1);
    } else {
      require(payload.len() >= 28, "payload length is too small");
      fee = payload.indexUint(27, 1);
    }
    delegator = payload.indexAddress(7);
  }

  /// @notice             Parses the BTC vin and set btcReceipt as used.
  ///
  /// @param _vinView     The vin of a Bitcoin transaction
  /// @param _blockHeight The block height where tx build in
  /// @return outpointHashs The outpoint records.
  /// @return version1 Whether the outpoint records contains BTC_STAKING_VERSION.
  /// @return version2 Whether the outpoint records contains BTCLST_STAKING_VERSION.
  function parseVin(
      bytes29 _vinView,
      uint32 _blockHeight
  ) internal returns (bytes32[] memory outpointHashs, bool version1, bool version2) {
    _vinView.assertType(uint40(BitcoinHelper.BTCTypes.Vin));
    bytes32 _txId;
    uint32 _outputIndex;

    // Finds total number of outputs
    uint _numberOfInputs = uint256(_vinView.indexCompactInt(0));
    outpointHashs = new bytes32[](_numberOfInputs);
    uint256 outpointIndex;

    for (uint index = 0; index < _numberOfInputs; ++index) {
      (_txId, _outputIndex) = _vinView.extractOutpoint(index);
      BtcReceipt storage br = btcReceiptMap[_txId];
      if (br.height != 0 && br.outputIndex == _outputIndex) {
        br.usedHeight = _blockHeight;
        outpointHashs[outpointIndex] = _txId;
        ++outpointIndex;
        if (br.version == BTC_STAKING_VERSION) {
          version1 = true;
        } else if (br.version == BTCLST_STAKING_VERSION) {
          version2 = true;
        }
        emit verifiedBurnTx(_txId, br.version, _blockHeight, _outputIndex);
      }
    }
  }


  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    require(false, "unknown param");
    emit paramChange(key, value);
  }
}