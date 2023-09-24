// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/Script.sol";

import {IBurn} from "../contracts/interface/IBurn.sol";
import {ICandidateHub} from "../contracts/interface/ICandidateHub.sol";
import {ILightClient} from "../contracts/interface/ILightClient.sol";
import {IPledgeAgent} from "../contracts/interface/IPledgeAgent.sol";
import {IRelayerHub} from "../contracts/interface/IRelayerHub.sol";
import {ISlashIndicator} from "../contracts/interface/ISlashIndicator.sol";
import {ISystemReward} from "../contracts/interface/ISystemReward.sol";
import {IValidatorSet} from "../contracts/interface/IValidatorSet.sol";

import {Registry} from "../contracts/Registry.sol";
import {BtcLightClient} from "../contracts/BtcLightClient.sol";
import {Burn} from "../contracts/Burn.sol";
import {CandidateHub} from "../contracts/CandidateHub.sol";
import {Foundation} from "../contracts/Foundation.sol";
import {GovHub} from "../contracts/GovHub.sol";
import {PledgeAgent} from "../contracts/PledgeAgent.sol";
import {RelayerHub} from "../contracts/RelayerHub.sol";
import {SlashIndicator} from "../contracts/SlashIndicator.sol";
import {SystemReward} from "../contracts/SystemReward.sol";
import {ValidatorSet} from "../contracts/ValidatorSet.sol";


contract Deployer is Script {

    uint public constant ANVIL_CHAINID = 31337;
    
    address public constant VALIDATOR_CONTRACT_ADDR = 0x0000000000000000000000000000000000001000;
    address public constant SLASH_CONTRACT_ADDR = 0x0000000000000000000000000000000000001001;
    address public constant SYSTEM_REWARD_ADDR = 0x0000000000000000000000000000000000001002;
    address public constant LIGHT_CLIENT_ADDR = 0x0000000000000000000000000000000000001003;
    address public constant RELAYER_HUB_ADDR = 0x0000000000000000000000000000000000001004;
    address public constant CANDIDATE_HUB_ADDR = 0x0000000000000000000000000000000000001005;
    address public constant GOV_HUB_ADDR = 0x0000000000000000000000000000000000001006;
    address public constant PLEDGE_AGENT_ADDR = 0x0000000000000000000000000000000000001007;
    address public constant BURN_ADDR = 0x0000000000000000000000000000000000001008;
    address public constant FOUNDATION_ADDR = 0x0000000000000000000000000000000000001009;

    IBurn private burn;
    IBtcLightClient private lightClient;
    ISlashIndicator private slashIndicator;
    ISystemReward private systemReward;
    ICandidateHub private candidateHub;
    IPledgeAgent private pledgeAgent;        
    IValidatorSet private validatorSet;
    IRelayerHub private relayerHub;
    address private foundationAddr;
    address private govHubAddr;

    function run() external {
	    // vm.startBroadcast(); // everything in this block sent via rpc to blockchain

        Registry registry = new Registry();

        if (block.chainid == ANVIL_CHAINID) {
            deployToLocalTestnet(registry);
        } else {
            connectToPredeployedContracts();
        }

        registry.setAll(
                    validatorSet, 
                    slashIndicator,
                    systemReward,
                    lightClient,
                    relayerHub,
                    candidateHub,
                    pledgeAgent,                                         
                    burn,
                    address(govHub),
                    address(foundation)
        );
        // vm.stopBroadcast();
    }

    function deployToLocalTestnet(Registry registry) private {
        burn = new Burn(registry);
        lightClient = new BtcLightClient(registry);
        slashIndicator = new SlashIndicator(registry);
        systemReward = new SystemReward(registry, address(lightClient), address(slashIndicator));
        candidateHub = new CandidateHub(registry);
        pledgeAgent = new PledgeAgent(registry);        
        validatorSet = new ValidatorSet(registry);
        relayerHub = new RelayerHub(registry);
        foundationAddr = address(new Foundation(registry));
        govHubAddr = address(new GovHub(registry));        
    }

    function connectToPredeployedContracts() private {       
        burn = IBurn(BURN_ADDR);
        lightClient = ILightClient(LIGHT_CLIENT_ADDR);
        slashIndicator = ISlashIndicator(SLASH_CONTRACT_ADDR);
        systemReward = ISystemReward(SYSTEM_REWARD_ADDR);
        candidateHub = ICandidateHub(CANDIDATE_HUB_ADDR);
        pledgeAgent = IPledgeAgent(PLEDGE_AGENT_ADDR);        
        validatorSet = IValidatorSet(VALIDATOR_CONTRACT_ADDR);
        relayerHub = IRelayerHub(RELAYER_HUB_ADDR);
        foundationAddr = FOUNDATION_ADDR;
        govHubAddr = GOV_HUB_ADDR;        
    }
}