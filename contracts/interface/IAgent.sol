// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IAgent {
  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveCandidate(address candidate);

  /// Same address provided when transfer.
  /// @param candidate Address of the candidate
  error SameCandidate(address candidate);

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
  /// @param coreAmount the accumurated amount of staked CORE.
  /// @param settleRound the settlement round
  /// @param claim claim or store rewards
  /// @return reward Amount claimed
  /// @return floatReward floating reward amount
  /// @return accStakedAmount accumulated stake amount (multiplied by rounds), used for grading calculation
  function claimReward(address delegator, uint256 coreAmount, uint256 settleRound, bool claim) external returns (uint256 reward, int256 floatReward, uint256 accStakedAmount);
}