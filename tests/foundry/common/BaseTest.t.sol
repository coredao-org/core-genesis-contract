// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "forge-std/console.sol";

import {IBurn} from "../../../contracts/interface/IBurn.sol";
import {ICandidateHub} from "../../../contracts/interface/ICandidateHub.sol";
import {ILightClient} from "../../../contracts/interface/ILightClient.sol";
import {IPledgeAgent} from "../../../contracts/interface/IPledgeAgent.sol";
import {IRelayerHub} from "../../../contracts/interface/IRelayerHub.sol";
import {ISlashIndicator} from "../../../contracts/interface/ISlashIndicator.sol";
import {ISystemReward} from "../../../contracts/interface/ISystemReward.sol";
import {IValidatorSet} from "../../../contracts/interface/IValidatorSet.sol";
import {System} from "../../../contracts/System.sol";

import {Test} from "forge-std/Test.sol";
import {Deployer} from "../../../scripts-foundry/Deployer.s.sol";

abstract contract BaseTest is System, Test {
    
    uint constant internal MAX_ETH_VALUE = 10_000_000 ether; // or any other reasonable cap
    uint constant internal ADDITIONAL_GAS_FEES = 500_000; // or any other reasonable value

    bool constant internal ACCEPT_PAYMENTS = true; // test EOAs/eth-accepting contracts
    bool constant internal REJECT_PAYMENTS = false;  // test eth-rejecting (hostile?) contracts

    ContractAddresses internal s_addresses;
    Deployer internal s_deployer;
    
    bool internal s_acceptPayment; // mutable by design. to be set by a derived test on demand

    constructor(bool accept) {
        s_acceptPayment = accept;
    }

    receive() external payable {
        if (!s_acceptPayment) { 
            revert("payment rejected");
        }
    } 

    function setUp() public virtual {
        s_deployer = new Deployer();
        s_addresses = s_deployer.run();
        _injectAddressesToAll();
    }

    function _injectAddressesToAll() private {
        _inject(s_addresses.validatorSet);
        _inject(s_addresses.slashIndicator);
        _inject(s_addresses.systemReward);
        _inject(s_addresses.lightClient);
        _inject(s_addresses.relayerHub);
        _inject(s_addresses.candidateHub);
        _inject(s_addresses.govHub);
        _inject(s_addresses.pledgeAgent);
        _inject(s_addresses.burn);
        _inject(s_addresses.foundation);
    }

    function _inject(address injectTo) private {
        // test mode only: inject all contracts' addresses to a platform contract
        System(injectTo).updateContractAddr(s_addresses);
    }

    function _hoaxWithGas(address impersonateTo) internal {
        _hoaxWithGas(impersonateTo, 0);
    }

    function _hoaxWithGas(address impersonateTo, uint value) internal {
        hoax(impersonateTo, value + ADDITIONAL_GAS_FEES);
    }

    function _limitFunds(uint value) internal view returns(uint) { 
        return bound(value, 0, MAX_ETH_VALUE); // avoiding OutOfFund error
        //vm.assume( value < MAX_ETH_VALUE); 
    }
}		