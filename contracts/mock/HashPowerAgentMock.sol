pragma solidity 0.8.4;

import {HashPowerAgent} from "../HashPowerAgent.sol";

contract HashPowerAgentMock is HashPowerAgent {

    function setPowerRewardMap(address delegator, uint256 reward, uint256 accStakedAmount) external {
        rewardMap[delegator] = Reward(reward, accStakedAmount);
    }


}
