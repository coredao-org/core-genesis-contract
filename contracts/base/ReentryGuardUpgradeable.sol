// SPDX-License-Identifier: MIT
// Loosely based on openzeppelin-contracts-upgradeable but with no slot-based storage 
pragma solidity 0.8.4;

abstract contract ReentryGuardUpgradeable {

    uint256 private constant NOT_ENTERED = 1;
    uint256 private constant ENTERED = 2;

    uint256 public _status;

    modifier nonReentrant() {
        require(_status != ENTERED, "reentrancy was detected");
        _status = ENTERED;
        _;
        _status = NOT_ENTERED;
    }

    function __ReentrancyGuard_init() internal {
        _status = NOT_ENTERED;
    }
}
