pragma solidity 0.6.12;

interface IPledgeAgent {
  function addRoundReward(address[] memory agentList, uint256[] memory rewardList) payable external;
  function getHybridScore(address[] memory candidates, uint256[] memory powers) external returns(uint256[] memory, uint256, uint256);
  function setNewRound(address[] memory validatorList, uint256 totalPower, uint256 totalCoin, uint256 round) external;
  function distributePowerReward(address candidate, address[] memory miners) external;
}
