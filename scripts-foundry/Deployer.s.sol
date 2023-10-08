// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/Script.sol";

import {ContractAddresses} from "../contracts/ContractAddresses.sol";
import {AllContracts} from "../contracts/AllContracts.sol";
import {Registry} from "../contracts/Registry.sol";

import {IBurn} from "../contracts/interface/IBurn.sol";
import {ICandidateHub} from "../contracts/interface/ICandidateHub.sol";
import {ILightClient} from "../contracts/interface/ILightClient.sol";
import {IPledgeAgent} from "../contracts/interface/IPledgeAgent.sol";
import {IRelayerHub} from "../contracts/interface/IRelayerHub.sol";
import {ISlashIndicator} from "../contracts/interface/ISlashIndicator.sol";
import {ISystemReward} from "../contracts/interface/ISystemReward.sol";
import {IValidatorSet} from "../contracts/interface/IValidatorSet.sol";

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


contract Deployer is Script, ContractAddresses {

    uint public constant ANVIL_CHAINID = 31337;
    uint public constant GANACHE_CHAINID = 1337;

    function run() external returns(AllContracts memory s_allContracts) {
        console.log("Deploying contracts to chainid: ", block.chainid);

        bool isLocalTestnet = block.chainid == ANVIL_CHAINID || block.chainid == GANACHE_CHAINID;
        
	    // vm.startBroadcast(); 
        if (isLocalTestnet) {
            s_allContracts = deployOnLocalTestnet();            
        } else {
            s_allContracts = returnPredeployedContracts();
        }
        // vm.stopBroadcast();
    }

    function deployOnLocalTestnet() private returns(AllContracts memory) {
        
        Registry registry = new Registry();

        IBurn burn = new Burn(registry);
        ILightClient lightClient = new BtcLightClient(registry);
        ISlashIndicator slashIndicator = new SlashIndicator(registry);
        ISystemReward systemReward = new SystemReward(registry, address(lightClient), address(slashIndicator));
        
        ICandidateHub candidateHub = new CandidateHub(registry);
        IPledgeAgent pledgeAgent = new PledgeAgent(registry);    
        IValidatorSet validatorSet = new ValidatorSet(registry);
        IRelayerHub relayerHub = new RelayerHub(registry);
        address foundationAddr = address(new Foundation(registry));
        address govHubAddr = address(new GovHub(registry));

        AllContracts memory s_allContracts = AllContracts({
            burn: burn,
            lightClient: lightClient,
            slashIndicator: slashIndicator,
            systemReward: systemReward,
            candidateHub: candidateHub,
            pledgeAgent: pledgeAgent,      
            validatorSet: validatorSet,
            relayerHub: relayerHub,
            foundationAddr: foundationAddr,
            govHubAddr: govHubAddr
        });

        registry.setAll(s_allContracts);

        return s_allContracts;
    }

    function returnPredeployedContracts() private pure returns(AllContracts memory) {      
        return AllContracts({
            burn: IBurn(BURN_ADDR),
            lightClient: ILightClient(LIGHT_CLIENT_ADDR),
            slashIndicator: ISlashIndicator(SLASH_CONTRACT_ADDR),
            systemReward: ISystemReward(SYSTEM_REWARD_ADDR),
            candidateHub: ICandidateHub(CANDIDATE_HUB_ADDR),
            pledgeAgent: IPledgeAgent(PLEDGE_AGENT_ADDR),     
            validatorSet: IValidatorSet(VALIDATOR_CONTRACT_ADDR),
            relayerHub: IRelayerHub(RELAYER_HUB_ADDR),
            foundationAddr: FOUNDATION_ADDR,
            govHubAddr: GOV_HUB_ADDR 
        });
    }
}