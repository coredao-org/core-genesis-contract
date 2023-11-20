// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IRelayerHub.sol";

abstract contract System {

  bool public alreadyInit;
  bool public s_guardIsActive;


  address public VALIDATOR_CONTRACT_ADDR;
  address public SLASH_CONTRACT_ADDR;
  address public SYSTEM_REWARD_ADDR;
  address public LIGHT_CLIENT_ADDR;
  address public RELAYER_HUB_ADDR;
  address public CANDIDATE_HUB_ADDR;
  address public GOV_HUB_ADDR;
  address public PLEDGE_AGENT_ADDR;
  address public BURN_ADDR;
  address public FOUNDATION_ADDR;

  function updateContractAddr(
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
  ) external {
    VALIDATOR_CONTRACT_ADDR = valAddr;
    SLASH_CONTRACT_ADDR = slashAddr;
    SYSTEM_REWARD_ADDR = rewardAddr;
    LIGHT_CLIENT_ADDR = lightAddr;
    RELAYER_HUB_ADDR = relayerHubAddr;
    CANDIDATE_HUB_ADDR = candidateHubAddr;
    GOV_HUB_ADDR = govHubAddr;
    PLEDGE_AGENT_ADDR = pledgeAgentAddr;
    BURN_ADDR = burnAddr;
    FOUNDATION_ADDR = foundationAddr;
  }

  modifier onlyCoinbase() {
  
    _;
  }

  modifier onlyZeroGasPrice() {
    
    _;
  }

  modifier onlyNotInit() { //@openissue
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

  modifier nonReentrant() {
    require(!s_guardIsActive, "reentrancy detected");
    s_guardIsActive = true;
    _;
    s_guardIsActive = false;
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

  /* @dev:init
        the init() functions are 'historical' in the sense that they were called once upon platform-contract's 
        initial deployment and will never be called again including not upon updates. If maliciously called, 
        the onlyNotInit() modifier should immediately revert.
        also, since they do not carry parameters the identity of their original caller was irrelevant - hence no 
        ownerOnly or similar access modifier was set
   */
}
