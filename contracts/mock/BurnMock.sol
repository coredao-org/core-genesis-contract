pragma solidity 0.8.4;

import "../Burn.sol";

contract BurnMock is Burn {
    function _updateAddressesAlreadyCalled() internal override view returns (bool) {
        return false;
    }
    
    function _testModeAddressesWereSet() internal override view returns (bool) {
        return false;
    }

}
