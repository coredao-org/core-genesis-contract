// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IPledge {
  function distributeReward(uint256 reward) external payable;
  function getPledgeAmount() external returns (uint256 totalPledgeAmount);
}