pragma solidity ^0.6.4;

interface IValidatorSet {
  function misdemeanor(address validator) external;
  function felony(address validator, uint256 felonyRound, int256 felonyDeposit) external;
  function distributeReward() external;
  function updateValidatorSet(address[] memory operateAddrList, address[] memory consensusAddrList, address payable[] memory feeAddrList, uint256[] memory commissionThousandthsList) external;
  function isValidator(address addr) external returns (bool);
}
