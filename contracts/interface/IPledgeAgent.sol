// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IPledgeAgent {
  function addRoundReward(address[] calldata agentList, uint256[] calldata rewardList) payable external;
  function setNewRound(address[] calldata validatorList, uint256 round) external;
  function distributePowerReward(address candidate, address[] calldata miners) external;
  function onFelony(address agent) external;
  function delegateCoin(address agent) external payable;
  function undelegateCoin(address agent) external;
  function undelegateCoin(address agent, uint256 amount) external;
  function transferCoin(address sourceAgent, address targetAgent) external;
  function transferCoin(address sourceAgent, address targetAgent, uint256 amount) external;
  function claimReward(address[] calldata agentList) external returns (uint256, bool);
  function delegateBtc(bytes32 txid, uint32 lockTime, address delegator, address agent, uint256 value) external;
  function transferBtc(bytes32 txid, address targetAgent) external;
  function claimBtcReward(bytes32[] calldata txidList) external returns (uint256 rewardSum);
  function getBTCAmount(address[] calldata candidates) external returns(uint256[] memory amounts);
}
