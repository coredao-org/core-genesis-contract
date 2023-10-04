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

    function setAll(AllContracts memory allContracts) external onlyOwner setOnlyOnce { 
        //@correlate-registry.cache: allow registry caching of each contract only if setAll may be called only once
        _verifyAll(allContracts);
        s_allContracts = allContracts;
    }

    function getAllContracts() external view returns (AllContracts memory) {
        assert(s_allContracts.burn != IBurn(address(0))); // make sure setAll() was called
        return s_allContracts;
    }

    function govHubAddr() external view returns (address) {
        address gotHub = s_allContracts.govHubAddr;
        assert(gotHub != address(0)); // make sure setAll() was called
        return gotHub;
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
}
