pragma solidity ^0.6.4;

import "../SystemReward.sol";

contract SystemRewardMock is SystemReward {
    constructor() SystemReward() public {}

    function setOperator(address operator) public {
        operators[operator] = true;
        numOperator++;
    }
}
