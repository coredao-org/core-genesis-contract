// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract SetOnce {
    bool public s_wasSet;

    modifier setOnlyOnce() {
        require(!s_wasSet, "already set");
        s_wasSet = true;
        _;
    }
}
