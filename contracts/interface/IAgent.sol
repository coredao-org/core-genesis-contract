// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IAgent {
  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external;

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  /// @param round The new round tag
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmounts(address[] calldata candidates, uint256 round) external returns (uint256[] memory amounts, uint256 totalAmount);

  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external;

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  /// @param round The round tag
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 round) external;

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  function claimReward(address delegator) external returns (uint256 reward, uint256 rewardUnclaimed);
}