pragma solidity 0.8.4;

import "../RelayerHub.sol";

contract RelayerHubMock is RelayerHub {
    function developmentInit() external {
        dues = dues / 1e16;
        requiredDeposit = requiredDeposit / 1e16;
    }

    function setRelayerRegister(address account, bool value) external {
        relayersExistMap[account] = value;
    }
}
