pragma experimental ABIEncoderV2;
pragma solidity 0.8.4;

import "../SlashIndicator.sol";

contract SlashIndicatorMock is SlashIndicator {
    constructor() public SlashIndicator() {}

    function developmentInit() external {
        rewardForReportDoubleSign = rewardForReportDoubleSign / 1e16;
        felonyDeposit = felonyDeposit / 1e16;
        misdemeanorThreshold = 2;
        felonyThreshold = 4;
    }

    function parseHeader(bytes calldata header1) public pure returns (bytes32, address) {
        RLPDecode.RLPItem[] memory items1 = header1.toRLPItem().toList();
        return parseHeader(items1);
    }

  function setIndicators(address[] calldata newValidators, uint256[] calldata counts) public {
    for (uint256 i = validators.length; i > 0; i--) {
      delete indicators[validators[i - 1]];
      validators.pop();
    }

    for (uint256 i = newValidators.length; i > 0; i--) {
      indicators[newValidators[i-1]] = Indicator(0, counts[i-1], true);
      validators.push(newValidators[i-1]);
    }
  }

  function getIndicators() public view returns (address[] memory, uint256[] memory) {
    address[] memory v = new address[](validators.length);
    uint256[] memory c = new uint256[](validators.length);
    for (uint256 i = 0; i < validators.length; i++) {
      v[i] = validators[i];
      c[i] = indicators[v[i]].count;
    }
    return (v, c);
  }
}
