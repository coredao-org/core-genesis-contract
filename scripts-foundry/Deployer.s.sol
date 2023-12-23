// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";

import {System} from "../contracts/System.sol";
import {BurnMock} from "../contracts/mock/BurnMock.sol";
import {BtcLightClientMock} from "../contracts/mock/BtcLightClientMock.sol";
import {SlashIndicatorMock} from "../contracts/mock/SlashIndicatorMock.sol";
import {SystemRewardMock} from "../contracts/mock/SystemRewardMock.sol";
import {CandidateHubMock} from "../contracts/mock/CandidateHubMock.sol";
import {PledgeAgentMock} from "../contracts/mock/PledgeAgentMock.sol";
import {ValidatorSetMock} from "../contracts/mock/ValidatorSetMock.sol";
import {RelayerHubMock} from "../contracts/mock/RelayerHubMock.sol";
import {FoundationMock} from "../contracts/mock/FoundationMock.sol";
import {GovHubMock} from "../contracts/mock/GovHubMock.sol";


contract Deployer is Script, System {

    uint public constant CORE_MAINNET = 1116;
    uint public constant CORE_TESTNET = 1115;
    uint public constant ANVIL_CHAINID = 31337;
    uint public constant GANACHE_CHAINID = 1337;

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

    function run() external {
	    // vm.startBroadcast(); 
        if (_isLocalTestNode()) {
            _performActualDeployment();
        } else {
            // rely on the already deployed contracts
            _useAlreadyDeployedAddresses();
        }
        // vm.stopBroadcast();
    }

    function _performActualDeployment() private {        
        console.log("deploying on network %s", block.chainid);
        
        BurnMock burn = new BurnMock();
        BtcLightClientMock lightClient = new BtcLightClientMock();
        SlashIndicatorMock slashIndicator = new SlashIndicatorMock();
        SystemRewardMock systemReward = new SystemRewardMock(); 
        CandidateHubMock candidateHub = new CandidateHubMock();
        PledgeAgentMock pledgeAgent = new PledgeAgentMock();
        ValidatorSetMock validatorSet = new ValidatorSetMock();
        RelayerHubMock relayerHub = new RelayerHubMock();
        FoundationMock foundation = new FoundationMock();
        GovHubMock govHub = new GovHubMock();

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

    function _useAlreadyDeployedAddresses() private {        
        console.log("using pre-deployed contracts on network %s", block.chainid);
        
        validatorSetAddr = _VALIDATOR_CONTRACT_ADDR;
        slashAddr = _SLASH_CONTRACT_ADDR;
        systemRewardAddr = _SYSTEM_REWARD_ADDR;
        lightAddr = _LIGHT_CLIENT_ADDR;
        relayerHubAddr = _RELAYER_HUB_ADDR;
        candidateHubAddr = _CANDIDATE_HUB_ADDR;
        govHubAddr = _GOV_HUB_ADDR;
        pledgeAgentAddr = _PLEDGE_AGENT_ADDR;
        burnAddr = _BURN_ADDR;
        foundationAddr = _FOUNDATION_ADDR;
    }    

    function _isLocalTestNode() private view returns (bool) {
        return block.chainid != CORE_MAINNET && block.chainid != CORE_TESTNET;
    }
}