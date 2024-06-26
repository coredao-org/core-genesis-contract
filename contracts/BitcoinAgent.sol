// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinLST.sol";
import "./interface/IPledgeAgent.sol";
import "./lib/Address.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./System.sol";

/// This contract manages user delegate BTC.
/// Including both BTC independent delegate and LST delegate.
contract BitcoinAgent is IAgent, System, IParamSubscriber {

  // Protocol MAGIC `SAT+`, represents the short name for Satoshi plus protocol.
  uint256 public constant BTC_STAKE_MAGIC = 0x5341542b;
  uint256 public constant BTC_DECIMAL = 1e8;
  uint256 public constant CORE_DECIMAL = 1e18;
  uint64 public constant INIT_MIN_BTC_VALUE = 1e4;
  uint32 public constant INIT_BTC_CONFIRM_BLOCK = 3;
  uint32 public constant BTC_STAKING_VERSION = 1;
  uint32 public constant BTCLST_STAKING_VERSION = 2;

  address public btcStake; // oldBtcAddress is PledgeAgent
  address public btcLSTStake;

  // This field is used to store hash power reward of delegators
  // when turn round
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  // key: bitcoin tx id
  // value: bitcoin receipt.
  mapping(bytes32 => BtcReceipt) btcReceiptMap;

  // minimum acceptable value for a BTC staking transaction
  uint64 public minBtcValue;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // key: delegator, value: fee
  mapping(address => uint256) liabilities;
  // key: relayer, value: fee
  mapping(address => uint256) creditors;

  struct BtcReceipt {
    uint32 version;
    uint32 outputIndex;
    uint32 height;
    uint32 usedHeight;
  }

  struct STXO {
    bytes32 txid;
    uint32 outputIndex;
    uint32 version;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);

  function init() external onlyNotInit {
    minBtcValue = INIT_MIN_BTC_VALUE;
    btcConfirmBlock = INIT_BTC_CONFIRM_BLOCK;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 /*round*/) external override {
    // Nothing
  }

  /// Receive round rewards from ValidatorSet, which is triggered at the beginning of turn round
  /// @param validatorList List of validator operator addresses
  /// @param rewardList List of reward amount
  /// param originValidatorSize The validator size at the begin of round.
  /// @param roundTag The round tag
  function distributeReward(address[] calldata validatorList, uint256[] calldata rewardList, uint256 originValidatorSize, uint256 roundTag) external payable override onlyStakeHub {
    uint256 validatorSize = validatorList.length;
    require(validatorSize == rewardList.length, "the length of validatorList and rewardList should be equal");

    uint256 lstAmount = btcLST.getLastRoundStakeAmount();
    uint256 avgLstAmount = lstAmount / originValidatorSize;

    uint256[] memory amounts = IPledgeAgent(PLEDGE_AGENT_ADDR).getLastBTCAmount(validatorList);

    uint256 lstReward;
    uint256 btcReward;
    uint256 avgReward;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      avgReward = rewardList[i] * BTC_DECIMAL / (avgLstAmount + amounts[i]);
      lstReward += avgReward * avgLstAmount / BTC_DECIMAL;
      rewardList[i] = avgReward * amounts[i] / BTC_DECIMAL;
      btcReward += rewardList[i];
    }
    btcLST.distributeReward{ value: lstReward }(lstReward, roundTag);
    btcStake.distributeReward{ value: btcReward }(validatorList, rewardList, roundTag);
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  /// param validateSize The validate size of this round
  /// @param roundTag The new round tag
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmount(address[] calldata candidates, uint256 validateSize, uint256 roundTag) external override view returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    if (validateSize > candidateSize) {
      validateSize = candidateSize;
    }
    require(validateSize > 0, "validateSize should be positive")
    (bool success, bytes memory data) = btcLST.call{gas: 50000}(abi.encodeWithSignature("getStakeAmount()"));
    if (success) {
      totalAmount = abi.decode(data, (uint256));
    }
    uint256 avgSharedAmount = totalAmount / validateSize;

    // fetch hash power delegated on list of candidates
    // which is used to calculate hybrid score for validators in the new round
    amounts = IPledgeAgent(PLEDGE_AGENT_ADDR).getBTCAmount(candidates);
    for (uint256 i = 0; i < candidateSize; ++i) {
      amounts[i] += avgSharedAmount;
      totalAmount += amounts[i];
    }
  }

  /*********************** External methods ***************************/
  // User workflow to delegate BTC to Core blockchain
  //  1. A user creates a bitcoin transaction, locks up certain amount ot Bitcoin in one of the transaction output for certain period.
  //     The transaction should also have an op_return output which contains the staking information, such as the validator and reward addresses. 
  //  2. Transmit the transaction to Core blockchain by calling the below method `delegateBtc`.
  //  3. The user can claim rewards using the reward address set in step 1 during the staking period.
  //  4. The user can spend the timelocked UTXO using the redeem script when the lock expires.
  //     The redeem script should start with a time lock. such as:
  //         <abstract locktime> OP_CLTV OP_DROP <pubKey> OP_CHECKSIG
  //         <abstract locktime> OP_CLTV OP_DROP OP_DUP OP_HASH160 <pubKey Hash> OP_EQUALVERIFY OP_CHECKSIG
  //         <abstract locktime> OP_CLTV OP_DROP M <pubKey1> <pubKey1> ... <pubKeyN> N OP_CHECKMULTISIG
  /// delegate BTC to Core network
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  /// @param script the corresponding redeem script of the locked up output
  function verifyMintTx(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index, bytes memory script) external override {
    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "only relayer can submit the BTC transaction");

    bytes32 txid = btcTx.calculateTxId();

    BtcReceipt storage br = btcReceiptMap[txid];
    require(br.height == 0, "btc tx confirmed");

    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index), "btc tx not confirmed");

    (,,bytes29 voutView,) = btcTx.extractTx();
    (uint64 value, bytes29 payload, uint32 outputIndex) = voutView.parseToScriptValueAndData(script);
    require(value >= minBtcValue, "staked value does not meet requirement");

    uint32 version = parsePayloadVersionAndCheckProtocol(bytes29 payload);
    require(version == 1 || version == 2, "unsupport sat+ version");
    address delegator;
    uint256 fee;
    if (version == 1) {
      (delegator, fee) = btcStake.delegate(txid, payload, script, value);
    } else
      (delegator, fee) = btcLSTStake.delegate(txid, payload, script, value);
    }

    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");

    if (fee != 0) {
      fee *= CORE_DECIMAL;
      liabilities[delegator] += fee;
      creditors[msg.sender] += fee;
    }
    br.height = blockHeight;
    br.outputIndex = outputIndex;
    br.version = version;
  }

  function verifyBurnTx(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external {
    bytes32 txid = btcTx.calculateTxId();
    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index), "btc tx not confirmed");
    (,bytes29 _vinView, bytes29 voutView,) = btcTx.extractTx();

    STXO[] memory stxos = parseVin(_vinView, blockHeight);

    bool version1;
    bool version2;

    for (uint256 index = 0; index < stxos.length; ++index) {
      if (stxos[index].version == BTC_STAKING_VERSION) {
        version1 = true;
      } else if (stxos[index].version == BTCLST_STAKING_VERSION) {
        version2 = true;
      } else {
        break;
      }
    }

    if (version1) {
      btcStake.undelegate(txid, stxos, voutView);
    }
    if (version2) {
      btcLSTStake.undelegate(txid, stxos, voutView);

      // TODO voutView exchange set to btcReceiptMap.
    }
  }

  /// Claim reward for miner
  /// The param represents list of validators to claim rewards on.
  /// this contract implement is ignore.
  /// @return (Amount claimed, Are all rewards claimed)
  function claimReward(address[] calldata) external returns (uint256, bool) {
    uint256 rewardSum = rewardMap[msg.sender];
    if (rewardSum != 0) {
      rewardMap[msg.sender] = 0;
      Address.sendValue(payable(msg.sender), rewardSum);
      emit claimedReward(msg.sender, rewardSum);
    }

    IPledgeAgent(PLEDGE_AGENT_ADDR).claimReward(candidates);

    return (rewardSum, true);
  }

  /*********************** Internal method ********************************/
  function parsePayloadVersionAndCheckProtocol(bytes29 payload) internal pure returns (uint32) {
    require(payload.len() >= 7, "payload length is too small");
    require(payload.indexUint(0, 4) == BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == CHAINID, "wrong chain id");
    return payload.indexUint(4, 1);
    #require(payload.indexUint(4, 1) == 1, "wrong version");
    #delegator= payload.indexAddress(7);
    #agent = payload.indexAddress(27);
    #fee = payload.indexUint(47, 1) * FEE_FACTOR;
  }


  /// @notice             Parses the BTC vin and set btcReceipt as used.
  ///
  /// @param _vinView     The vin of a Bitcoin transaction
  /// @param _blockHeight The block height where tx build in
  /// @return stxos       The stxo records.
  function parseVin(
      bytes29 _vinView,
      uint32 _blockHeight
  ) internal typeAssert(_vinView, BTCTypes.Vin) returns (STXO[] memory stxos) {
      bytes32 _txId;
      uint _outputIndex;

      // Finds total number of outputs
      uint _numberOfInputs = uint256(indexCompactInt(_vinView, 0));
      receipts = new STXO[](_numberOfInputs);
      uint stxoIndex;

      for (uint index = 0; index < _numberOfInputs; ++index) {
          (_txId, _outputIndex) = extractOutpoint(_vinView, index);
          BtcReceipt br storage = btcReceiptMap[_txId];
          if (br.height != 0 && br.outputIndex == _outputIndex) {
            br.usedHeight = _blockHeight;
            stxos[stxoIndex] = STXO(_txId, _outputIndex, br.version);
            ++stxoIndex;
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