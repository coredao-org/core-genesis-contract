// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {console} from "forge-std/console.sol";
import {BaseTest} from "../common/BaseTest.t.sol";
import {ValidatorSet} from "../../contracts/ValidatorSet.sol";
import {SystemReward} from "../../contracts/SystemReward.sol";
import {Address} from "../../contracts/lib/Address.sol";

contract ValidatorSetTest is BaseTest  {

    uint constant private INIT_NUM_VALIDATORS = 15;
    string constant private IS_BURN_KEY = "isBurn";

    ValidatorSet private s_validatorSet;
    SystemReward private s_systemReward;

    event rewardTo(address indexed to, uint256 amount);
    event rewardEmpty();
    event receiveDeposit(address indexed from, uint256 amount);
    event paramChange(string key, bytes value);

    constructor() BaseTest(REJECT_PAYMENTS) {}

	function setUp() public override {
        BaseTest.setUp();
        s_validatorSet = ValidatorSet(payable(s_deployer.validatorSetAddr()));
        s_systemReward = SystemReward(payable(s_deployer.systemRewardAddr()));
        console.log("==> s_validatorSet: %s, s_systemReward: %s", s_deployer.validatorSetAddr(), s_deployer.systemRewardAddr());
	}

    function testFuzz_sendEther(uint value) public {
        value = bound(value, 0, 1000 ether);
        address sender = makeAddr("sender");
        _hoaxWithGas(sender, value);
        if (value > 0) {
            vm.expectEmit();
            emit receiveDeposit(sender, value);
        }
        Address.sendValue(payable(address(s_systemReward)), value);
    }

    function testFuzz_systemReward_receiveRewards(uint value, bool isBurn) public {
        _hoaxWithGas(s_deployer.govHubAddr()); // updateParam() can only be called by the governance contract
        uint isBurnVal = isBurn ? 1 : 0;
        s_systemReward.updateParam(IS_BURN_KEY, _toBytes(isBurnVal));
        assertEq(s_systemReward.isBurn(), isBurn, "failed to set isBurn");

        value = bound(value, 1, 1000 ether); // onlyIfPositiveValue
        
        address sender = makeAddr("sender");
        _hoaxWithGas(sender, value);

        vm.expectEmit(true,false,false,true);
        emit receiveDeposit(sender, value);

        s_systemReward.receiveRewards{value: value}();
    }

    // function testFuzz_claimRewards(uint value, uint systemRewardBalance, bool operatorIsSlash, bool toAddressIsZero) public {
    //     value = bound(value, 1, 1000 ether);
    //     systemRewardBalance = bound(systemRewardBalance, 1, 1000 ether);

    //     vm.deal(address(s_systemReward), systemRewardBalance);

    //     address payable to = toAddressIsZero ? payable(address(0)) : payable(makeAddr("to"));
        
    //     // only these two contracts can invoke claimRewards()
    //     address operator = operatorIsSlash ? s_deployer.slashAddr() : s_deployer.lightClientAddr();
    
    //     uint actualAmount = value < systemRewardBalance ? value : systemRewardBalance;
    //     bool allowRewardClaiming = to != address(0) && actualAmount > 0;
    //     if (allowRewardClaiming) {
    //         vm.expectEmit(true,false,false,true);
    //         emit rewardTo(to, actualAmount);
    //     } else {
    //         vm.expectEmit(false,false,false,true);
    //         emit rewardEmpty();
    //     }
        
    //     vm.expectRevert("only operator is allowed to call the method");    
    //     s_systemReward.claimRewards(to, value);
    // }
}		

