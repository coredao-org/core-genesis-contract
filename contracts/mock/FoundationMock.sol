// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../Foundation.sol";
import {BaseMock} from "./BaseMock.sol";


contract FoundationMock is Foundation , BaseMock {

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

