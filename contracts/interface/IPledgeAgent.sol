// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IPledgeAgent {
  function addRoundReward(address[] calldata agentList, uint256[] calldata rewardList) payable external;
  function getHybridScore(address[] calldata candidates, uint256[] calldata powers) external returns(uint256[] memory, uint256, uint256);
  function setNewRound(address[] calldata validatorList, uint256 totalPower, uint256 totalCoin, uint256 round) external;
  function distributePowerReward(address candidate, address[] calldata miners) external;
  function onFelony(address agent) external;
}
