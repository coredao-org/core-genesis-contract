pragma solidity 0.6.12;

interface ISystemReward {
  function claimRewards(address payable to, uint256 amount) external returns(uint256 actualAmount);
  function receiveRewards() external payable;
}