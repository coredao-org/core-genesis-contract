// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface IValidatorSet {
  function misdemeanor(address validator) external;
  function felony(address validator, uint256 felonyRound, uint256 felonyDeposit) external;
  function distributeReward() external returns (address[] memory operateAddrList);
  function updateValidatorSet(address[] calldata operateAddrList, address[] calldata consensusAddrList, address payable[] calldata feeAddrList, uint256[] calldata commissionThousandthsList, bytes[] calldata voteAddrs) external;
  function isValidator(address addr) external returns (bool);
  function getValidatorsAndVoteAddresses() external view returns (address[] memory, bytes[] memory);
}
