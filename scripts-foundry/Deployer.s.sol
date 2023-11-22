// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Script} from "forge-std/Script.sol";
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
import {ValidatorSet} from "../contracts/ValidatorSet.sol";
import {SystemRewardMock} from "../contracts/mock/SystemRewardMock.sol";


contract Deployer is System, Script {

    uint public constant ANVIL_CHAINID = 31337;
    uint public constant GANACHE_CHAINID = 1337;

    // @dev declared as state-varible to circumvent stack-too-deep error
    Burn private burn; 
    BtcLightClient private lightClient;
    SlashIndicator private slashIndicator;
    SystemRewardMock private systemReward;
    CandidateHub private candidateHub;
    PledgeAgent private pledgeAgent;
    ValidatorSet private validatorSet;
    RelayerHub private relayerHub;
    Foundation private foundation;
    GovHub private govHub;

    function run() external {
	    // vm.startBroadcast(); 
        if (_isLocalTestnet()) {
            _performActualDeployment();
        } else {
            // rely on the already deployed contracts
        }
        // vm.stopBroadcast();
    }

    function _performActualDeployment() private {        
        console.log("deploying on network %s", block.chainid);
        
        burn = new Burn();                                
        burn.init();
        lightClient = new BtcLightClient();        
        lightClient.init();
        slashIndicator = new SlashIndicator();  
        slashIndicator.init();
        systemReward = new SystemRewardMock(); // must use mock else onlyOperator() will fail        
        systemReward.init();      
        candidateHub = new CandidateHub();        
        candidateHub.init();
        pledgeAgent = new PledgeAgent();           
        pledgeAgent.init();
        validatorSet = new ValidatorSet();        
        validatorSet.init();
        relayerHub = new RelayerHub();              
        relayerHub.init();
        foundation = new Foundation();               
        //foundation.init(); -- non existent 
        govHub = new GovHub();                           
        govHub.init();

        address validatorSetAddr = address(validatorSet);
        address slashAddr = address(slashIndicator);
        address systemRewardAddr = address(systemReward);
        address lightAddr = address(lightClient);
        address relayerHubAddr = address(relayerHub);
        address candidateHubAddr = address(candidateHub);
        address govHubAddr = address(govHub);
        address pledgeAgentAddr = address(pledgeAgent);
        address burnAddr = address(burn);
        address foundationAddr = address(foundation);

        burn.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        lightClient.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        slashIndicator.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        systemReward.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        candidateHub.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        pledgeAgent.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        validatorSet.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        relayerHub.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        foundation.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);
        govHub.updateContractAddr(validatorSetAddr, slashAddr, systemRewardAddr, lightAddr, relayerHubAddr,
                                candidateHubAddr, govHubAddr, pledgeAgentAddr, burnAddr, foundationAddr);

        // to be used by tests
        VALIDATOR_CONTRACT_ADDR = validatorSetAddr;
        SLASH_CONTRACT_ADDR = slashAddr;
        SYSTEM_REWARD_ADDR = systemRewardAddr;
        LIGHT_CLIENT_ADDR = lightAddr;
        RELAYER_HUB_ADDR = relayerHubAddr;
        CANDIDATE_HUB_ADDR = candidateHubAddr;
        GOV_HUB_ADDR = govHubAddr;
        PLEDGE_AGENT_ADDR = pledgeAgentAddr;
        BURN_ADDR = burnAddr;
        FOUNDATION_ADDR = foundationAddr;
    }

    function _isLocalTestnet() private view returns(bool) {
        return block.chainid == ANVIL_CHAINID || block.chainid == GANACHE_CHAINID; // add more local testnet ids if needed
    }
}