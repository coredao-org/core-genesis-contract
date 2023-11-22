// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../SystemReward.sol";

contract SystemRewardMock is SystemReward {
    function setOperator(address operator) public {
        operators[operator] = true;
        numOperator++;
    }

    function _updateAddressesAlreadyCalled() internal override view returns (bool) {
        return false;
    }

    function _testModeAddressesWereSet() internal override view returns (bool) {
        return false;
    }

    function _gasPriceIsZero() internal override view returns (bool) {
        return true;
    }
}
