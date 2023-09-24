// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract SetOnce {
    bool public s_wasSet;

    function markAsSet() internal {
        s_wasSet = true;
    }

    modifier setOnlyOnce() {
        require(!s_wasSet, "already set");
        _;
    }
}