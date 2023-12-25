// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../SlashIndicator.sol";
import "../lib/RLPDecode.sol";
import {BaseMock} from "./BaseMock.sol";


contract SlashIndicatorMock is SlashIndicator , BaseMock {
    uint32 private constant MOCK_CHAINID = 1112;

    using RLPDecode for bytes;
    using RLPDecode for RLPDecode.RLPItem;

    function developmentInit() external {
        rewardForReportDoubleSign = rewardForReportDoubleSign / 1e16;
        felonyDeposit = felonyDeposit / 1e16;
        misdemeanorThreshold = 2;
        felonyThreshold = 4;
    }

    function parseHeader(bytes calldata header) public pure returns (bytes32, address) {
        RLPDecode.RLPItem[] memory items = header.toRLPItem().toList();
        return parseHeader(items);
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

  function getSlashValidators() external view returns (address[] memory) {
    return validators;
  }

  function _chainId() internal pure override returns (uint) {
    return uint(MOCK_CHAINID);
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

    function _isBlockProducer() internal override pure returns (bool) {
        return true;
    }

    function _zeroGasPrice() internal override pure returns (bool) {
        return true;
    }


    // -- address mock overrides --

    function _validatorSet() view internal override returns (address) {
        return _notNull(s_validatorSet);
    }

    function _slash() view internal override returns (address) {
        return _notNull(s_slash);
    }

    function _systemReward() view internal override returns (address) {
        return _notNull(s_systemReward);   
    }

    function _lightClient() view internal override returns (address) {
        return _notNull(s_lightClient); 
    }

    function _relayerHub() view internal override returns (address) {
        return _notNull(s_relayerHub);  
    }

    function _candidateHub() view internal override returns (address) {
        return _notNull(s_candidateHub);  
    }

    function _govHub() view internal override returns (address) {
        return _notNull(s_govHub);
    }

    function _pledgeAgent() view internal override returns (address) {
        return _notNull(s_pledgeAgent);  
    }

    function _burn() view internal override returns (address) {
        return _notNull(s_burn);  
    }

    function _foundation() view internal override returns (address) {
        return _notNull(s_foundation);  
    }    
}

