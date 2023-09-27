// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {ImmutableOwner} from "../utils/ImmutableOwner.sol";
import {SetOnce} from "../utils/SetOnce.sol";
import {AllContracts} from "./AllContracts.sol";

import {IValidatorSet} from "../interface/IValidatorSet.sol";
import {ICandidateHub} from "../interface/ICandidateHub.sol";
import {ILightClient} from "../interface/ILightClient.sol";
import {ISystemReward} from "../interface/ISystemReward.sol";
import {ISlashIndicator} from "../interface/ISlashIndicator.sol";
import {IRelayerHub} from "../interface/IRelayerHub.sol";
import {IBurn} from "../interface/IBurn.sol";
import {IPledgeAgent} from "../interface/IPledgeAgent.sol";

contract Registry is ImmutableOwner, SetOnce {
    
    AllContracts public s_allContracts;

    function setAll(AllContracts memory allContracts) external setOnlyOnce onlyOwner {
        s_allContracts = allContracts;
    }

    function validatorSet() external view returns(IValidatorSet) {
        IValidatorSet _validatorSet = s_allContracts.validatorSet;
        assert(address(_validatorSet) != address(0));
        return _validatorSet;
    }  

    function slashIndicator() external view returns(ISlashIndicator) {
        ISlashIndicator _slashIndicator = s_allContracts.slashIndicator;
        assert(address(_slashIndicator) != address(0));
        return _slashIndicator;
    }  

   function systemReward() external view returns(ISystemReward) {
        ISystemReward _systemReward = s_allContracts.systemReward;
        assert(address(_systemReward) != address(0));
        return _systemReward;
    }  

   function systemRewardPayable() external view returns(address payable) {
        ISystemReward _systemReward = s_allContracts.systemReward;
        assert(address(_systemReward) != address(0));
        return payable(address(_systemReward));
    }  

    function lightClient() external view returns(ILightClient) {
        ILightClient _lightClient = s_allContracts.lightClient;
        assert(address(_lightClient) != address(0));
        return _lightClient;
    }  
    
    function relayerHub() external view returns(IRelayerHub) {
        IRelayerHub _relayerHub = s_allContracts.relayerHub;
        assert(address(_relayerHub) != address(0));
        return _relayerHub;
    }

    function candidateHub() external view returns(ICandidateHub) {
        ICandidateHub _candidateHub = s_allContracts.candidateHub;
        assert(address(_candidateHub) != address(0));
        return _candidateHub;
    }  

   function pledgeAgent() external view returns(IPledgeAgent) {
        IPledgeAgent _pledgeAgent = s_allContracts.pledgeAgent;
        assert(address(_pledgeAgent) != address(0));
        return _pledgeAgent;
    }

    function burnContract() external view returns(IBurn) {
        IBurn _burn = s_allContracts.burn;
        assert(address(_burn) != address(0));
        return _burn;
    }

    function govHubAddr() external view returns(address) {
        address _govHubAddr = s_allContracts.govHubAddr;
        assert(_govHubAddr != address(0));
        return _govHubAddr;
    }

    function foundationPayable() external view returns(address payable) {
        address _foundationAddr = s_allContracts.foundationAddr;
        assert(_foundationAddr != address(0));
        return payable(_foundationAddr);
    }
}

