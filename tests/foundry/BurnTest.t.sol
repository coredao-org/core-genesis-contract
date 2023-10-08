// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/console.sol";

import {BaseTest} from "./common/BaseTest.sol";
import {AllContracts} from "../../contracts/AllContracts.sol";
import {System} from "../../contracts/System.sol";
import {Burn} from "../../contracts/Burn.sol";

contract BurnTest is BaseTest  {
    string constant private ONLY_GOV_ALLOWED_MSG = "the msg sender must be governance contract";
    string constant private BAD_PARAM_ERROR_MSG = "unknown param";
    string constant private BURN_CAP_KEY = "burnCap";

    Burn private s_burn;

    event burned(address indexed to, uint256 amount);

    constructor() BaseTest(ACCEPT_ETH) {} // accept eth else burn() will fail on transfering the remaining funds back to the caller

	function setUp() public override {
	    BaseTest.setUp();
        s_burn = Burn(address(s_allContracts.burn));
	}


    // --- burn() tests ---

    function testFuzz_burn_with_value_variations(uint value) public {
        value = _limitFunds(value);
        console.log("value: %d, burnCap: %d , orig balance: %d", value, s_burn.burnCap(), address(s_burn).balance);
        s_burn.burn{value: value}();
    }

    function testFuzz_burn_with_value_and_balance_variations(uint value, uint addedBalance) public {
        value = _limitFunds(value);
        addedBalance =_limitFunds(addedBalance);         
        vm.deal(address(s_burn), addedBalance);
        s_burn.burn{value: value}();
    }

    function testFuzz_burn_with_value_balance_and_cap_variations(uint value, uint addedBalance, uint burnCap) public {
        value = _limitFunds(value);
        addedBalance = _limitFunds(addedBalance); 
        burnCap = _limitFunds(burnCap); 

        _updateBurnCap(burnCap);        

        vm.deal(address(s_burn), addedBalance);
        s_burn.burn{value: value}();
    }

    function testFuzz_burn_with_balance_lesser_than_burnCap(uint value, uint burnCap) public {
        value = _limitFunds(value);
        burnCap = _limitFunds(burnCap); 

        if (burnCap < address(s_burn).balance) {
            // here we only test the burnCap >= balance scenario
            burnCap = address(s_burn).balance;
        }
        _updateBurnCap(burnCap);        

        assertTrue( burnCap >= address(s_burn).balance, "bad burnCap value");

        uint SOME_GAS_CONSUMPTION = 30_000;

        address sender = makeAddr("Joe");
        hoax(sender, value + SOME_GAS_CONSUMPTION);

        uint preSenderBalance = address(sender).balance;

        // if (value != 0) {
        //     vm.expectEmit();
        //     emit burned(sender, value);
        // }zzzzz

        s_burn.burn{value: value}();

        uint postSenderBalance = address(sender).balance;

        console.log("preSenderBalance: %s, postSenderBalance: %s", preSenderBalance, postSenderBalance);

        // zzzz assertTrue(postSenderBalance > preSenderBalance - SOME_GAS_CONSUMPTION , "sender balance should not change");
    }


    // --- updateParam() tests ---

    function test_verify_nonGov_cannot_updateParams() public {
        uint legalBurnCapValue = address(s_burn).balance + 1;
        vm.prank(makeAddr("Joe"));
        vm.expectRevert(abi.encodePacked(ONLY_GOV_ALLOWED_MSG));
        s_burn.updateParam(BURN_CAP_KEY, abi.encodePacked(legalBurnCapValue));
    }

    function testFuzz_updateParams_success_scenario(uint newBurnCap,uint addedBalance) public {
        vm.deal(address(s_burn), addedBalance);
        vm.assume( newBurnCap >= address(s_burn).balance); //@test?? 

        _updateBurnCap(newBurnCap);        

        assertEq(newBurnCap, s_burn.burnCap(), "bad cap value");
    }

    function testFuzz_updateParams_bad_paramName(string memory paramName, uint addedBalance) public {
        addedBalance = _limitFunds(addedBalance); 
        uint origBurnCap = s_burn.burnCap();
        vm.deal(address(s_burn), addedBalance);                
        vm.prank(s_allContracts.govHubAddr);

        uint legalBurnCapValue = address(s_burn).balance + 1;

        vm.expectRevert(abi.encodePacked(BAD_PARAM_ERROR_MSG));
        s_burn.updateParam(paramName, abi.encodePacked(legalBurnCapValue));

        assertEq(origBurnCap, s_burn.burnCap(), "bad cap value");
    }

    // function testFuzz_updateParams_with_bad_burnBap(uint newBurnCap, uint addedBalance) public {
    //     addedBalance = _limitFunds(addedBalance); 
    //     vm.deal(address(s_burn), addedBalance);

    //     uint origBurnCap = s_burn.burnCap();
    //     uint origBalance = address(s_burn).balance;

    //     vm.assume( newBurnCap < address(s_burn).balance); // should result in OutOfBounds error
        
    //     vm.expectRevert(
    //         abi.encodeWithSelector(System.OutOfBounds.selector, BURN_CAP_KEY, newBurnCap, origBalance, type(uint256).max)
    //     );
    //     _updateBurnCap(newBurnCap);

    //     assertEq(origBurnCap, s_burn.burnCap(), "bad cap value");zzzzz
    // }


    function _updateBurnCap(uint newBurnCap) private {
        uint origCap = s_burn.burnCap();
        vm.prank(s_allContracts.govHubAddr);
        s_burn.updateParam(BURN_CAP_KEY, abi.encodePacked(newBurnCap));
        uint newCap = s_burn.burnCap();
        assertEq(newBurnCap, s_burn.burnCap(), "cap not updated");
    }

}		

//zzzz forge remappings , forge test --gas-report ,  forge coverage , vm.expectEmit  ,  invariantXxx()
// change block.timestamp: vm.warp , forge fmt    // code auto-formatting ,  verify getters never revert


// zzz invariants:
// invariant stats: runs(=number of sequences), calls( all func calls in all Seq), reverts( failed funcs)

	// when testing invariants we can limit the tests targets using (in setUp function):
		// targetContract( contract_addr), targetSelector(FuzzSelector(list-of-funcs)), or excludeContract(addr)


	// Handler-based testing https://www.rareskills.io/post/invariant-testing-solidity , https://www.youtube.com/watch?v=kPx4K8kRvUQ&list=PLO5VPQH6OWdUrKEWPF07CSuVm3T99DQki&index=19 
    //          perform the invariant tests on a "handler"  contract that internally calls the relevant real contracts	


	// [invariant]
	// runs = 128
	// depth = 128
	// fail_on_revert = true/false   //the fact that u cannot set fail_on_revert per-test is a major limitation
