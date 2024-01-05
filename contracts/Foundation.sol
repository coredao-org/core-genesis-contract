// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";

/// This is the DAO Treasury smart contract
/// The funds in this contract can only be moved through governance vote
contract Foundation is System {
  event received(address indexed from, uint256 amount);
  event fundSuccess(address indexed payee, uint256 amount);

  receive() external payable {
    if (msg.value != 0) {
      emit received(msg.sender, msg.value);
    }
  }

  /// Send funds to a specific address with specific amount
  /// @param payee The address to send funds to
  /// @param amount The amount of funds to send
  function fund(address payable payee, uint256 amount) external onlyGov {
      require(payee != address(0), "Payee address should not be zero.");
      (bool success, ) = payee.call{value: amount}("");
      require(success, "Fund transfer failed.");
      emit fundSuccess(payee, amount);
  }
}
