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

  struct BtcReceipt {
    uint32 height;
    uint32 outpointIndex; // output index.
    uint32 version;
    uint32 usedHeight;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);

  function init() external onlyNotInit {
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
    bytes32 txid = btcTx.calculateTxId();

    BtcReceipt storage br = btcReceiptMap[txid];
    require(br.height == 0, "btc tx confirmed");

    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, (btcConfirmBlock == 0 ? INIT_BTC_CONFIRM_BLOCK : btcConfirmBlock), nodes, index), "btc tx not confirmed");

    (,,bytes29 voutView,) = btcTx.extractTx();
    uint256 value;
    bytes29 payload;
    uint256 outputIndex;
    (value, payload, outputIndex) = voutView.parseToScriptValueAndData(script);
    require(br.value >= (minBtcValue == 0 ? INIT_MIN_BTC_VALUE : minBtcValue), "staked value does not meet requirement");

    uint256 version = parsePayloadVersion(bytes29 payload);
    require(version == 1 || version == 2, "unsupport sat+ version");
    if (version == 1) {
      btcStake.delegate(payload, script, value);
    } else
      btcLSTStake.delegate(payload, script, value);
    }
    br.height = blockHeight;
    br.outpointIndex = outputIndex;
    br.version = version;
  }

  function verifyBurnTx(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external {
    bytes32 txid = btcTx.calculateTxId();
    require(ILightClient(LIGHT_CLIENT_ADDR).
      checkTxProof(txid, blockHeight, (btcConfirmBlock == 0 ? INIT_BTC_CONFIRM_BLOCK : btcConfirmBlock), nodes, index), "btc tx not confirmed");
    (,bytes29 _vinView, bytes29 voutView,) = btcTx.extractTx();
    // TODO iterate vin
    // match outpoint in btcReceiptMap.
    // update it btcReceiptMap[outpoint.hash].usedHeight = blockHeight

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
  function parsePayloadVersion(bytes29 payload) internal pure returns (uint256) {
    require(payload.len() >= 48, "payload length is too small");
    require(payload.indexUint(0, 4) == BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == CHAINID, "wrong chain id");
    return payload.indexUint(4, 1);
    require(payload.indexUint(4, 1) == 1, "wrong version");
    delegator= payload.indexAddress(7);
    agent = payload.indexAddress(27);
    fee = payload.indexUint(47, 1) * FEE_FACTOR;
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