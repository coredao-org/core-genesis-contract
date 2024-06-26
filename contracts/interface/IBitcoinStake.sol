// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinStake {
  function delegate(uint32 blockHeight, bytes29 payload, bytes memory script, bytes32 txid, uint32 outputIndex) external;
  function undelegate(bytes memory btctx) external;

  function distributeReward(uint256 reward, uint256 roundTag) external payable;
  function getStakeAmount() external returns (uint256 totalAmount);
  function getLastRoundStakeAmount() external returns (uint256 totalAmount);
}
