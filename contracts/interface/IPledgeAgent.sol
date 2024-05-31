// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IPledgeAgent {
  function delegateCoin(address agent) external payable;
  function undelegateCoin(address agent) external;
  function undelegateCoin(address agent, uint256 amount) external;
  function transferCoin(address sourceAgent, address targetAgent) external;
  function transferCoin(address sourceAgent, address targetAgent, uint256 amount) external;
  function claimReward(address[] calldata agentList) external returns (uint256, bool);
  function calculateReward(address[] calldata agentList, address delegator) external returns (uint256);

  function claimBtcReward(bytes32[] calldata txidList) external returns (uint256 rewardSum);
}
