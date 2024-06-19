// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinLST {
  function distributeReward(uint256 reward) external payable;
  function getStakeAmount() external returns (uint256 totalAmount);
}