// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import {Configuration} from "../Configuration.sol";

contract ConfigurationMock is Configuration {

    function addConfigMock(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions,
        bool isActive
    ) external onlyInit {
        _addConfig(contractAddr, events, functions, isActive);
    }

    function updateConfigMock(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions
    ) external onlyInit {
        _updateConfig(contractAddr, events, functions);
    }
}
