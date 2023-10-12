// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract Updatable {
    //@dev this marker contract is used to mark contracts that can be updated by the golang engine
    //such contract must:
    //      a. avoid declaring constructor
    //      b. avoid modifying their prior-version storage layout: 
    //          - state-vars may be *appended* but not deleted, or re-ordered. 
    //          - state-var name may be changed, but not the type.
    //          - constant state-var are not storage so not included in the above restriction
}