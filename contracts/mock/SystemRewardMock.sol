// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../SystemReward.sol";
import "../registry/Registry.sol";


contract SystemRewardMock is SystemReward {
    mapping(address => bool) private operators;
    
    constructor(Registry registry) SystemReward(registry) {}

    function setOperator(address operator) public { 
        operators[operator] = true;
    }

    function _isOperator(address addr) internal override view returns (bool) {
        return operators[addr];
    }
}
