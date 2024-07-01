// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IBitcoinStake {
  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 amount, uint256 outputIndex) external returns (address delegator, uint256 fee);
  function undelegate(bytes32 txid, bytes memory stxos, bytes29 voutView) external;

  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 roundTag) external payable;
  function getStakeAmounts(address[] calldata candidators) external returns (uint256[] memory amounts);
  function getLastRoundBTCAmounts(address[] calldata validators) external view returns (uint256[] memory amounts);

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param roundTag The new round tag
  function setNewRound(address[] calldata validators, uint256 roundTag) external;
}
