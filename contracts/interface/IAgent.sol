// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IAgent {
  /// Receive round rewards from ValidatorSet, which is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  /// @param originValidatorSize The validator size at the begin of round.
  /// @param roundTag The round tag
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 originValidatorSize, uint256 roundTag) external payable;
  
  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  /// @param validateSize The validate size of this round
  /// @param roundTag The new round tag
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmount(address[] calldata candidates, uint256 validateSize, uint256 roundTag) external returns (uint256[] memory amounts, uint256 totalAmount);

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param roundTag The new round tag
  function setNewRound(address[] calldata validators, uint256 roundTag) external;
}