pragma solidity 0.6.12;
import "./System.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BytesLib.sol";
import "./interface/ISlashIndicator.sol";
import "./interface/IValidatorSet.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ISystemReward.sol";
import "./lib/RLPDecode.sol";
import "./lib/RLPEncode.sol";

contract SlashIndicator is ISlashIndicator,System,IParamSubscriber{
  using RLPDecode for *;
  using RLPEncode for *;

  uint256 public constant MISDEMEANOR_THRESHOLD = 50;
  uint256 public constant FELONY_THRESHOLD = 150;
  uint256 public constant DECREASE_RATE = 4;
  uint256 public constant INIT_REWARD_FOR_REPORT_DOUBLE_SIGN = 1e16;
  uint32 public constant CHAINID = 1112;
  int256 public constant INIT_FELONY_DEPOSIT = 1e22;
  uint256 public constant INIT_FELONY_ROUND = 2;

  // State of the contract
  address[] public validators;
  mapping(address => Indicator) public indicators;
  uint256 public previousHeight;
  uint256 public misdemeanorThreshold;
  uint256 public felonyThreshold;

  uint256 public rewardForReportDoubleSign;

  int256 public felonyDeposit;
  uint256 public felonyRound;

  event validatorSlashed(address indexed validator);
  event indicatorCleaned();
  event paramChange(string key, bytes value);

  struct Indicator {
    uint256 height;
    uint256 count;
    bool exist;
  }

  modifier oncePerBlock() {
    require(block.number > previousHeight, "can not slash twice in one block");
    _;
    previousHeight = block.number;
  }

  
  function init() external onlyNotInit{
    misdemeanorThreshold = MISDEMEANOR_THRESHOLD;
    felonyThreshold = FELONY_THRESHOLD;
    rewardForReportDoubleSign = INIT_REWARD_FOR_REPORT_DOUBLE_SIGN;
    felonyDeposit = INIT_FELONY_DEPOSIT;
    felonyRound = INIT_FELONY_ROUND;
    alreadyInit = true;
  }

  /*********************** External func ********************************/
  // @validator consensus address of validator
  // this method is called by other validators from golang consensus engine
  function slash(address validator) external onlyCoinbase onlyInit oncePerBlock onlyZeroGasPrice{
    Indicator memory indicator = indicators[validator];
    if (indicator.exist) {
      indicator.count++;
    } else {
      indicator.exist = true;
      indicator.count = 1;
      validators.push(validator);
    }
    indicator.height = block.number;
    if (indicator.count % felonyThreshold == 0) {
      indicator.count = 0;
      IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(validator, felonyRound, felonyDeposit);
    } else if (indicator.count % misdemeanorThreshold == 0) {
      IValidatorSet(VALIDATOR_CONTRACT_ADDR).misdemeanor(validator);
    }
    indicators[validator] = indicator;
    emit validatorSlashed(validator);
  }

  // this method is called by external verifiers
  function doubleSignSlash(bytes calldata header1,bytes calldata header2) external onlyInit {
    RLPDecode.RLPItem[] memory items1 = header1.toRLPItem().toList();
    RLPDecode.RLPItem[] memory items2 = header2.toRLPItem().toList();

    require(items1[0].toUintStrict() == items2[0].toUintStrict(),"parent of two blocks must be the same");

    (bytes32 sigHash1, address validator1) = parseHeader(items1);
    (bytes32 sigHash2, address validator2) = parseHeader(items2);
    require(sigHash1 != sigHash2, "must be two different blocks");
    require(validator1 != address(0x00), "header data is illegal");
    require(validator1 == validator2, "validators of the two blocks must be the same");
    require(IValidatorSet(VALIDATOR_CONTRACT_ADDR).isValidator(validator1), "not a validator");
    IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(validator1, type(uint256).max, felonyDeposit);
    ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(msg.sender, rewardForReportDoubleSign);
  }

  function parseHeader(RLPDecode.RLPItem[] memory items) internal pure returns (bytes32,address){
    bytes memory extra = items[12].toBytes();
    bytes memory sig = BytesLib.slice(extra, 32, 65);
    bytes[] memory rlpbytes_list = new bytes[](16);
    rlpbytes_list[0] = CHAINID.encodeInt();
    for(uint256 i = 0;i < 15;++i){
      if(i == 12){
        rlpbytes_list[13] = BytesLib.slice(extra, 0, 32).encodeBytes();
      } else {
        rlpbytes_list[i + 1] = items[i].toRlpBytes();
      }
    }
    bytes memory rlpbytes = rlpbytes_list.encodeList();
    bytes32 sigHash = keccak256(rlpbytes);
    return (sigHash , ecrecovery(sigHash,sig));
  }

  function ecrecovery(bytes32 hash, bytes memory sig) internal pure returns (address) {
    bytes32 r;
    bytes32 s;
    uint8 v;

    if (sig.length != 65) {
      return address(0x0);
    }

    assembly {
      r := mload(add(sig, 32))
      s := mload(add(sig, 64))
      v := and(mload(add(sig, 65)), 255)
    }

    if (v < 27) {
      v += 27;
    }

    if (v != 27 && v != 28) {
      return address(0x0);
    }
    return ecrecover(hash, v, r, s);
  }


  // To prevent validator misbehaving and leaving, do not clean slash record to zero, but decrease by felonyThreshold/DECREASE_RATE .
  // Clean is an effective implement to reorganize "validators" and "indicators".
  function clean() external override(ISlashIndicator) onlyCandidate onlyInit{
    if(validators.length == 0){
      return;
    }
    uint256 i = 0;
    uint256 j = validators.length-1;
    for (;i <= j;) {
      bool findLeft = false;
      bool findRight = false;
      for(;i<j;i++){
        Indicator memory leftIndicator = indicators[validators[i]];
        if(leftIndicator.count > felonyThreshold/DECREASE_RATE){
          leftIndicator.count = leftIndicator.count - felonyThreshold/DECREASE_RATE;
          indicators[validators[i]] = leftIndicator;
        }else{
          findLeft = true;
          break;
        }
      }
      for(;i<=j;j--){
        Indicator memory rightIndicator = indicators[validators[j]];
        if(rightIndicator.count > felonyThreshold/DECREASE_RATE){
          rightIndicator.count = rightIndicator.count - felonyThreshold/DECREASE_RATE;
          indicators[validators[j]] = rightIndicator;
          findRight = true;
          break;
        }else{
          delete indicators[validators[j]];
          validators.pop();
        }
        // avoid underflow
        if(j==0){
          break;
        }
      }
      // swap element in array
      if (findLeft && findRight){
        delete indicators[validators[i]];
        validators[i] = validators[j];
        validators.pop();
      }
      // avoid underflow
      if(j==0){
        break;
      }
      // move to next
      i++;
      j--;
    }
    emit indicatorCleaned();
  }

  /*********************** Param update ********************************/
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov{
    if (Memory.compareStrings(key,"misdemeanorThreshold")) {
      require(value.length == 32, "length of misdemeanorThreshold mismatch");
      uint256 newMisdemeanorThreshold = BytesToTypes.bytesToUint256(32, value);
      require(newMisdemeanorThreshold >= 1 && newMisdemeanorThreshold < felonyThreshold, "the misdemeanorThreshold out of range");
      misdemeanorThreshold = newMisdemeanorThreshold;
    } else if (Memory.compareStrings(key,"felonyThreshold")) {
      require(value.length == 32, "length of felonyThreshold mismatch");
      uint256 newFelonyThreshold = BytesToTypes.bytesToUint256(32, value);
      require(newFelonyThreshold <= 1000 && newFelonyThreshold > misdemeanorThreshold, "the felonyThreshold out of range");
      felonyThreshold = newFelonyThreshold;
    } else if (Memory.compareStrings(key,"rewardForReportDoubleSign")) {
      require(value.length == 32, "length of rewardForReportDoubleSign mismatch");
      uint256 newRewardForReportDoubleSign = BytesToTypes.bytesToUint256(32, value);
      require(newRewardForReportDoubleSign != 0, "the rewardForReportDoubleSign out of range");
      rewardForReportDoubleSign = newRewardForReportDoubleSign;
    } else if (Memory.compareStrings(key,"felonyDeposit")) {
      require(value.length == 32, "length of felonyDeposit mismatch");
      int256 newFelonyDeposit = BytesToTypes.bytesToInt256(32, value);
      require(newFelonyDeposit >= INIT_FELONY_DEPOSIT * 100, "the felonyDeposit out of range");
      felonyDeposit = newFelonyDeposit;
    } else if (Memory.compareStrings(key,"felonyRound")) {
      require(value.length == 32, "length of felonyRound mismatch");
      uint256 newFelonyRound = BytesToTypes.bytesToUint256(32, value);
      require(newFelonyRound >= 2, "the felonyRound out of range");
      felonyRound = newFelonyRound;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key,value);
  }

  /*********************** query api ********************************/
  function getSlashIndicator(address validator) external view returns (uint256,uint256) {
    Indicator memory indicator = indicators[validator];
    return (indicator.height, indicator.count);
  }
}