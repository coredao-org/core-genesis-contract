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
        //@correlate-regcache: allow registry caching of each contract only if setAll may be called only once
        verifyAll_(allContracts);
        s_allContracts = allContracts;
    }

    function getAllContracts() external view returns (AllContracts memory) {
        verifyAll_(s_allContracts);
        return s_allContracts;
    }

    function verifyAll_(AllContracts memory allContracts) private pure {
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

