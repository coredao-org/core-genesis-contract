// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IPledgeAgent.sol";
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


  function delegate(bytes memory payload, bytes memory script, uint256 value) internal {
  }

  function undelegate(bytes memory btctx) internal {
    // receiptMap[txid];
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
    if (Memory.compareStrings(key, "add")) {
      addMultisigAddress(value);
    } else if (Memory.compareStrings(key, "remove")) {
      removeWallet(value);
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

}
