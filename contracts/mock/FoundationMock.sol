pragma solidity 0.8.4;

import "../Foundation.sol";

contract FoundationMock is Foundation {

    function setGov(address _gov) external {
        GOV_HUB_ADDR = _gov;
    }

}