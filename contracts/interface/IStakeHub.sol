// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IStakeHub {
  function addRoundReward(address[] calldata validatorList,
    uint256[] calldata rewardList,
    uint256 roundTag) payable external;
  function getHybridScore(address[] calldata candidates, uint256 roundTag) external returns(uint256[] memory);
  function setNewRound(address[] calldata validatorList, uint256 roundTag) external;

  function addNotePayable(address delegator, address creditor, uint256 amount) external;
}
