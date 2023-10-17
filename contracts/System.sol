// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IRelayerHub.sol";
import {AllContracts} from "./util/TestnetUtils.sol";

contract Gateway {
  address govhub;
  address govhub;
  address govhub;
  address govhub;
  address govhub;
  
  init() {
    //curr addr
  }
  
}

abstract contract System {



  bool public alreadyInit;
  //--- end of old layout ----  

  //@dev: no additional state variables can be added to this contract else 
  // the storage layout of all derived contratcs will break!

  address private constant VALIDATOR_CONTRACT_ADDR = 0x0000000000000000000000000000000000001000;
  address private constant SLASH_CONTRACT_ADDR = 0x0000000000000000000000000000000000001001;
  address private constant SYSTEM_REWARD_ADDR = 0x0000000000000000000000000000000000001002;
  address private constant LIGHT_CLIENT_ADDR = 0x0000000000000000000000000000000000001003;
  address private constant RELAYER_HUB_ADDR = 0x0000000000000000000000000000000000001004;
  address private constant CANDIDATE_HUB_ADDR = 0x0000000000000000000000000000000000001005;
  address private constant GOV_HUB_ADDR = 0x0000000000000000000000000000000000001006;
  address private constant PLEDGE_AGENT_ADDR = 0x0000000000000000000000000000000000001007;
  address private constant BURN_ADDR = 0x0000000000000000000000000000000000001008;
  address private constant FOUNDATION_ADDR = 0x0000000000000000000000000000000000001009;

  // distributed networks
  uint public constant CORE_MAINNET_ID = 1116;
  uint public constant CORE_TESTNET_ID = 1115;

  // local test nodes
  uint public constant GANACHE_ID = 1337;
  uint public constant ANVIL_ID = 31337;
  
  uint public constant STORAGE_LAYOUT_V1 = 1e12;

  uint public constant LIGHT_CLIENT_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 2;
  uint public constant BURN_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 3;
  uint public constant CANDIDATE_HUB_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 4;
  uint public constant GOVHUB_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 5;
  uint public constant PLEDGER_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 6;
  uint public constant RELAYER_HUB_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 7;
  uint public constant SLASH_INDICATOR_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 8;
  uint public constant SYSTEM_REWARD_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 9;
  uint public constant VALIDATOR_SET_SENTINEL_V1 = STORAGE_LAYOUT_V1 + 10;

  modifier onlyCoinbase() {  
    require(msg.sender == _coinbase(), "the message sender must be the block producer");  
    _;
  }

  modifier onlyZeroGasPrice() {    
    require(_gasprice() == 0 , "gasprice is not zero");    
    _;
  }  

  modifier contractAddressesWereSet() {
    require(_contractAddressesWereSet(), "contract addresses not set yet");
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
    require(msg.sender == SLASH_CONTRACT_ADDR, "the msg sender must be slash contract");
    _;
  }

  modifier onlyGov() {
    require(msg.sender == GOV_HUB_ADDR, "the msg sender must be governance contract");
    _;
  }

  modifier onlyCandidate() {
    require(msg.sender == CANDIDATE_HUB_ADDR, "the msg sender must be candidate contract");
    _;
  }

  modifier onlyValidator() {
    require(msg.sender == VALIDATOR_CONTRACT_ADDR, "the msg sender must be validatorSet contract");
    _;
  }

  modifier onlyRelayer() {
    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "the msg sender is not a relayer");
    _;
  }

  modifier onlyIfPositiveValue() {
    require(msg.value > 0, "value should be greater than zero"); 
    _;
  }

  modifier openForAll() {_;}
  
  modifier onlyDeployer(address deployer) {
    require(msg.sender == deployer, "not deployer address"); 
    _;
  }

  modifier onlyIfLocalTestNode() {
    require(_isLocalTestNode(), "not a *local* test node"); 
    _;
  }

  modifier canCallDebugInit(address deployer) {
    _verifyDebugInitMayBeCalled(deployer);
    _;
  }

  modifier onlyIfMapNotInitialized() {
    if (!s_mapWasInitialized) {
      s_mapWasInitialized = true;
      _; // enter function
    }
  }

  function _verifyDebugInitMayBeCalled(address deployer) private view 
                onlyIfLocalTestNode // can be called only on a *local* test node
                onlyInit // avoid debug_init() getting override by later calling init() 
                onlyDeployer(deployer) // can only be called by the deployer
  { 
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

  function _gasprice() internal virtual view returns (uint) {
    return tx.gasprice;
  }

  function _coinbase() internal virtual view returns (address) {
    return block.coinbase;
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
    _transfer(payable(sendTo), amount);
  }

  function _unsafeTransfer(address sendTo, uint256 amount) internal {
    // internally invokes call() with no gas limit! should always be reentrancy safe
    Address.sendValue(payable(sendTo), amount);
  }

  function _sufficientBalance(uint256 amount) private view returns (bool) {
    return address(this).balance >= amount;
  }

  // ------- Registry functions below are platform-contracts that are safe to access ------- 

  function _foundationPayable() internal returns(address payable) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              payable(s_localNodeAddresses.foundationAddr) :
              payable(FOUNDATION_ADDR);
  }

  function _systemReward() internal returns(ISystemReward) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.systemReward :
              ISystemReward(SYSTEM_REWARD_ADDR);
  }

  function _systemRewardPayable() internal returns(address payable) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              payable(address(s_localNodeAddresses.systemReward)) :
              payable(SYSTEM_REWARD_ADDR);
  }

  function _lightClient() internal returns(ILightClient) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.lightClient :
              ILightClient(LIGHT_CLIENT_ADDR);
  }  

  function _candidateHub() internal returns(ICandidateHub) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.candidateHub :
              ICandidateHub(CANDIDATE_HUB_ADDR);
  }  

  function _pledgeAgent() internal returns(IPledgeAgent) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.pledgeAgent :
              IPledgeAgent(PLEDGE_AGENT_ADDR);
  }

  function _burnContract() internal returns(IBurn) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.burn :
              IBurn(BURN_ADDR);
  }

  function _validatorSet() internal returns(IValidatorSet) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.validatorSet :
              IValidatorSet(VALIDATOR_CONTRACT_ADDR);
  }  

  function _slashIndicator() internal returns(ISlashIndicator) contractAddressesWereSet {
    return _isLocalTestNode() ? 
              s_localNodeAddresses.slashIndicator :
              ISlashIndicator(SLASH_CONTRACT_ADDR);
  }  

  function _contractAddressesWereSet() private view returns(bool) {
    return _isLocalTestNode() ? 
              _localNodeAddressesWereSet() : 
              true;
  }

  function _localNodeAddressesWereSet() private view returns(bool) {
    return s_localNodeAddresses.foundationAddr != address(0); // or any other platform contract
  }

  function _setLocalNodeAddresses(AllContracts localNodeContractAddresses) internal onlyIfLocalTestNode {
    require(!_localNodeAddressesWereSet(), "contract addresses already set");
    _verifyLocalNodeAddresses(localNodeContractAddresses);
    s_localNodeAddresses = localNodeContractAddresses;
  }

  function _verifyLocalNodeAddresses() private view {
    assert(s_localNodeAddresses.burn != IBurn(address(0)));
    assert(s_localNodeAddresses.lightClient != ILightClient(address(0)));
    assert(s_localNodeAddresses.slashIndicator != ISlashIndicator(address(0)));
    assert(s_localNodeAddresses.systemReward != ISystemReward(address(0)));
    assert(s_localNodeAddresses.candidateHub != ICandidateHub(address(0)));
    assert(s_localNodeAddresses.pledgeAgent != IPledgeAgent(address(0)));
    assert(s_localNodeAddresses.validatorSet != IValidatorSet(address(0)));
    assert(s_localNodeAddresses.relayerHub != IRelayerHub(address(0)));
    assert(s_localNodeAddresses.foundationAddr != address(0));
    assert(s_localNodeAddresses.govHubAddr != address(0));
  }

  function _isLocalTestNode() private pure returns(bool) {
    // sanity check - should never apply to a global network
    if (block.chainid == CORE_MAINNET_ID || block.chainid == CORE_TESTNET_ID) {
      return false; // main/test global networks use fixed contract addresses
    }     
    return block.chainid == GANACHE_ID || block.chainid == ANVIL_ID;
  }

  modifier nonReentrant() {
    require(!s_reentryGuard, "reentrancy detected");
    s_reentryGuard = true;
    _;
    s_reentryGuard = false;
  }

  function _baseData(bytes32 slotPos) internal pure returns (BaseData storage baseData) {
    assembly {
        baseData.slot := slotPos
    }
  }

  function _basePostUpdate() internal  { // zzzz how to protect this?
    s_reentryGuard = false;
  }
  /* zzzz in childsay Gov:
      bytes32 constant KEY = keccak256("zzzzname-of-contract");

      modifier onlyDeployer() {
        if (!_isLocalTstNode()) {
          //zzzz figure out how to detect _deployer()!!
          require(msg.sender == _deployer(), "not deployer address"); 
        }
        _;
      }

      function postUpdate() external override onlyDeployer { //cannot be onlyOnce!
        _basePostUpdate();
        BaseData storage sref_base = _baseData(KEY);
      }

  */


  /* @dev:init init() is an 'historical' function. It was oiginally called upon the initial 
     platform contracts deployment effectively replacing a constructor. 
     It will not be called on any future updates of the contracts. In fact, since 'onlyNotInit' 
     will always be false, should be considered as a non-callable function
  */
}
