// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import '@openzeppelin/contracts/token/ERC20/IERC20.sol';

interface IBitcoinLSTToken is IERC20 {
  function mint(address delegator, uint256 amount) external;
  function burn(address delegator, uint256 amount) external;
}