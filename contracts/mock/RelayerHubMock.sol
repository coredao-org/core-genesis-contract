pragma experimental ABIEncoderV2;
pragma solidity 0.8.4;

import "../RelayerHub.sol";

contract RelayerHubMock is RelayerHub {
    constructor() RelayerHub() public {}

    function developmentInit() external {
        dues = dues / 1e16;
        requiredDeposit = requiredDeposit / 1e16;
    }
}
