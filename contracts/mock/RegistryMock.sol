// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Registry} from "../registry/Registry.sol";

contract RegistryMock is Registry {
    
    function _markAsSet() internal override {}
}