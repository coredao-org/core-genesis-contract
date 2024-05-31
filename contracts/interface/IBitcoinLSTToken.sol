// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinLSTToken {
  function mint(address delegator, uint256 amount) external onlyBTCLSTStake;
  function burn(uint256 amount) external;
  function burned(bytes[] calldata lockscripts, uint256[] calldata amounts) external onlyBTCLSTStake;

  function distributeReward(uint256 reward, uint256 roundTag) external payable;
  function getTotalSupply() external returns (uint256 totalAmount);
}