// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface ICandidateHub {
  function canDelegate(address candidate) external view returns(bool);
  function isValidator(address candidate) external view returns(bool);
  function isCandidateByOperate(address operateAddr) external view returns(bool);
  function jailValidator(address operateAddr, uint256 round, uint256 fine) external;
  function getRoundTag() external view returns(uint256);
  function getInitValidatorCount() external pure returns(uint256);
}