// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BytesLib.sol";
import "./lib/SatoshiPlusHelper.sol";
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
  using RLPEncode for uint256;

  uint256 public constant MISDEMEANOR_THRESHOLD = 50;
  uint256 public constant FELONY_THRESHOLD = 150;
  uint256 public constant DECREASE_RATE = 4;
  uint256 public constant INIT_REWARD_FOR_REPORT_DOUBLE_SIGN = 5e20;
  uint256 public constant INIT_FELONY_DEPOSIT = 1e21;
  uint256 public constant INIT_FELONY_ROUND = 2;
  uint256 public constant INFINITY_ROUND = 0xFFFFFFFFFFFFFFFF;
  uint256 public constant INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION = 5e20;

  // State of the contract
  address[] public validators;
  mapping(address => Indicator) public indicators;
  uint256 public previousHeight;
  uint256 public misdemeanorThreshold;
  uint256 public felonyThreshold;

  uint256 public rewardForReportDoubleSign;

  uint256 public felonyDeposit;
  uint256 public felonyRound;

  uint256 public rewardForReportFinalityViolation;

  struct Indicator {
    uint256 height;
    uint256 count;
    bool exist;
  }

  // Proof that a validator misbehaved in fast finality
  struct VoteData {
    uint256 srcNum;
    bytes32 srcHash;
    uint256 tarNum;
    bytes32 tarHash;
    bytes sig;
  }

  struct FinalityEvidence {
    VoteData voteA;
    VoteData voteB;
    bytes voteAddr;
  }

  modifier oncePerBlock() {
    require(block.number > previousHeight, "can not slash twice in one block");
    _;
    previousHeight = block.number;
  }

  /*********************** events **************************/
  event validatorSlashed(address indexed validator);
  event indicatorCleaned();
  
  function init() external onlyNotInit{
    misdemeanorThreshold = MISDEMEANOR_THRESHOLD;
    felonyThreshold = FELONY_THRESHOLD;
    rewardForReportDoubleSign = INIT_REWARD_FOR_REPORT_DOUBLE_SIGN;
    felonyDeposit = INIT_FELONY_DEPOSIT;
    felonyRound = INIT_FELONY_ROUND;
    rewardForReportFinalityViolation = INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION;
    alreadyInit = true;
  }

  /*********************** External func ********************************/
  /// Slash the validator because of unavailability
  /// This method is called by other validators from golang consensus engine.
  /// @param validator The consensus address of validator
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

  /// Slash the validator because of double sign
  /// This method is called by external verifiers
  /// @param header1 A block header submitted by the validator
  /// @param header2 Another block header submitted by the validator with same height and parent
  function doubleSignSlash(bytes calldata header1, bytes calldata header2) external onlyInit {
    RLPDecode.RLPItem[] memory items1 = header1.toRLPItem().toList();
    RLPDecode.RLPItem[] memory items2 = header2.toRLPItem().toList();

    require(items1[0].toUintStrict() == items2[0].toUintStrict(), "parent of two blocks must be the same");

    (bytes32 sigHash1, address validator1) = parseHeader(items1);
    (bytes32 sigHash2, address validator2) = parseHeader(items2);
    require(sigHash1 != sigHash2, "must be two different blocks");
    require(validator1 != address(0x00), "validator is illegal");
    require(validator1 == validator2, "must be the same validator");
    require(IValidatorSet(VALIDATOR_CONTRACT_ADDR).isValidator(validator1), "not a validator");
    IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(validator1, INFINITY_ROUND, felonyDeposit);
    ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(payable(msg.sender), rewardForReportDoubleSign);
  }

  function submitFinalityViolationEvidence(FinalityEvidence memory evidence) public onlyInit {
    if (rewardForReportFinalityViolation == 0) {
      rewardForReportFinalityViolation = INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION;
    }

    // Basic check
    require(evidence.voteA.srcNum+256 > block.number &&
      evidence.voteB.srcNum+256 > block.number, "too old block involved");
    require(!(evidence.voteA.srcHash == evidence.voteB.srcHash &&
      evidence.voteA.tarHash == evidence.voteB.tarHash), "two identical votes");
    require(evidence.voteA.srcNum < evidence.voteA.tarNum &&
      evidence.voteB.srcNum < evidence.voteB.tarNum, "srcNum bigger than tarNum");

    // Vote rules check
    require((evidence.voteA.srcNum<evidence.voteB.srcNum && evidence.voteB.tarNum<evidence.voteA.tarNum) ||
      (evidence.voteB.srcNum<evidence.voteA.srcNum && evidence.voteA.tarNum<evidence.voteB.tarNum) ||
      evidence.voteA.tarNum == evidence.voteB.tarNum, "no violation of vote rules");

    // BLS verification
    require(verifyBLSSignature(evidence.voteA, evidence.voteAddr) &&
      verifyBLSSignature(evidence.voteB, evidence.voteAddr), "verify signature failed");

    (address[] memory vals, bytes[] memory voteAddrs) = IValidatorSet(VALIDATOR_CONTRACT_ADDR).getValidatorsAndVoteAddresses();
    for (uint256 i; i < voteAddrs.length; ++i) {
      if (BytesLib.equal(voteAddrs[i],  evidence.voteAddr)) {
        ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(payable(msg.sender), rewardForReportFinalityViolation);
        IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(vals[i], felonyRound, felonyDeposit);
        break;
      }
    }
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
      revert UnsupportedGovParam(key);
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
    bytes memory sig = BytesLib.slice(extra, extra.length - 65, 65);
    bytes[] memory rlpbytes_list = new bytes[](16);
    rlpbytes_list[0] = RLPEncode.encodeUint(uint(SatoshiPlusHelper.CHAINID));
    for(uint256 i = 0; i < 15; ++i){
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

    if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
      return address(0x0);
    }

    if (v < 27) {
      v += 27;
    }

    if (v != 27 && v != 28) {
      return address(0x0);
    }
    return ecrecover(hash, v, r, s);
  }

  function verifyBLSSignature(VoteData memory vote, bytes memory voteAddr) internal view returns(bool) {
    bytes[] memory elements = new bytes[](4);
    bytes memory _bytes = new bytes(32);
    elements[0] = vote.srcNum.encodeUint();
    bytes32ToBytes(32, vote.srcHash, _bytes);
    elements[1] = _bytes.encodeBytes();
    elements[2] = vote.tarNum.encodeUint();
    bytes32ToBytes(32, vote.tarHash, _bytes);
    elements[3] = _bytes.encodeBytes();

    bytes32ToBytes(32, keccak256(elements.encodeList()), _bytes);

    // assemble input data
    bytes memory input = new bytes(176);
    bytesConcat(input, _bytes, 0, 32);
    bytesConcat(input, vote.sig, 32, 96);
    bytesConcat(input, voteAddr, 128, 48);

    // call the precompiled contract to verify the BLS signature
    // the precompiled contract's address is 0x66
    bytes memory output = new bytes(1);
    assembly {
      let len := mload(input)
      if iszero(staticcall(not(0), 0x66, add(input, 0x20), len, add(output, 0x20), 0x01)) {
        revert(0, 0)
      }
    }
    if (BytesLib.toUint8(output, 0) != uint8(1)) {
      return false;
    }
    return true;
  }

  function bytesConcat(bytes memory data, bytes memory _bytes, uint256 index, uint256 len) internal pure {
    for (uint i; i<len; ++i) {
      data[index++] = _bytes[i];
    }
  }

  function bytes32ToBytes(uint _offst, bytes32 _input, bytes memory _output) internal pure {
    assembly {
        mstore(add(_output, _offst), _input)
        mstore(add(add(_output, _offst),32), add(_input,32))
    }
  }
}