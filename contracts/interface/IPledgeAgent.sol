pragma solidity ^0.6.4;

interface IPledgeAgent {
  function addRoundReward(address[] memory agentList, uint256[] memory rewardList) payable external;
  function getIntegral(address[] memory candidates, bytes20[] memory lastMiners, bytes20[] memory miners, uint256[] memory powers) external returns(uint256[] memory, uint256, uint256);
  function setNewRound(address[] memory validatorList, uint256 totalPower, uint256 totalCoin, uint256 round) external;
  function inactiveAgent(address agent) external;
}
