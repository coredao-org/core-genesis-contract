pragma solidity 0.8.4;

import "../SystemReward.sol";

contract SystemRewardMock is SystemReward {
    function setOperator(address operator) public {
        operators[operator] = true;
        numOperator++;
    }
}
