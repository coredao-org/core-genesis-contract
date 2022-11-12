pragma solidity 0.6.12;

interface IValidatorSet {
  function misdemeanor(address validator) external;
  function felony(address validator, uint256 felonyRound, uint256 felonyDeposit) external;
  function distributeReward() external;
  function updateValidatorSet(address[] calldata operateAddrList, address[] calldata consensusAddrList, address payable[] calldata feeAddrList, uint256[] calldata commissionThousandthsList) external;
  function isValidator(address addr) external returns (bool);
}
