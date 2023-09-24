// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {IRelayerHub} from "./interface/IRelayerHub.sol";
import {Registry} from "./Registry.sol";
import {ContractAddresses} from "./ContractAddresses.sol";

abstract contract System is Registry, ContractAddresses {

  Registry internal immutable s_registry;

  constructor(Registry registry) {
    s_registry = registry;
  }

  modifier onlyCoinbase() {  
    require(msg.sender == block.coinbase, "the message sender must be the block producer");  
    _;
  }

  modifier onlyZeroGasPrice() {    
    require(tx.gasprice == 0 , "gasprice is not zero");    
    _;
  }

  modifier onlySlash() {
    require(msg.sender == address(s_registry.slashIndicator()), "the msg sender must be slash contract");
    _;
  }

  modifier onlyGov() {
    require(msg.sender == s_registry.govHubAddr(), "the msg sender must be governance contract");
    _;
  }

  modifier onlyCandidate() {
    require(msg.sender == address(s_registry.candidateHub()), "the msg sender must be candidate contract");
    _;
  }

  modifier onlyValidator() {
    require(msg.sender == address(s_registry.validatorSet()), "the msg sender must be validatorSet contract");
    _;
  }

  modifier onlyRelayer() {
    require(s_registry.relayerHub().isRelayer(msg.sender), "the msg sender is not a relayer");
    _;
  }

  modifier onlyIfPositiveValue() {
    require(msg.value > 0, "value should not be zero"); 
    _;
  }

  modifier openForAll() {_;}

  /// The length of param mismatch. Default is 32 bytes.
  /// @param name the name of param.
  error MismatchParamLength(string name);

  /// The passed in param is out of bound. Should be in range [`lowerBound`,
  /// `upperBound`] but the value is `given`.
  /// @param name the name of param.
  /// @param given the value of param.
  /// @param lowerBound requested lower bound of the param.
  /// @param upperBound requested upper bound of the param
  error OutOfBounds(string name, uint256 given, uint256 lowerBound, uint256 upperBound);
}
