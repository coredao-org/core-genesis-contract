pragma solidity 0.6.12;

import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IRelayerHub.sol";
import "./interface/IParamSubscriber.sol";
import "./System.sol";
import "./lib/SafeMath.sol";


contract RelayerHub is IRelayerHub, System, IParamSubscriber{
  using SafeMath for uint256;

  uint256 public constant INIT_REQUIRED_DEPOSIT =  1e20;
  uint256 public constant INIT_DUES =  1e17;

  // requiredDeposit = refundable deposit
  // dues = unregister fee
  uint256 public requiredDeposit;
  uint256 public dues;

  mapping(address =>Relayer) relayers;
  mapping(address =>bool) relayersExistMap;

  struct Relayer{
    uint256 deposit;
    uint256 dues;
  }

  modifier noExist() {
    require(!relayersExistMap[msg.sender], "relayer already exists");
    _;
  }

  modifier exist() {
    require(relayersExistMap[msg.sender], "relayer does not exist");
    _;
  }

  modifier noProxy() {
    require(msg.sender == tx.origin, "no proxy is allowed");
    _;
  }

  event relayerRegister(address _relayer);
  event relayerUnRegister(address _relayer);
  event paramChange(string key, bytes value);


  function init() external onlyNotInit{
    requiredDeposit = INIT_REQUIRED_DEPOSIT;
    dues = INIT_DUES;
    alreadyInit = true;
  }

  function register() external payable noExist onlyInit notContract noProxy{
    require(msg.value == requiredDeposit, "deposit value does not match requirement");
    relayers[msg.sender] = Relayer(requiredDeposit, dues);
    relayersExistMap[msg.sender] = true;
    emit relayerRegister(msg.sender);
  }

  function  unregister() external exist onlyInit{
    Relayer memory r = relayers[msg.sender];
    msg.sender.transfer(r.deposit.sub(r.dues));
    address payable systemPayable = address(uint160(SYSTEM_REWARD_ADDR));
    systemPayable.transfer(r.dues);
    delete relayersExistMap[msg.sender];  
    delete relayers[msg.sender];
    emit relayerUnRegister(msg.sender);
  }

  /*********************** Param update ********************************/
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

  function isRelayer(address sender) external override view returns (bool) {
    return relayersExistMap[sender];
  }
}
