// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {BytesToTypes} from "./lib/BytesToTypes.sol";
import {Memory} from "./lib/Memory.sol";
import {IParamSubscriber} from "./interface/IParamSubscriber.sol";
import {System} from "./System.sol";

/* @dev storing latest platform-contract addresses thus allowing a community process 
    (rather than 'node voting') to determine the platform-contracts to be used
*/
contract Gateway is System, IParamSubscriber { 

  uint constant private VALUE_LENGTH = 32;

  struct PlatformAddresses {
    address validator;
    address slashIndicator;
    address systemReward;
    address lightClient;
    address relayerHub;
    address candidateHub;
    address govHub;
    address pledgeAgent;
    address burn;
    address foundation;
  } 

  error ZeroAddressNotAllowed();

  event paramChange(string key, bytes value);

  PlatformAddresses public s_addresses;

  // @dev using this approach we need to somehow pass the current addresses to the Gateway,
  //  preferrably in the constructor. An alternative would be to issue a community 
  //  proposal for the Gateway initialize and use the updateParam() route
  constructor(PlatformAddresses memory addresses) { 
    s_addresses = addresses;
  }

  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    address addr = _bytesToAddress(key, value, true); // new version of a platform contract

    if (_eq(key, "validator")) {
        s_addresses.validator = addr;
    } else if (_eq(key, "slashIndicator")) {
        s_addresses.slashIndicator = addr;
    } else if (_eq(key, "systemReward")) {
        s_addresses.systemReward = addr;
    } else if (_eq(key, "lightClient")) {
        s_addresses.lightClient = addr;
    } else if (_eq(key, "relayerHub")) {
        s_addresses.relayerHub = addr;
    } else if (_eq(key, "candidateHub")) {
        s_addresses.candidateHub = addr;
    } else if (_eq(key, "govHub")) {
        s_addresses.govHub = addr;
    } else if (_eq(key, "pledgeAgent")) {
        s_addresses.pledgeAgent = addr;
    } else if (_eq(key, "burn")) {
        s_addresses.burn = addr;
    } else if (_eq(key, "foundation")) {
        s_addresses.foundation = addr;
    } else {
      revert("unknown param");
    }
    emit paramChange(key, value);
  }

  function init() external onlyNotInit {
    alreadyInit = true; // avoid onlyInit() modifier reverting
  }

  function _bytesToAddress(string calldata key, bytes calldata value, bool notZero) private pure returns (address addr) {
    if (value.length != VALUE_LENGTH) {
      revert MismatchParamLength(key);
    }
    addr = BytesToTypes.bytesToAddress(VALUE_LENGTH, value);
    if (notZero && addr == address(0)) {
        revert ZeroAddressNotAllowed();
    }
  }

  function _eq(string memory s1, string memory s2) private pure returns (bool){
    return Memory.compareStrings(s1, s2);
  }
}