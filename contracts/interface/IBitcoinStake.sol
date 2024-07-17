// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinStake {
  /// Bitcoin delegate, it is called by relayer via BitcoinAgent.verifyMintTx
  ///
  /// @param txid the bitcoin tx hash
  /// @param delegator a Coredao address who delegate the Bitcoin
  /// @param candidate the candidate node address.
  /// @param script it is used to verify the target txout
  /// @param amount amount of the target txout
  function delegate(bytes32 txid, address delegator, address candidate, bytes memory script, uint256 amount) external;

  /// Bitcoin undelegate, it is called by relayer via BitcoinAgent.verifyBurnTx
  ///
  /// @param txid the bitcoin tx hash
  /// @param outpointHashs outpoints from tx inputs.
  /// @param voutView tx outs as bytes29.
  function undelegate(bytes32 txid, bytes32[] memory outpointHashs, bytes29 voutView) external;

  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external;

  /// Get real stake amount
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of amounts of all special candidates in this round
  function getStakeAmounts(address[] calldata candidates) external view returns (uint256[] memory amounts);

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param roundTag The new round tag
  function setNewRound(address[] calldata validators, uint256 roundTag) external;

  /// Receive round rewards from BitcoinAgent. It is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList) external;

  /// Claim reward for delegator
  /// @return reward Amount claimed
  function claimReward() external returns (uint256 reward);
}
