// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../GovHub.sol";
import {BaseMock} from "./BaseMock.sol";


contract GovHubMock is GovHub , BaseMock {
    uint256 private constant MOCK_VOTING_PERIOD = 201600;
    uint256 private constant MOCK_EXECUTING_PERIOD = 201600;
    bytes private constant MOCK_INIT_MEMBERS = hex"f86994548e6acce441866674e04ab84587af2d394034c094bb06d463bc143eecc4a0cfa35e0346d5690fa9f694e2fe60f349c6e1a85caad1d22200c289da40dc1294b198db68258f06e79d415a0998be7f9b38ea722694dd173b85f306128f1b10d7d7219059c28c6d6c09";

    function developmentInit() external {
        votingPeriod = 20;
        address[2] memory initMembers = [
            address(0x9fB29AAc15b9A4B7F17c3385939b007540f4d791),
            address(0x96C42C56fdb78294F96B0cFa33c92bed7D75F96a)
        ];
        delete memberSet;
        for (uint256 i = 0; i < initMembers.length; i++) {
            memberSet.push(initMembers[i]);
            members[initMembers[i]] = memberSet.length;
        }
    }

    function resetMembers(address[] calldata newMembers) external {
        delete memberSet;
        for (uint256 i = 0; i < newMembers.length; i++) {
            memberSet.push(newMembers[i]);
            members[newMembers[i]] = memberSet.length;
        }
    }

    function _votingPeriod() internal override pure returns (uint256) {
        return MOCK_VOTING_PERIOD;
    }

    function _executingPeriod() internal override pure returns (uint256) {
        return MOCK_EXECUTING_PERIOD;
    }

    function _initMembers() internal override pure returns (bytes memory) {
        return MOCK_INIT_MEMBERS;
    }

    function _isValidMember() internal override pure returns (bool) {
        return true;
    }

    function _isProposer(uint256 proposalId) internal override pure returns (bool) {
        (proposalId);
        return true; // disable proposer check for mocks
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

