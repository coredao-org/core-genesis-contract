// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinLSTStake {
  function delegate(bytes memory payload, bytes memory script, uint256 value) external;
  function undelegate(bytes btctx) external;

  function distributeReward(uint256 reward, uint256 roundTag) external payable;
  function getStakeAmount() external returns (uint256 totalAmount);
  function getLastRoundStakeAmount() external returns (uint256 totalAmount);
}