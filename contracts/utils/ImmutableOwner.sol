// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract ImmutableOwner {
    address public immutable s_owner = msg.sender;

    modifier onlyOwner() {
        require(msg.sender == s_owner, "not owner");
        _;
    }
}