// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {IValidatorSet} from "../interface/IValidatorSet.sol";
import {ICandidateHub} from "../interface/ICandidateHub.sol";
import {ILightClient} from "../interface/ILightClient.sol";
import {ISystemReward} from "../interface/ISystemReward.sol";
import {ISlashIndicator} from "../interface/ISlashIndicator.sol";
import {IRelayerHub} from "../interface/IRelayerHub.sol";
import {IBurn} from "../interface/IBurn.sol";
import {IPledgeAgent} from "../interface/IPledgeAgent.sol";

struct AllContracts {
    IBurn burn;
    ILightClient lightClient;
    ISlashIndicator slashIndicator;
    ISystemReward systemReward;
    ICandidateHub candidateHub;
    IPledgeAgent pledgeAgent;        
    IValidatorSet validatorSet;
    IRelayerHub relayerHub;
    address foundationAddr;
    address govHubAddr;
}

function _verifyLocalNodeAddresses(AllContracts memory allContracts) private pure {
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

//zzz call it
function _populateMap(mapping(address => bool) storage contractsMap, AllContracts memory allContracts) private {
    //@correlate-registry.cache: if allContracts can be set morethan once - old contractMap should be cleared!
    contractsMap[address(allContracts.burn)] = true;
    contractsMap[address(allContracts.lightClient)] = true;
    contractsMap[address(allContracts.slashIndicator)] = true;
    contractsMap[address(allContracts.systemReward)] = true;
    contractsMap[address(allContracts.candidateHub)] = true;
    contractsMap[address(allContracts.pledgeAgent)] = true;
    contractsMap[address(allContracts.validatorSet)] = true;
    contractsMap[address(allContracts.relayerHub)] = true;
    contractsMap[allContracts.foundationAddr] = true;
    contractsMap[allContracts.govHubAddr] = true;
}