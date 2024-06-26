// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinStake {
  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 amount) external returns (address delegator, uint256 fee);
  function undelegate(bytes memory btctx) external;

  function distributeReward(uint256 reward, uint256 roundTag) external payable;
  function getStakeAmount() external returns (uint256 totalAmount);
  function getLastRoundStakeAmount() external returns (uint256 totalAmount);
}
