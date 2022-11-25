// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface ISystemReward {
  function claimRewards(address payable to, uint256 amount) external returns(uint256 actualAmount);
  function receiveRewards() external payable;
}