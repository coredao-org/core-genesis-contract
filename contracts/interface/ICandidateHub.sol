// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface ICandidateHub {
  function canDelegate(address agent) external view returns(bool);
  function isCandidateByOperate(address agent) external view returns(bool);
  function jailValidator(address operateAddress, uint256 round, uint256 fine) external;
  function getRoundTag() external view returns(uint256);
}
