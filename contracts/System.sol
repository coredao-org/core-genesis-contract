// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IRelayerHub.sol";
import {AllContracts} from "./util/TestnetUtils.sol";

abstract contract System {

  bool public alreadyInit;
  uint public storageLayoutSentinel = SYSTEM_SENTINEL; zzzzz not sure if i can update base contract??

  address public immutable s_deployer = msg.sender;
  address public mapping(string => bool) s_funcWasCalled;
  AllContracts private s_localNodeAddresses;
  bool private s_contractMapInitialized;
  address private mapping(address => bool) s_contractMap;  

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
  
  uint public constant SYSTEM_SENTINEL = 1e18 + 1;
  uint public constant LIGHT_CLIENT_SENTINEL = 1e18 + 2;
  uint public constant BURN_SENTINEL = 1e18 + 3;
  uint public constant CANDIDATE_HUB_SENTINEL = 1e18 + 4;
  uint public constant GOVHUB_SENTINEL = 1e18 + 5;
  uint public constant PLEDGER_SENTINEL = 1e18 + 6;
  uint public constant RELAYER_HUB_SENTINEL = 1e18 + 7;
  uint public constant SLASH_INDICATOR_SENTINEL = 1e18 + 8;
  uint public constant SYSTEM_REWARD_SENTINEL = 1e18 + 9;
  uint public constant VALIDATOR_SET_SENTINEL = 1e18 + 10;

  string public constant DEBUG_INIT_CALL = "debug_init";

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
  
  modifier onlyDeployer() {
    require(msg.sender == s_deployer, "not deployer address"); 
    _;
  }

  modifier onlyIfLocalTestNode() {
    require(_isLocalTestNode(), "not a *local* test node"); 
    _;
  }

  modifier calledOnlyOnce(string calldata funcName) {
    require(!s_funcWasCalled[funcName], "function already called"); 
    s_funcWasCalled[funcName] = true;
    _;
  }

  modifier canCallDebugInit() {
    _verifyDebugInitMayBeCalled();
    _;
  }

  function _verifyDebugInitMayBeCalled() private view 
                onlyInit // avoid debug_init() getting override by later calling init() 
                onlyIfLocalTestNode // can be called only on a *local* test node
                onlyDeployer // can only be called by the deployer
                calledOnlyOnce(DEBUG_INIT_CALL) // and only once
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

  // --- Registry functions below are platform-contracts that are safe to access ---

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

  function _onlyPlatformContracts(address[] memory targets) internal returns(bool) {
    _initContractMapIfNeeded();
    uint len = targets.length;
    for (uint i = 0; i < len; i++) {
        if (!s_contractMap[targets[i]]) {
            return false; // not a platform contract
        }
    }
    return true;  
  }  

  function _initContractMapIfNeeded() private {
    if (s_contractMapInitialized) {
      return; 
    }
    s_contractMapInitialized = true;

    address _burn, _lightClient, _slashIndicator, _systemReward, _candidateHub, 
            _pledgeAgent, _validatorSet, _relayerHub, _foundationAddr, _govHubAddr;
    if (_isLocalTestNode()) {
      _verifyAllLocalNodeAddressesWereSet();
      _burn = address(s_localNodeAddresses.burn);
      _lightClient = address(s_localNodeAddresses.lightClient);
      _slashIndicator = address(s_localNodeAddresses.slashIndicator);
      _systemReward = address(s_localNodeAddresses.systemReward);
      _candidateHub = address(s_localNodeAddresses.candidateHub);
      _pledgeAgent = address(s_localNodeAddresses.pledgeAgent);
      _validatorSet = address(s_localNodeAddresses.validatorSet);
      _relayerHub = address(s_localNodeAddresses.relayerHub);
      _foundationAddr = s_localNodeAddresses.foundationAddr;
      _govHubAddr = s_localNodeAddresses.govHubAddr;
    } else {
      _burn = BURN_ADDR;
      _lightClient = LIGHT_CLIENT_ADDR;
      _slashIndicator = SLASH_CONTRACT_ADDR;
      _systemReward = SYSTEM_REWARD_ADDR;
      _candidateHub = CANDIDATE_HUB_ADDR;
      _pledgeAgent = PLEDGE_AGENT_ADDR;
      _validatorSet = VALIDATOR_CONTRACT_ADDR;
      _relayerHub = RELAYER_HUB_ADDR;
      _foundationAddr = FOUNDATION_ADDR;
      _govHubAddr = GOV_HUB_ADDR;
    }
    s_contractMap[_burn] = true;
    s_contractMap[_lightClient] = true;
    s_contractMap[_slashIndicator] = true;
    s_contractMap[_systemReward] = true;
    s_contractMap[_candidateHub] = true;
    s_contractMap[_pledgeAgent] = true;
    s_contractMap[_validatorSet] = true;
    s_contractMap[_relayerHub] = true;
    s_contractMap[_foundationAddr] = true;
    s_contractMap[_govHubAddr] = true;  
  }

  function _verifyAllLocalNodeAddressesWereSet() private view {
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
    // let's be extra cautious
    if (block.chainid == CORE_MAINNET_ID || block.chainid == CORE_TESTNET_ID) {
      return false; // all global networks use fixed contract addresses
    }     
    return block.chainid == GANACHE_ID || block.chainid == ANVIL_ID;
  }
}
