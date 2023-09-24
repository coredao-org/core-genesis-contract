pragma solidity 0.8.4;

import "../SystemReward.sol";
import "../Registry.sol";

contract SystemRewardMock is SystemReward {
    constructor(Registry registry, address lightClientAddr, address slashIndicatorAddr) 
            SystemReward(registry, lightClientAddr, slashIndicatorAddr) {} 

    function setOperator(address operator) public {
        operators[operator] = true;
        numOperator++;
    }
}
