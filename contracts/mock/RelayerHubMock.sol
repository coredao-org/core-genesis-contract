pragma solidity 0.8.4;

import "../RelayerHub.sol";

contract RelayerHubMock is RelayerHub {
    function developmentInit() external {
        dues = dues / 1e16;
        requiredDeposit = requiredDeposit / 1e16;
    }

    function _updateAddressesAlreadyCalled() internal override view returns (bool) {
        return false;
    }

    function _testModeAddressesWereSet() internal override view returns (bool) {
        return false;
    }
}
