// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {IRelayerHub} from "./interface/IRelayerHub.sol";

abstract contract System {

  address internal constant _VALIDATOR_CONTRACT_ADDR = 0x0000000000000000000000000000000000001000;
  address internal constant _SLASH_CONTRACT_ADDR = 0x0000000000000000000000000000000000001001;
  address internal constant _SYSTEM_REWARD_ADDR = 0x0000000000000000000000000000000000001002;
  address internal constant _LIGHT_CLIENT_ADDR = 0x0000000000000000000000000000000000001003;
  address internal constant _RELAYER_HUB_ADDR = 0x0000000000000000000000000000000000001004;
  address internal constant _CANDIDATE_HUB_ADDR = 0x0000000000000000000000000000000000001005;
  address internal constant _GOV_HUB_ADDR = 0x0000000000000000000000000000000000001006;
  address internal constant _PLEDGE_AGENT_ADDR = 0x0000000000000000000000000000000000001007;
  address internal constant _BURN_ADDR = 0x0000000000000000000000000000000000001008;
  address internal constant _FOUNDATION_ADDR = 0x0000000000000000000000000000000000001009;

  // ReentrancyGuard
  uint256 private constant GUARD_NOT_ENTERED = 0;
  uint256 private constant GUARD_ENTERED = 100;

  // ERC-7201 namespace: keccak256(abi.encode(uint256(keccak256("core.system.extended.storage")) - 1)) & ~bytes32(uint256(0xff));
  bytes32 private constant _EXT_STORAGE_LOCATION = 0x67a7102a872f79141e3e6e107bddf1a70e311104f2c8c3897ed1c7c60974e600;

  bool public alreadyInit;


  modifier onlyCoinbase() {  
    require(_isBlockProducer(), "the message sender must be the block producer");  
    _;
  }

  modifier onlyZeroGasPrice() {    
    require(_zeroGasPrice() , "gasprice is not zero");
    _;
  }

  modifier onlyNotInit() {
    require(!alreadyInit, "the contract already init");
    _;
  }

  modifier onlyInit() {
    require(alreadyInit, "the contract not init yet");
    _;
  }

  modifier onlySlash() {
    require(msg.sender == _slash(), "the msg sender must be slash contract");
    _;
  }

  modifier onlyGov() {
    require(msg.sender == _govHub(), "the msg sender must be governance contract");
    _;
  }

  modifier onlyCandidate() {
    require(msg.sender == _candidateHub(), "the msg sender must be candidate contract");
    _;
  }

  modifier onlyValidator() {
    require(msg.sender == _validatorSet(), "the msg sender must be validatorSet contract");
    _;
  }

  modifier onlyRelayer() {
    require(IRelayerHub(_relayerHub()).isRelayer(msg.sender), "the msg sender is not a relayer");
    _;
  }

  modifier onlyIfPositiveValue() {
    require(msg.value > 0, "value should be greater than zero"); 
    _;
  }

  modifier openForAll() {_;}

  modifier nonReentrant() {
    ExtStorage storage $ = _ext();
    require($.guardStatus != GUARD_ENTERED, "reentry detected");
    $.guardStatus = GUARD_ENTERED;
    _;
    $.guardStatus = GUARD_NOT_ENTERED;
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

 /* @dev ExtStorage: an extended storage struct used to store base contract state variables in a 'floating' 
    i.e. non-sequential storage slot. this is done to avoid collisions with derived contracts' state variables.       
    Uses ERC-7201 namespace to reduce chances of collision, see https://eips.ethereum.org/EIPS/eip-7201
  */
  struct ExtStorage {
    /// @custom:storage-location erc7201:core.system.extended.storage
    uint256 guardStatus;
    // @dev additional extended-storage fields goes here
  }


 /* @dev _ext(): obtain a storage reference to the non-sequential extended storage struct
    see https://solidity.readthedocs.io/en/v0.8.4/internals/layout_in_storage.html#layout-of-state-variables-in-storage
  */
  function _ext() private pure returns (ExtStorage storage $) {
    assembly { $.slot := _EXT_STORAGE_LOCATION }
  }

  function _isBlockProducer() internal virtual view returns (bool) {
    return msg.sender == block.coinbase;
  }

  function _zeroGasPrice() internal virtual view returns (bool) {
    return tx.gasprice == 0;
  }



  // -- address virtual getters --

  function _validatorSet() view internal virtual returns (address) {
    return _VALIDATOR_CONTRACT_ADDR;   
  }

  function _slash() view internal virtual returns (address) {
    return _SLASH_CONTRACT_ADDR;   
  }

  function _systemReward() view internal virtual returns (address) {
    return _SYSTEM_REWARD_ADDR;   
  }

  function _lightClient() view internal virtual returns (address) {
    return _LIGHT_CLIENT_ADDR;   
  }

  function _relayerHub() view internal virtual returns (address) {
    return _RELAYER_HUB_ADDR;   
  }

  function _candidateHub() view internal virtual returns (address) {
    return _CANDIDATE_HUB_ADDR;   
  }

  function _govHub() view internal virtual returns (address) {
    return _GOV_HUB_ADDR;   
  }

  function _pledgeAgent() view internal virtual returns (address) {
    return _PLEDGE_AGENT_ADDR;   
  }

  function _burn() view internal virtual returns (address) {
    return _BURN_ADDR;   
  }

  function _foundation() view internal virtual returns (address) {
    return _FOUNDATION_ADDR;   
  }


  /* @dev:init
        the init() functions are 'historical' in the sense that they were called once upon platform-contract's 
        initial deployment and will never be called again including not upon updates. If maliciously called, 
        the onlyNotInit() modifier should immediately revert.
        also, since they do not carry parameters the identity of their original caller was irrelevant - hence no 
        ownerOnly or similar access modifier was set
   */
}
