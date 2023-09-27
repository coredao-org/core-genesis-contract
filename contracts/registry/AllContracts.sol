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

