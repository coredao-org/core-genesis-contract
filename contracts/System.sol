// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IRelayerHub.sol";

contract System {

  bool public alreadyInit;


  address public constant VALIDATOR_CONTRACT_ADDR = 0x0000000000000000000000000000000000001000;
  address public constant SLASH_CONTRACT_ADDR = 0x0000000000000000000000000000000000001001;
  address public constant SYSTEM_REWARD_ADDR = 0x0000000000000000000000000000000000001002;
  address public constant LIGHT_CLIENT_ADDR = 0x0000000000000000000000000000000000001003;
  address public constant RELAYER_HUB_ADDR = 0x0000000000000000000000000000000000001004;
  address public constant CANDIDATE_HUB_ADDR = 0x0000000000000000000000000000000000001005;
  address public constant GOV_HUB_ADDR = 0x0000000000000000000000000000000000001006;
  address public constant PLEDGE_AGENT_ADDR = 0x0000000000000000000000000000000000001007;
  address public constant BURN_ADDR = 0x0000000000000000000000000000000000001008;
  address public constant FOUNDATION_ADDR = 0x0000000000000000000000000000000000001009;
  address public constant STAKE_HUB_ADDR = 0x0000000000000000000000000000000000001010;

  address public constant CORE_AGENT_ADDR = 0x0000000000000000000000000000000000001011;
  address public constant HASH_AGENT_ADDR = 0x0000000000000000000000000000000000001012;
  address public constant BTC_AGENT_ADDR = 0x0000000000000000000000000000000000001013;
  address public constant BTC_STAKE_ADDR = 0x0000000000000000000000000000000000001014;
  address public constant BTCLST_STAKE_ADDR = 0x0000000000000000000000000000000000001015;

  modifier onlyCoinbase() {
  
    require(msg.sender == block.coinbase, "the message sender must be the block producer");
  
    _;
  }

  modifier onlyZeroGasPrice() {
    
    require(tx.gasprice == 0 , "gasprice is not zero");
    
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

  modifier onlyStakeHub() {
    require(msg.sender == STAKE_HUB_ADDR, "the msg sender must be stake hub contract");
    _;
  }

  modifier onlyBtcStake() {
    require(msg.sender == BTC_STAKE_ADDR, "the msg sender must be bitcoin stake contract");
    _;
  }

  modifier onlyBtcAgent() {
    require(msg.sender == BTC_AGENT_ADDR, "the msg sender must be bitcoin agent contract");
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
}
