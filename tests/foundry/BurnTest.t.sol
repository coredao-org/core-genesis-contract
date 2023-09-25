// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/console.sol";

import {Test} from "forge-std/Test.sol";
import {Deployer} from "../../scripts-foundry/Deployer.s.sol";

import {System} from "../../contracts/System.sol";
import {AllContracts} from "../../contracts/AllContracts.sol";
import {IBurn} from "../../contracts/interface/IBurn.sol";
import {Burn} from "../../contracts/Burn.sol";
import {ContractAddresses} from "../../contracts/ContractAddresses.sol";
import {ICandidateHub} from "../../contracts/interface/ICandidateHub.sol";
import {ILightClient} from "../../contracts/interface/ILightClient.sol";
import {IPledgeAgent} from "../../contracts/interface/IPledgeAgent.sol";
import {IRelayerHub} from "../../contracts/interface/IRelayerHub.sol";
import {ISlashIndicator} from "../../contracts/interface/ISlashIndicator.sol";
import {ISystemReward} from "../../contracts/interface/ISystemReward.sol";
import {IValidatorSet} from "../../contracts/interface/IValidatorSet.sol";

contract BurnTest is Test  {

    string constant private ONLY_GOV_ALLOWED_MSG = "the msg sender must be governance contract";
    string constant private BAD_PARAM_ERROR_MSG = "unknown param";
    string constant private BURN_CAP_KEY = "burnCap";

    Burn private burn;
    Deployer private deployer;
    AllContracts private allContracts;

	function setUp() public {
	    deployer = new Deployer();
		allContracts = deployer.run();
        burn = Burn(address(allContracts.burn));
	}

    receive() external payable {} // else Burn.burn() will fail on transfering remaining funds back to the caller


    // --- burn() tests ---

    function testFuzz_burn_with_value_variations(uint value) public {
        limitFunds(value);
        console.log("value: %d, burnCap: %d , orig balance: %d", value, burn.burnCap(), address(burn).balance);
        burn.burn{value: value}();
    }

    function testFuzz_burn_with_value_and_balance_variations(uint value, uint addedBalance) public {
        limitFunds(value);
        limitFunds(addedBalance); 
        vm.deal(address(burn), addedBalance);
        burn.burn{value: value}();
    }

    function testFuzz_burn_with_value_balance_and_cap_variations(uint value, uint addedBalance, uint burnCap) public {
        limitFunds(value);
        limitFunds(addedBalance); 
        limitFunds(burnCap); 

        updateBurnCap(burnCap);        

        vm.deal(address(burn), addedBalance);
        burn.burn{value: value}();
    }


    // --- updateParam() tests ---

    function test_verify_nonGov_cannot_updateParams() public {
        uint legalBurnCapValue = address(burn).balance + 1;
        vm.prank(makeAddr("Joe"));
        vm.expectRevert(abi.encodePacked(ONLY_GOV_ALLOWED_MSG));
        burn.updateParam(BURN_CAP_KEY, abi.encodePacked(legalBurnCapValue));
    }

    function testFuzz_updateParams_success_scenario(uint newBurnCap,uint addedBalance) public {
        vm.deal(address(burn), addedBalance);
        vm.assume( newBurnCap >= address(burn).balance); 

        updateBurnCap(newBurnCap);        

        assertEq(newBurnCap, burn.burnCap());
    }

    function testFuzz_updateParams_bad_paramName(string memory paramName, uint addedBalance) public {
        limitFunds(addedBalance); 
        uint origBurnCap = burn.burnCap();
        vm.deal(address(burn), addedBalance);                
        vm.prank(allContracts.govHubAddr);

        uint legalBurnCapValue = address(burn).balance + 1;

        vm.expectRevert(abi.encodePacked(BAD_PARAM_ERROR_MSG));
        burn.updateParam(paramName, abi.encodePacked(legalBurnCapValue));

        assertEq(origBurnCap, burn.burnCap());
    }

    function testFuzz_updateParams_with_bad_burnBap(uint newBurnCap, uint addedBalance) public {
        limitFunds(addedBalance); 
        vm.deal(address(burn), addedBalance);

        uint origBurnCap = burn.burnCap();
        uint origBalance = address(burn).balance;

        vm.assume( newBurnCap < address(burn).balance); // should result in OutOfBounds error
        
        vm.expectRevert(
            abi.encodeWithSelector(System.OutOfBounds.selector, BURN_CAP_KEY, newBurnCap, origBalance, type(uint256).max)
        );
        updateBurnCap(newBurnCap);

        assertEq(origBurnCap, burn.burnCap());
    }



    function limitFunds(uint value) private pure {
        vm.assume( value < 1_000_000 ether); // avoid "EvmError: OutOfFund"
    }

    function updateBurnCap(uint newBurnCap) private {
        vm.prank(allContracts.govHubAddr);
        burn.updateParam(BURN_CAP_KEY, abi.encodePacked(newBurnCap));
    }
}		