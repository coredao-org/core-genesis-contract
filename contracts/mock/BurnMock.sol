// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../Burn.sol";

contract BurnMock is Burn {
    function _updateAddressesAlreadyCalled() internal override view returns (bool) {
        return false;
    }

    function _addressesWereSet() internal override view returns (bool) {
        return false;
    }
}
