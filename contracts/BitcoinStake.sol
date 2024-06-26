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

  uint256 public constant INIT_DELEGATE_BTC_GAS_PRICE = 1e12;
  uint256 public constant BTC_STAKE_MAGIC = 0x5341542b;
  uint256 public constant CHAINID = 1116;
  uint256 public constant FEE_FACTOR = 1e18;

  uint256 public delegateBtcGasPrice;

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed agent, address indexed delegator, bytes script, uint32 blockHeight, uint256 outputIndex);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveAgent(address candidate);

  function delegate(uint32 blockHeight, bytes29 payload, bytes memory script, bytes32 txid, uint32 outputIndex) override external {
    require(script[0] == bytes1(uint8(0x04)) && script[5] == bytes1(uint8(0xb1)), "not a valid redeem script");
    require(tx.gasprice <= (delegateBtcGasPrice == 0 ? INIT_DELEGATE_BTC_GAS_PRICE : delegateBtcGasPrice), "gas price is too high");

    uint32 lockTime = parseLockTime(script);

    (address delegator, address agent, uint256 fee) = parseAndCheckPayload(payload);
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).isCandidateByOperate(agent)) {
      revert InactiveAgent(agent);
    }

    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");
   
    IPledgeAgent(PLEDGE_AGENT_ADDR).delegateBtc(blockHeight, payload, script, txid, lockTime, delegator, agent, fee);

    emit delegatedBtc(txid, agent, delegator, script, blockHeight, outputIndex);
  }

  function undelegate(bytes memory btctx) override external {
    // TODO clear the stake tx.
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }

    if (Memory.compareStrings(key,"delegateBtcGasPrice")) {
      uint256 newDelegateBtcGasPrice = BytesToTypes.bytesToUint256(32, value);
      if (newDelegateBtcGasPrice < 1e9) {
        revert OutOfBounds(key, newDelegateBtcGasPrice, 1e9, type(uint256).max);
      }
      delegateBtcGasPrice = newDelegateBtcGasPrice;
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

  function parseAndCheckPayload(bytes29 payload) internal pure returns (address delegator, address agent, uint256 fee) {
    require(payload.len() >= 48, "payload length is too small");
    require(payload.indexUint(0, 4) == BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(4, 1) == 1, "wrong version");
    require(payload.indexUint(5, 2) == CHAINID, "wrong chain id");
    delegator= payload.indexAddress(7);
    agent = payload.indexAddress(27);
    fee = payload.indexUint(47, 1) * FEE_FACTOR;
  }
}
