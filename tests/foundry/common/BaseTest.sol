// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/console.sol";

import {Test} from "forge-std/Test.sol";
import {Deployer} from "../../../scripts-foundry/Deployer.s.sol";
import {AllContracts} from "../../../contracts/AllContracts.sol";

abstract contract BaseTest is Test {
    
    uint constant private MAX_ETH_VALUE = 10_000_000 ether; // or any other reasonable cap
    uint constant private REQUIRED_GAS = 500_000; // increase if needed

    bool constant internal ACCEPT_ETH = true; // test EOAs/eth-accepting contracts
    bool constant internal NO_ETH = false;  // test eth-rejecting (hostile?) contracts


    AllContracts internal s_allContracts;
    
    bool internal s_acceptsEth; // mutable by design. can be set by a derived test where needed

    constructor(bool acceptsEth) {
        s_acceptsEth = acceptsEth;
    }

    function setUp() public virtual {
        s_allContracts = new Deployer().run();
    }

    receive() external payable {
        if (!s_acceptsEth) {
            revert("payment rejected");
        }
    } 

    function _hoaxWithGas(address impersonateTo, uint value) internal {
        hoax(impersonateTo, value+REQUIRED_GAS);
    }

    function _hoaxWithGas(address impersonateTo) internal {
        hoax(impersonateTo, REQUIRED_GAS);
    }

    function _limitFunds(uint value) internal view returns(uint) { 
        return bound(value, 0, MAX_ETH_VALUE); // avoid "EvmError: OutOfFund"
        //vm.assume( value < MAX_ETH_VALUE); 
    }
}		
