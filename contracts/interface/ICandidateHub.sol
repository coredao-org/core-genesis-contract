pragma solidity 0.6.12;

interface ICandidateHub {
  function canDelegate(address agent) external view returns(bool);
  function jailValidator(address operateAddress, uint256 round, uint256 fine) external;
}
