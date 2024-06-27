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

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedBtc(bytes32 indexed txid, address indexed agent, address indexed delegator, bytes script, uint256 outputIndex, uint32 amount);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveAgent(address candidate);

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
    rewardPerBTC[roundTag] += rewardPerBTC[lastRoundTag] + reward * BTC_DECIMAL / totalAmount;
    lastRoundTag = roundTag;
  }
  function getStakeAmounts(address[] calldata candidates) external returns (uint256 totalAmount) {
    return IPledgeAgent(PLEDGE_AGENT_ADDR).getBTCAmount(candidates);
  }
  function getLastRoundStakeAmounts(address[] calldata validators) external returns (uint256[] memory amounts) {
  
  }

  function claimReward() {
    (rewardPerBTC[roundTag-1] - rewardPerBTC[xxx]) * btcamount / BTC_DECIMAL;
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
    delegator= payload.indexAddress(7);
    agent = payload.indexAddress(27);
    fee = payload.indexUint(47, 1);
  }
}
