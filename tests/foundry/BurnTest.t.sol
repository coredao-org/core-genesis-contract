// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Test} from "forge-std/Test.sol";
import {Deployer} from "../../scripts-foundry/Deployer.sol";

import {IBurn} from "../contracts/interface/IBurn.sol";
import {ContractAddresses} from "../contracts/ContractAddresses.sol";
import {ICandidateHub} from "../contracts/interface/ICandidateHub.sol";
import {ILightClient} from "../contracts/interface/ILightClient.sol";
import {IPledgeAgent} from "../contracts/interface/IPledgeAgent.sol";
import {IRelayerHub} from "../contracts/interface/IRelayerHub.sol";
import {ISlashIndicator} from "../contracts/interface/ISlashIndicator.sol";
import {ISystemReward} from "../contracts/interface/ISystemReward.sol";
import {IValidatorSet} from "../contracts/interface/IValidatorSet.sol";

contract BurnTest is Test  {
    Burn public burn;
    Deployer private deployer;

	function setUp() public {
	    deployer = new Deployer();
		allDeployedContracts = deployer.run()
	}


}		