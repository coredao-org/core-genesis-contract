// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import {Updatable} from "./util/Updatable.sol";
import {AllContracts} from "./util/TestnetUtils.sol";
import {ReentrancyGuard} from "./lib/ReentrancyGuard.sol";

/// This is the DAO Treasury smart contract
/// The funds in this contract can only be moved through governance vote
contract Foundation is System, ReentrancyGuard, Updatable {
  event received(address indexed from, uint256 amount);
  event fundSuccess(address indexed payee, uint256 amount);
  event fundFailed(address indexed payee, uint256 amount, uint256 balance);

  receive() external payable {
    if (msg.value != 0) {
      emit received(msg.sender, msg.value);
    }
  }

  function debug_init(AllContracts allContracts) external override canCallDebugInit {//zzzzzz call from tests
    _setLocalNodeAddresses(allContracts);
  }

  /// Send funds to a specific address with specific amount
  /// @param payee The address to send funds to
  /// @param amount The amount of funds to send
  function fund(address payable payee, uint256 amount) external nonReentrant onlyGov {
    require(payee != address(0), "payee address should not be zero");
    bool wasSent = _unsafeSend(payee, amount);
    if (wasSent) {
      emit fundSuccess(payee, amount);
    } else {
      emit fundFailed(payee, amount, address(this).balance);
    }
  }
}
