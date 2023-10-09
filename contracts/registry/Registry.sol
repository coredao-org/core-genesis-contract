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
    
    AllContracts private s_allContracts;
    mapping(address => bool) private s_contractMap;

    function setAll(AllContracts memory allContracts) external onlyOwner setOnlyOnce { 
        //@correlate-registry.cache: allow registry caching of each contract only if setAll may be called only once
        _verifyAll(allContracts);
        _populateMap(allContracts);
        s_allContracts = allContracts;
    }

    function onlyPlatformContracts(address[] memory targets) external view returns(bool) {    
        assert(_setAllWasCalled()); 
        uint len = targets.length;
        for (uint i = 0; i < len; i++) {
            if (!s_contractMap[targets[i]]) {
                return false; // not a platform contract
            }
        }
        return true;
    }


    function getAllContracts() external view returns (AllContracts memory) {
        assert(_setAllWasCalled()); 
        return s_allContracts;
    }

    function govHubAddr() external view returns (address) {
        address govHub = s_allContracts.govHubAddr;
        assert(govHub != address(0));
        return govHub;
    }

    function _verifyAll(AllContracts memory allContracts) private pure {
        assert(allContracts.burn != IBurn(address(0)));
        assert(allContracts.lightClient != ILightClient(address(0)));
        assert(allContracts.slashIndicator != ISlashIndicator(address(0)));
        assert(allContracts.systemReward != ISystemReward(address(0)));
        assert(allContracts.candidateHub != ICandidateHub(address(0)));
        assert(allContracts.pledgeAgent != IPledgeAgent(address(0)));
        assert(allContracts.validatorSet != IValidatorSet(address(0)));
        assert(allContracts.relayerHub != IRelayerHub(address(0)));
        assert(allContracts.foundationAddr != address(0));
        assert(allContracts.govHubAddr != address(0));
    }

    function _populateMap(AllContracts memory allContracts) private {
        //@correlate-registry.cache: if allContracts can be set morethan once - old contractMap should be cleared!
        s_contractMap[address(allContracts.burn)] = true;
        s_contractMap[address(allContracts.lightClient)] = true;
        s_contractMap[address(allContracts.slashIndicator)] = true;
        s_contractMap[address(allContracts.systemReward)] = true;
        s_contractMap[address(allContracts.candidateHub)] = true;
        s_contractMap[address(allContracts.pledgeAgent)] = true;
        s_contractMap[address(allContracts.validatorSet)] = true;
        s_contractMap[address(allContracts.relayerHub)] = true;
        s_contractMap[allContracts.foundationAddr] = true;
        s_contractMap[allContracts.govHubAddr] = true;
    }

    function _setAllWasCalled() private view returns(bool) {
        return s_allContracts.burn != IBurn(address(0)); // or any other platform contract
    }
}

