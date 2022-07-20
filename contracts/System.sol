pragma solidity ^0.6.4;

import "./interface/ISystemReward.sol";
import "./interface/IRelayerHub.sol";
import "./interface/ILightClient.sol";

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

  modifier notContract() {
    require(!isContract(msg.sender), "contract is not allowed to be a relayer");
    _;
  }

  // Not reliable, do not use when need strong verify
  function isContract(address addr) internal view returns (bool) {
    uint size;
    assembly { size := extcodesize(addr) }
    return size > 0;
  }
}
