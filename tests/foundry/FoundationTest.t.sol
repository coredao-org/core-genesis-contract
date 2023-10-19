// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {console} from "forge-std/console.sol";
import {BaseTest} from "./common/BaseTest.t.sol";
import {Foundation} from "../../contracts/Foundation.sol";

contract FoundationTest is BaseTest  {

    Foundation private s_foundation;

    event received(address indexed from, uint256 amount);
    event fundSuccess(address indexed payee, uint256 amount);
    event fundFailed(address indexed payee, uint256 amount, uint256 balance);

    constructor() BaseTest(REJECT_PAYMENTS) {} 

	function setUp() public override {
        BaseTest.setUp();
        s_foundation = Foundation(payable(s_addresses.foundation));
	}


    function testFuzz_sendEther(uint value) public {
        value = bound(value, 0, 1000 ether);
        address sender = makeAddr("sender");
        _hoaxWithGas(sender, value);
        if (value > 0) {
            vm.expectEmit(true,false,false,true);
            emit received(sender, value);
        }
        payable(address(s_foundation)).transfer(value);
    }

    function testFuzz_fund_successful(uint value) public {
        value = bound(value, 0, 1000 ether);
        address payable payee = payable(makeAddr("payee"));
        _hoaxWithGas(s_addresses.govHub);
        
        vm.deal(address(s_foundation), value); // make sure Foundation has the needed funds
        
        vm.expectEmit(true,false,false,true);
        emit fundSuccess(payee, value);

        s_foundation.fund(payee, value);
    }

    function testFuzz_fund_failed_insufficient_balance(uint value) public {
        value = bound(value, 1, 1000 ether);
        address payable payee = payable(makeAddr("payee"));
        _hoaxWithGas(s_addresses.govHub);
        
        uint newBalance = value-1;
        vm.deal(address(s_foundation), newBalance); // make sure Foundation has the needed funds
        
        vm.expectEmit(true,false,false,true);
        emit fundFailed(payee, value, newBalance);

        s_foundation.fund(payee, value);
    }

    function testFuzz_fund_failed_payee_with_no_payable_func(uint value) public {
        value = bound(value, 1, 1000 ether);
        address payable payee = payable(address(this)); // note that this contract's receive() will always revert
        _hoaxWithGas(s_addresses.govHub);
        
        uint newBalance = value-1;
        vm.deal(address(s_foundation), newBalance); // make sure Foundation has the needed funds
        
        vm.expectEmit(true,false,false,true);
        emit fundFailed(payee, value, newBalance);

        s_foundation.fund(payee, value);
    }
}		

