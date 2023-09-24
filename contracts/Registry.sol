// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {ImmutableOwner} from "./utils/ImmutableOwner.sol";
import {SetOnce} from "./utils/SetOnce.sol";

import {IValidatorSet} from "./interface/IValidatorSet.sol";
import {ICandidateHub} from "./interface/ICandidateHub.sol";
import {ILightClient} from "./interface/ILightClient.sol";
import {ISystemReward} from "./interface/ISystemReward.sol";
import {ISlashIndicator} from "./interface/ISlashIndicator.sol";
import {IRelayerHub} from "./interface/IRelayerHub.sol";
import {IBurn} from "./interface/IBurn.sol";
import {IPledgeAgent} from "./interface/IPledgeAgent.sol";

contract Registry is ImmutableOwner, SetOnce {
    
    IValidatorSet private s_validatorSet; 
    ISlashIndicator private s_slashIndicator;
    ISystemReward private s_systemReward;
    ILightClient private s_lightClient;
    IRelayerHub private s_relayerHub;
    ICandidateHub private s_candidateHub;
    IPledgeAgent private s_pledgeAgent;
    IBurn private s_burn;
    address private s_govHubAddr;
    address private s_foundationAddr;

    function setAll(
                 IValidatorSet _validatorSet, 
                 ISlashIndicator _slashIndicator,
                 ISystemReward _systemReward,
                 ILightClient _lightClient,
                 IRelayerHub _relayerHub,
                 ICandidateHub _candidateHub,
                 IPledgeAgent _pledgeAgent,                                         
                 IBurn _burn,
                 address _govHubAddr,
                 address _foundationAddr
                 ) external setOnlyOnce onlyOwner {
        s_validatorSet = _validatorSet; 
        s_slashIndicator = _slashIndicator;
        s_systemReward = _systemReward;
        s_lightClient = _lightClient;
        s_relayerHub = _relayerHub;
        s_candidateHub = _candidateHub;
        s_pledgeAgent = _pledgeAgent;       
        s_burn = _burn;
        s_govHubAddr = _govHubAddr;
        s_foundationAddr = _foundationAddr;
        markAsSet(); // avoid double-setting            
    }

    function validatorSet() external view returns(IValidatorSet) {
        IValidatorSet _validatorSet = s_validatorSet;
        assert(address(_validatorSet) != address(0));
        return _validatorSet;
    }  

    function slashIndicator() external view returns(ISlashIndicator) {
        ISlashIndicator _slashIndicator = s_slashIndicator;
        assert(address(_slashIndicator) != address(0));
        return _slashIndicator;
    }  

   function systemReward() external view returns(ISystemReward) {
        ISystemReward _systemReward = s_systemReward;
        assert(address(_systemReward) != address(0));
        return _systemReward;
    }  

   function systemRewardPayable() external view returns(address payable) {
        ISystemReward _systemReward = s_systemReward;
        assert(address(_systemReward) != address(0));
        return payable(address(_systemReward));
    }  

    function lightClient() external view returns(ILightClient) {
        ILightClient _lightClient = s_lightClient;
        assert(address(_lightClient) != address(0));
        return _lightClient;
    }  
    
    function relayerHub() external view returns(IRelayerHub) {
        IRelayerHub _relayerHub = s_relayerHub;
        assert(address(_relayerHub) != address(0));
        return _relayerHub;
    }

    function candidateHub() external view returns(ICandidateHub) {
        ICandidateHub _candidateHub = s_candidateHub;
        assert(address(_candidateHub) != address(0));
        return _candidateHub;
    }  

   function pledgeAgent() external view returns(IPledgeAgent) {
        IPledgeAgent _pledgeAgent = s_pledgeAgent;
        assert(address(_pledgeAgent) != address(0));
        return _pledgeAgent;
    }

    function burnContract() external view returns(IBurn) {
        IBurn _burn = s_burn;
        assert(address(_burn) != address(0));
        return _burn;
    }

    function govHubAddr() external view returns(address) {
        address _govHubAddr = s_govHubAddr;
        assert(_govHubAddr != address(0));
        return _govHubAddr;
    }

    function foundationPayable() external view returns(address payable) {
        address _foundationAddr = s_foundationAddr;
        assert(_foundationAddr != address(0));
        return payable(_foundationAddr);
    }
}