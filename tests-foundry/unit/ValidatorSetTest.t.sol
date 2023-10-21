// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {console} from "forge-std/console.sol";
import {BaseTest} from "../common/BaseTest.t.sol";
import {ValidatorSet} from "../../contracts/ValidatorSet.sol";

contract ValidatorSetTest is BaseTest  {

    uint constant private INIT_NUM_VALIDATORS = 15;

    ValidatorSet private s_validatorSet;

    event rewardTo(address indexed to, uint256 amount);
    event rewardEmpty();
    event receiveDeposit(address indexed from, uint256 amount);
    event paramChange(string key, bytes value);

    constructor() BaseTest(REJECT_PAYMENTS) {}

	function setUp() public override {
        BaseTest.setUp();
        s_validatorSet = ValidatorSet(payable(s_addresses.validatorSet));
	}

    function test_construction() public {
        console.log("====>len: %d", s_validatorSet.numValidators());
        assertEq(s_validatorSet.numValidators(), INIT_NUM_VALIDATORS, "currentValidatorSet should be empty");

        // ValidatorSet.Validator storage asdsa = s_validatorSet.currentValidatorSet(0);//.consensusAddress;

        ValidatorSet.Validator memory val = s_validatorSet.getValidator(0);
        
        address xxx = val.operateAddress;
        console.log("xxx :   %s", xxx);

        // ValidatorSet.Validator memory aa = s_validatorSet.currentValidatorSet(0);
        
        // assertEq(s_validatorSet.blockReward(), ValidatorSet.BLOCK_REWARD, "bad reward");
        // assertEq(s_validatorSet.blockRewardIncentivePercent(), ValidatorSet.BLOCK_REWARD_INCENTIVE_PERCENT, "bad nventive");
    }


//   constructor(Registry registry) System(registry) {
//     (ValidatorSet.Validator[] memory validatorSet, bool valid) = decodeValidatorSet(INIT_VALIDATORSET_BYTES);
//     require(valid, "failed to parse init validatorSet");
//     uint256 validatorSize = validatorSet.length;
//     for (uint256 i = 0; i < validatorSize; i++) {
//       currentValidatorSet.push(validatorSet[i]);
//       currentValidatorSetMap[validatorSet[i].consensusAddress] = i + 1;
//     }
//     blockReward = BLOCK_REWARD;
//     blockRewardIncentivePercent = BLOCK_REWARD_INCENTIVE_PERCENT;
//   }


    // function testFuzz_sendEther(uint value) public {
    //     value = bound(value, 0, 1000 ether);
    //     address sender = makeAddr("sender");
    //     _hoaxWithGas(sender, value);
    //     if (value > 0) {
    //         vm.expectEmit(true,false,false,true);
    //         emit receiveDeposit(sender, value);
    //     }
    //     payable(address(s_systemReward)).transfer(value);
    // }

    // function testFuzz_systemReward(uint value, bool isBurn) public {
    //     _hoaxWithGas(s_addresses.govHub); // updateParam() can only be called by the governance contract
    //     uint isBurnVal = isBurn ? 1 : 0;
    //     s_systemReward.updateParam(IS_BURN_KEY, abi.encodePacked(isBurnVal));
    //     assertEq(s_systemReward.isBurn(), isBurn, "failed to set isBurn");

    //     value = bound(value, 1, 1000 ether); // onlyIfPositiveValue
        
    //     address sender = makeAddr("sender");
    //     _hoaxWithGas(sender, value);

    //     vm.expectEmit(true,false,false,true);
    //     emit receiveDeposit(sender, value);

    //     s_systemReward.receiveRewards{value: value}();
    // }

    // function testFuzz_claimRewards(uint value, uint systemRewardBalance, bool operatorIsSlash, bool toAddressIsZero) public {
    //     value = bound(value, 1, 1000 ether);
    //     systemRewardBalance = bound(systemRewardBalance, 1, 1000 ether);

    //     vm.deal(address(s_systemReward), systemRewardBalance);

    //     address payable to = toAddressIsZero ? payable(address(0)) : payable(makeAddr("to"));
        
    //     // only these two contracts can invoke claimRewards()
    //     address operator = operatorIsSlash ? s_addresses.slashIndicator : s_addresses.lightClient;
    
    //     uint actualAmount = value < systemRewardBalance ? value : systemRewardBalance;
    //     bool allowRewardClaiming = to != address(0) && actualAmount > 0;
    //     if (allowRewardClaiming) {
    //         vm.expectEmit(true,false,false,true);
    //         emit rewardTo(to, actualAmount);
    //     } else {
    //         vm.expectEmit(false,false,false,true);
    //         emit rewardEmpty();
    //     }
        
    //     _hoaxWithGas(operator);            
    //     s_systemReward.claimRewards(to, value);
    // }
}		

