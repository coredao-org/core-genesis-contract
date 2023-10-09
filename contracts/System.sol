// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {Address} from "./lib/Address.sol";
import {Registry} from "./registry/Registry.sol";
import {AllContracts} from "./registry/AllContracts.sol";

import {IBurn} from "./interface/IBurn.sol";
import {IValidatorSet} from "./interface/IValidatorSet.sol";
import {ICandidateHub} from "./interface/ICandidateHub.sol";
import {ILightClient} from "./interface/ILightClient.sol";
import {ISystemReward} from "./interface/ISystemReward.sol";
import {ISlashIndicator} from "./interface/ISlashIndicator.sol";
import {IRelayerHub} from "./interface/IRelayerHub.sol";
import {IPledgeAgent} from "./interface/IPledgeAgent.sol";


contract System is Registry {
  
  Registry private immutable s_registry;  

  AllContracts private s_allContracts;  

  constructor(Registry registry) {
    s_registry = registry;  
  }

  function updateContractAddr( //placeholder
    address valAddr,
    address slashAddr,
    address rewardAddr,
    address lightAddr,
    address relayerHubAddr,
    address candidateHubAddr,
    address govHubAddr,
    address pledgeAgentAddr,
    address burnAddr,
    address foundationAddr
  ) external pure {
  }
  
  modifier onlyCoinbase() {
    require(msg.sender == _coinbase(), "the message sender must be the block producer");
    _;
  }

  modifier onlyZeroGasPrice() {
    require(_gasprice() == 0 , "gasprice is not zero");
    _;
  }

  modifier onlyNotInit() { //@openissue remove modifier
    //require(!s_alreadyInit, "the contract already init");
    _;
  }

  modifier onlyInit() { //@openissue remove modifier
    //require(s_alreadyInit, "the contract not init yet");
    _;
  }

  modifier onlySlash() {
    require(msg.sender == address(_slashIndicator()), "the msg sender must be slashIndicator contract");
    _;
  }

  modifier onlyGov() {
    require(msg.sender == _govHubAddr(), "the msg sender must be governance contract");
    _;
  }

  modifier onlyCandidate() {
    require(msg.sender == address(_candidateHub()), "the msg sender must be candidateHub contract");
    _;
  }

  modifier onlyValidator() {
    require(msg.sender == address(_validatorSet()), "the msg sender must be validatorSet contract");
    _;
  }

  modifier onlyRelayer() {
    require(_relayerHub().isRelayer(msg.sender), "the msg sender is not a relayer");
    _;
  }

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

  function init() external onlyNotInit {} // placeholder

  function _gasprice() internal virtual view returns (uint) {
    return tx.gasprice;
  }

  function _coinbase() internal virtual view returns (address) {
    return block.coinbase;
  } 

  function govHub() external returns (address) {
    return _govHubAddr();
  }


  // ------- eth-send methods --------

  function _send(address sendTo, uint256 amount) internal returns (bool) {
    if (!_sufficientBalance(amount)) {
      return false;
    }
    return payable(sendTo).send(amount);
  }

  function _unsafeSend(address sendTo, uint256 amount) internal returns (bool) {
    // internally invokes call() with no gas limit! should always be reentrancy safe
    if (!_sufficientBalance(amount)) {
      return false;
    }
    (bool success, ) = payable(sendTo).call{value: amount}("");
    return success;
  }

  function _transfer(address sendTo, uint256 amount) internal {
    require(_sufficientBalance(amount), "insufficient balance");
    payable(sendTo).transfer(amount);
  }

  function _unsafeTransfer(address sendTo, uint256 amount) internal {
    // internally invokes call() with no gas limit! should always be reentrancy safe
    Address.sendValue(payable(sendTo), amount);
  }

  function _sufficientBalance(uint256 amount) private view returns (bool) {
    return address(this).balance >= amount;
  }

  // --- Registry functions below are platform-contracts that are safe to access ---

  function _foundationPayable() internal returns(address payable) {
    _cacheAllContractsLocally();
    return payable(s_allContracts.foundationAddr);
  }

  function _systemReward() internal returns(ISystemReward) {
    _cacheAllContractsLocally();
    return s_allContracts.systemReward;
  }

  function _systemRewardPayable() internal returns(address payable) {
    _cacheAllContractsLocally();
    address _systemRewardAddr = address(s_allContracts.systemReward);
    return payable(_systemRewardAddr);
  }

  function _lightClient() internal returns(ILightClient) {
    _cacheAllContractsLocally();
    return s_allContracts.lightClient;
  }  

  function _relayerHub() internal returns(IRelayerHub) {
    _cacheAllContractsLocally();
    return s_allContracts.relayerHub;
  }

  function _candidateHub() internal returns(ICandidateHub) {
    _cacheAllContractsLocally();
    return s_allContracts.candidateHub;
  }  

  function _pledgeAgent() internal returns(IPledgeAgent) {
    _cacheAllContractsLocally();
    return s_allContracts.pledgeAgent;
  }

  function _burnContract() internal returns(IBurn) {
    _cacheAllContractsLocally();
    return s_allContracts.burn;
  }

  function _validatorSet() internal returns(IValidatorSet) {
    _cacheAllContractsLocally();
    return s_allContracts.validatorSet;
  }  

  function _slashIndicator() internal returns(ISlashIndicator) {
    _cacheAllContractsLocally();
    return s_allContracts.slashIndicator;
  }  

  function _govHubAddr() internal returns(address) {
    _cacheAllContractsLocally();
    return s_allContracts.govHubAddr;
  }

  function _cacheAllContractsLocally() private {
    //@correlate-registry.cache
    bool alreadyCached = s_allContracts.burn != IBurn(address(0)); // or any other platform contract
    if (!alreadyCached) { 
      s_allContracts = s_registry.getAllContracts();
    }
  }

}
