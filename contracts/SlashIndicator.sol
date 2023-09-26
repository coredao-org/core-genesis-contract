// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
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

/// This contract manages slash/jail operations to validators on Core blockchain
contract SlashIndicator is ISlashIndicator,System,IParamSubscriber{
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.RLPItem;
  using RLPEncode for bytes;
  using RLPEncode for bytes[];

  uint256 public constant MISDEMEANOR_THRESHOLD = 50;
  uint256 public constant FELONY_THRESHOLD = 150;
  uint256 public constant DECREASE_RATE = 4;
  uint256 public constant INIT_REWARD_FOR_REPORT_DOUBLE_SIGN = 5e20;
  uint32 public constant CHAINID = 1116;
  uint256 public constant INIT_FELONY_DEPOSIT = 1e21;
  uint256 public constant INIT_FELONY_ROUND = 2;
  uint256 public constant INFINITY_ROUND = 0xFFFFFFFFFFFFFFFF;

  // State of the contract
  address[] public validators;
  mapping(address => Indicator) public indicators;
  uint256 public previousHeight;
  uint256 public misdemeanorThreshold;
  uint256 public felonyThreshold;

  uint256 public rewardForReportDoubleSign;

  uint256 public felonyDeposit;
  uint256 public felonyRound;

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

  /*********************** events **************************/
  event validatorSlashed(address indexed validator);
  event indicatorCleaned();
  event paramChange(string key, bytes value);

  
  function init() external onlyNotInit{
    misdemeanorThreshold = MISDEMEANOR_THRESHOLD;
    felonyThreshold = FELONY_THRESHOLD;
    rewardForReportDoubleSign = INIT_REWARD_FOR_REPORT_DOUBLE_SIGN;
    felonyDeposit = INIT_FELONY_DEPOSIT;
    felonyRound = INIT_FELONY_ROUND;
    alreadyInit = true;
  }

  /*********************** External func ********************************/

/* @product Called by the block producer once per-block to slash the validator 
    because of unavailability
   @param validator: validator to slash
   @logic
      1. increase the count of the validator's slash.indicator record by 1 and sets its 
         height to the current block number
      2. If the slash.indicator count has reached the felonyThreshold jump (default = 150), 
         then zero it and call the felony method for the validator
      3. Else, if the slash.indicator count has reached the misdemeanorThreshold 
         jump (default = 50), then leave its value unchanged and call the misdemeanor 
         method for the validator
*/
  function slash(address validator) external onlyCoinbase onlyInit oncePerBlock onlyZeroGasPrice{
    if (!IValidatorSet(VALIDATOR_CONTRACT_ADDR).isValidator(validator)) {
      return;
    }
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

/* @product Slash the validator because of double sign
   @param header1: A block header submitted by the validator
   @param header2: Another block header submitted by the validator with same height and parent

  @logic
    1. This method is called by external verifiers, with no verifications are done to enfore it. @openissue
       It receives header1 and header2 parameters, and verifies that:
          a. the headers refer to to distinct blocks i.e. 'double sign'
          b. that the validators inside each header are identical and legal validators
    2. it then continues to apply a felony on the validator using the global felonyDeposit value
       and to pass the global rewardForReportDoubleSign value to the caller of this method
    3. Note that if the current SystemReward's balance is less than the reward amount then the 
      latter will be slashed to the balance value without reverting
    4. Note2 that nowhere is a check made to verify that the method caller is himself not the 
       'bad' validator
*/
  function doubleSignSlash(bytes calldata header1, bytes calldata header2) external onlyInit {
    RLPDecode.RLPItem[] memory items1 = header1.toRLPItem().toList();
    RLPDecode.RLPItem[] memory items2 = header2.toRLPItem().toList();

    require(items1[0].toUintStrict() == items2[0].toUintStrict(),"parent of two blocks must be the same");

    (bytes32 sigHash1, address validator1) = parseHeader(items1);
    (bytes32 sigHash2, address validator2) = parseHeader(items2);
    require(sigHash1 != sigHash2, "must be two different blocks");
    require(validator1 != address(0x00), "validator is illegal");
    require(validator1 == validator2, "must be the same validator");
    require(IValidatorSet(VALIDATOR_CONTRACT_ADDR).isValidator(validator1), "not a validator");
    IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(validator1, INFINITY_ROUND, felonyDeposit);
    ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(payable(msg.sender), rewardForReportDoubleSign);
  }

  /// Clean slash record by felonyThreshold/DECREASE_RATE.
  /// @dev To prevent validator misbehaving and leaving, do not clean slash record
  /// @dev to zero, but decrease by felonyThreshold/DECREASE_RATE.
  /// @dev Clean is an effective implement to reorganize "validators" and "indicators".
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
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov{
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key,"misdemeanorThreshold")) {
      uint256 newMisdemeanorThreshold = BytesToTypes.bytesToUint256(32, value);
      if (newMisdemeanorThreshold == 0 || newMisdemeanorThreshold >= felonyThreshold) {
        revert OutOfBounds(key, newMisdemeanorThreshold, 1, felonyThreshold - 1);
      }
      misdemeanorThreshold = newMisdemeanorThreshold;
    } else if (Memory.compareStrings(key,"felonyThreshold")) {
      uint256 newFelonyThreshold = BytesToTypes.bytesToUint256(32, value);
      if (newFelonyThreshold <= misdemeanorThreshold) {
        revert OutOfBounds(key, newFelonyThreshold, misdemeanorThreshold + 1, type(uint256).max);
      }
      felonyThreshold = newFelonyThreshold;
    } else if (Memory.compareStrings(key,"rewardForReportDoubleSign")) {
      uint256 newRewardForReportDoubleSign = BytesToTypes.bytesToUint256(32, value);
      if (newRewardForReportDoubleSign == 0 || newRewardForReportDoubleSign > 1e21) {
        revert OutOfBounds(key, newRewardForReportDoubleSign, 1, 1e21);
      }
      rewardForReportDoubleSign = newRewardForReportDoubleSign;
    } else if (Memory.compareStrings(key,"felonyDeposit")) {
      uint256 newFelonyDeposit = BytesToTypes.bytesToUint256(32, value);
      if (newFelonyDeposit < 1e18) {
        revert OutOfBounds(key, newFelonyDeposit, 1e18, type(uint256).max);
      }
      felonyDeposit = newFelonyDeposit;
    } else if (Memory.compareStrings(key,"felonyRound")) {
      uint256 newFelonyRound = BytesToTypes.bytesToUint256(32, value);
      if (newFelonyRound == 0) {
        revert OutOfBounds(key, newFelonyRound, 1, type(uint256).max);
      }
      felonyRound = newFelonyRound;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key,value);
  }

  /*********************** query api ********************************/
  /// Get slash indicators of a validator
  /// @param validator The validator address to query
  function getSlashIndicator(address validator) external view returns (uint256,uint256) {
    Indicator memory indicator = indicators[validator];
    return (indicator.height, indicator.count);
  }

  /*********************** Internal Functions **************************/
  function parseHeader(RLPDecode.RLPItem[] memory items) internal pure returns (bytes32,address){
    bytes memory extra = items[12].toBytes();
    bytes memory sig = BytesLib.slice(extra, 32, 65);
    bytes[] memory rlpbytes_list = new bytes[](16);
    rlpbytes_list[0] = RLPEncode.encodeUint(uint(CHAINID));
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
}