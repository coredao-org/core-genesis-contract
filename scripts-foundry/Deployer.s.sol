// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/Script.sol";
import {console} from "forge-std/console.sol";

import {System} from "../contracts/System.sol";
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


contract Deployer is System, Script {

    uint public constant ANVIL_CHAINID = 31337;
    uint public constant GANACHE_CHAINID = 1337;

    function run() external returns(ContractAddresses memory addresses) {
	    // vm.startBroadcast(); 
        if (_isLocalTestnet()) {
            addresses = _deployOnLocalTestnet();            
        } else {
            addresses = _returnPredeployedContracts();
        }
        require(_allAddressesWereSet(addresses), "failed to deploy all contracts");
        // vm.stopBroadcast();
    }

    function _deployOnLocalTestnet() private returns(ContractAddresses memory) {        
        console.log("deploying on local testnet %s", block.chainid);
        Burn burn = new Burn();                                
        burn.init();
        BtcLightClient lightClient = new BtcLightClient();        
        lightClient.init();
        SlashIndicator slashIndicator = new SlashIndicator();  
        slashIndicator.init();
        SystemReward systemReward = new SystemReward();        
        systemReward.init();      
        CandidateHub candidateHub = new CandidateHub();        
        candidateHub.init();
        PledgeAgent pledgeAgent = new PledgeAgent();           
        pledgeAgent.init();
        ValidatorSet validatorSet = new ValidatorSet();        
        validatorSet.init();
        RelayerHub relayerHub = new RelayerHub();              
        relayerHub.init();
        Foundation foundation = new Foundation();               
        //foundation.init(); -- nope
        GovHub govHub = new GovHub();                           
        govHub.init();

        return System.ContractAddresses({
            burn: address(burn),
            lightClient: address(lightClient),
            slashIndicator: address(slashIndicator),
            systemReward: address(systemReward),
            candidateHub: address(candidateHub),
            pledgeAgent: address(pledgeAgent),      
            validatorSet: address(validatorSet),
            relayerHub: address(relayerHub),
            foundation: address(foundation),
            govHub: address(govHub)
        });
    }

    function _returnPredeployedContracts() private view returns(ContractAddresses memory) {      
        console.log("using pre-deployed contracts on Core network %s", block.chainid);
        return System.ContractAddresses({
            burn: BURN_ADDR,
            lightClient: LIGHT_CLIENT_ADDR,
            slashIndicator: SLASH_CONTRACT_ADDR,
            systemReward: SYSTEM_REWARD_ADDR,
            candidateHub: CANDIDATE_HUB_ADDR,
            pledgeAgent: PLEDGE_AGENT_ADDR,     
            validatorSet: VALIDATOR_CONTRACT_ADDR,
            relayerHub: RELAYER_HUB_ADDR,
            foundation: FOUNDATION_ADDR,
            govHub: GOV_HUB_ADDR 
        });
    }

    function _isLocalTestnet() private view returns(bool) {
        return block.chainid == ANVIL_CHAINID || block.chainid == GANACHE_CHAINID; // add more local testnet ids if needed
    }
}