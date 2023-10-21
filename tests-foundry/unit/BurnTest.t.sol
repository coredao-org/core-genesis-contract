// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {console} from "forge-std/console.sol";
import {BaseTest} from "../common/BaseTest.t.sol";
import {Burn} from "../../contracts/Burn.sol";

contract BurnTest is BaseTest  {
    string constant private ONLY_GOV_ALLOWED_MSG = "the msg sender must be governance contract";
    string constant private BAD_PARAM_ERROR_MSG = "unknown param";
    string constant private BURN_CAP_KEY = "burnCap";

    Burn private s_burn;

    event burned(address indexed to, uint256 amount); // event must be clowned here from tested contract to be used in expectEmit()

    constructor() BaseTest(ACCEPT_PAYMENTS) {} // accept eth else burn() will fail on transfering the remaining funds back to the caller

	function setUp() public override {
	    BaseTest.setUp();
        s_burn = Burn(s_addresses.burn);
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

    // function testFuzz_burn_with_burnCap_lesser_than_balance_results_in_no_eth_transfer(uint burnCap) public {
    //     burnCap = _limitFunds(burnCap);

    //     if (address(s_burn).balance <= burnCap) {
    //         vm.deal(address(s_burn), burnCap+1); 
    //     }
        
    //     _updateBurnCap(burnCap); zzzzzz OutOfBounds(burnCap, 2851217494792020368862436 [2.851e24], 2851217494792020368862437 

    //     assertTrue( burnCap >= address(s_burn).balance, "bad burnCap value");

    //     address sender = makeAddr("Joe");
        
    //     uint value = burnCap; 
    //     _hoaxWithGas(sender, value); // internally adds ADDITIONAL_GAS_FEES to value

    //     uint preSenderBalance = address(sender).balance;

    //     s_burn.burn{value: value}();

    //     uint postSenderBalance = address(sender).balance;

    //     console.log("preSenderBalance: %s, postSenderBalance: %s", preSenderBalance, postSenderBalance);

    //     assertTrue(postSenderBalance > preSenderBalance - ADDITIONAL_GAS_FEES , "no eth should have been transferred to sender");
    // }


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
        vm.assume(!_strEqual(paramName, s_burn.BURN_CAP_KEY())); // else no BAD_PARAM_ERROR_MSG revert
        addedBalance = _limitFunds(addedBalance); 
        uint origBurnCap = s_burn.burnCap();
        vm.deal(address(s_burn), addedBalance);                
        vm.prank(s_addresses.govHub);

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
        vm.prank(s_addresses.govHub);
        s_burn.updateParam(BURN_CAP_KEY, abi.encodePacked(newBurnCap));
        uint newCap = s_burn.burnCap();
        console.log("orig cap: %d, new cap: %d", origCap, newCap);
        assertEq(newBurnCap, s_burn.burnCap(), "cap not updated");
    }

}		
