pragma solidity 0.8.4;

import "../RelayerHub.sol";
import "../Registry.sol";

contract RelayerHubMock is RelayerHub {

    constructor(Registry registry) RelayerHub(registry) {}

    function developmentInit() external {
        dues = dues / 1e16;
        requiredDeposit = requiredDeposit / 1e16;
    }
}
