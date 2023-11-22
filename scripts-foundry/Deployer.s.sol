// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";

import {BtcLightClient} from "../contracts/BtcLightClient.sol";
import {System} from "../contracts/System.sol";
import {Burn} from "../contracts/Burn.sol";
import {CandidateHub} from "../contracts/CandidateHub.sol";
import {Foundation} from "../contracts/Foundation.sol";
import {GovHub} from "../contracts/GovHub.sol";
import {PledgeAgent} from "../contracts/PledgeAgent.sol";
import {RelayerHub} from "../contracts/RelayerHub.sol";
import {SlashIndicator} from "../contracts/SlashIndicator.sol";
import {ValidatorSet} from "../contracts/ValidatorSet.sol";
import {SystemRewardMock} from "../contracts/mock/SystemRewardMock.sol";


contract Deployer is Script, System {
    address public validatorSetAddr;
    address public slashAddr ;
    address public systemRewardAddr;
    address public lightAddr;
    address public relayerHubAddr;
    address public candidateHubAddr;
    address public govHubAddr ;
    address public pledgeAgentAddr;
    address public burnAddr ;
    address public foundationAddr;

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
        if (_isLocalTestNode()) {
            _performActualDeployment();
        } else {
            // rely on the already deployed contracts
        }
        // vm.stopBroadcast();
    }

    function _performActualDeployment() private {        
        console.log("deploying on network %s", block.chainid);
        
        burn = new Burn();                                
        lightClient = new BtcLightClient();        
        slashIndicator = new SlashIndicator();  
        systemReward = new SystemRewardMock(); // must use mock else onlyOperator() will fail        
        candidateHub = new CandidateHub();        
        pledgeAgent = new PledgeAgent();           
        validatorSet = new ValidatorSet();        
        relayerHub = new RelayerHub();              
        foundation = new Foundation();               
        govHub = new GovHub();                           

        validatorSetAddr = address(validatorSet);
        slashAddr = address(slashIndicator);
        systemRewardAddr = address(systemReward);
        lightAddr = address(lightClient);
        relayerHubAddr = address(relayerHub);
        candidateHubAddr = address(candidateHub);
        govHubAddr = address(govHub);
        pledgeAgentAddr = address(pledgeAgent);
        burnAddr = address(burn);
        foundationAddr = address(foundation);

        // update contracts in local-node testing mode:
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

        // and call init() after setting of addresses
        burn.init();
        lightClient.init();
        slashIndicator.init();
        systemReward.init();      
        candidateHub.init();
        pledgeAgent.init();
        validatorSet.init();
        relayerHub.init();
        //foundation.init(); -- non existent 
        govHub.init();
    }
}