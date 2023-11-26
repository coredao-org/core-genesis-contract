// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IRelayerHub.sol";
import "./interface/IParamSubscriber.sol";
import "./System.sol";
import "./lib/Address.sol";

/// This contract manages BTC relayers on Core blockchain
contract RelayerHub is IRelayerHub, System, IParamSubscriber{
  uint256 public constant INIT_REQUIRED_DEPOSIT =  1e20;
  uint256 public constant INIT_DUES =  1e18;

  // the refundable deposit
  uint256 public requiredDeposit;
  // the unregister fee
  uint256 public dues;

  mapping(address =>Relayer) relayers;
  mapping(address =>bool) _unused_relayersExistMap;


  struct Relayer{
    uint256 deposit;
    uint256 dues;
  }

  modifier relayerDoesNotExist() {
    require(relayers[msg.sender].deposit == 0, "relayer already exists");
    _;
  }

  modifier relayerExist() {
    require(relayers[msg.sender].deposit > 0, "relayer does not exist");
    _;
  }

  // multisig may not be a relayer
  modifier noProxy() {
    require(msg.sender == tx.origin, "no proxy is allowed");
    _;
  }

  event relayerRegister(address indexed relayer);
  event relayerUnRegister(address indexed relayer);
  event paramChange(string key, bytes value);


  function init() external onlyNotInit{ //see @dev:init
    requiredDeposit = INIT_REQUIRED_DEPOSIT;
    dues = INIT_DUES;
    alreadyInit = true;
  }

  /// Register as a BTC relayer on Core blockchain
  function register() external payable relayerDoesNotExist onlyInit noProxy{
    uint _requiredDeposit = requiredDeposit;
    require(_requiredDeposit > 0 && msg.value == _requiredDeposit, "deposit value does not match requirement");
    relayers[msg.sender] = Relayer(_requiredDeposit, dues);
    emit relayerRegister(msg.sender);
  }
  
/* @product Called by a BTC relayer to unregister from the Core blockchain
   @logic
      1. Remove the relayer from internal structures
      2. Transfer (relayer.deposit - relayer.dues) eth to the relayer
      3. Transfer the relayer.dues eth to the SystemReward contract
 */
  function  unregister() external relayerExist onlyInit{
    Relayer memory r = relayers[msg.sender];
    delete relayers[msg.sender];
    payable(msg.sender).transfer(r.deposit - r.dues); //@dev:safe(no DoS since msg.sender)
    Address.sendValue(payable(_systemReward()), r.dues);
    emit relayerUnRegister(msg.sender);
  }

  /*********************** Param update ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov{
    if (Memory.compareStrings(key,"requiredDeposit")) {
      require(value.length == 32, "length of requiredDeposit mismatch");
      uint256 newRequiredDeposit = BytesToTypes.bytesToUint256(32, value);
      require(newRequiredDeposit > dues, "the requiredDeposit out of range");
      requiredDeposit = newRequiredDeposit;
    } else if (Memory.compareStrings(key,"dues")) {
      require(value.length == 32, "length of dues mismatch");
      uint256 newDues = BytesToTypes.bytesToUint256(32, value);
      require(newDues > 0 && newDues < requiredDeposit, "the dues out of range");
      dues = newDues;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /// Whether the input address is a relayer
  /// @param sender The address to check
  /// @return true/false
  function isRelayer(address sender) external override view returns (bool) {
    return relayers[sender].deposit > 0;
  }
}
