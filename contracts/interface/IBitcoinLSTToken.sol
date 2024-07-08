// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinLSTToken {
  function mint(address delegator, uint256 amount) external;
  function burn(address delegator, uint256 amount) external;
}