// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IValidatorSet.sol";
import "./interface/ICandidateHub.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ISlashIndicator.sol";
import "./interface/ILightClient.sol";
import "./System.sol";
import "./lib/Address.sol";

/// This contract manages all validator candidates on Core blockchain
/// It also exposes the method `turnRound` for the consensus engine to execute the `turn round` workflow
contract CandidateHub is ICandidateHub, System, IParamSubscriber {

  uint256 public constant INIT_REQUIRED_MARGIN = 1e22;
  uint256 public constant INIT_DUES = 1e20;
  uint256 private constant INIT_ROUND_INTERVAL = 86400;
  uint256 private constant INIT_VALIDATOR_COUNT = 21;
  uint256 public constant MAX_COMMISSION_CHANGE = 10;
  uint256 public constant CANDIDATE_COUNT_LIMIT = 1000;

  uint256 public constant SET_CANDIDATE = 1;
  uint256 public constant SET_INACTIVE = 2;
  uint256 public constant DEL_INACTIVE = 0xFF-SET_INACTIVE;
  uint256 public constant SET_JAIL = 4;
  uint256 public constant DEL_JAIL = 0xFF-SET_JAIL;
  uint256 public constant SET_MARGIN = 8;
  uint256 public constant DEL_MARGIN = 0xFF-SET_MARGIN;
  uint256 public constant SET_VALIDATOR = 16;
  uint256 public constant DEL_VALIDATOR = 0xFF-SET_VALIDATOR;
  uint256 public constant ACTIVE_STATUS = SET_CANDIDATE | SET_VALIDATOR;
  uint256 public constant UNREGISTER_STATUS = SET_CANDIDATE | SET_INACTIVE | SET_MARGIN;

  // the refundable deposit
  uint256 public requiredMargin;
  // the unregister fee
  uint256 public dues;

  uint256 public roundInterval;
  uint256 public validatorCount;
  uint256 public maxCommissionChange;

  // candidate list.
  Candidate[] public candidateSet;
  // key is the `operateAddr` of `Candidate`,
  // value is the index of `candidateSet`.
  mapping(address => uint256) public operateMap;

  // key is the `consensusAddr` of `Candidate`,
  // value is the index of `candidateSet`.
  mapping(address => uint256) consensusMap;

  // key is the `consensusAddr` of `Candidate`,
  // value is release round
  mapping(address => uint256) public jailMap;

  uint256 public roundTag;
  

  struct Candidate {
    address operateAddr;
    address consensusAddr;
    address payable feeAddr;
    uint256 commissionThousandths;
    uint256 margin;
    uint256 status;
    uint256 commissionLastChangeRound;
    uint256 commissionLastRoundValue;
  }

  modifier onlyIfCandidate() {
    require(isCandidate(msg.sender), "candidate does not exist");
    _;
  }

  modifier onlyIfNotCandidate() {
    require(!isCandidate(msg.sender), "candidate already exist");
    _;
  }

  modifier onlyIfConsensusAddrNotExist(address consensusAddr) {
    require(consensusMap[consensusAddr] == 0, "consensus already exists");
    _;
  }

  modifier onlyIfValueExceedsMargin() {
    require(msg.value >= requiredMargin, "deposit is not enough");
    _;
  }

  /*********************** events **************************/
  event registered(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths, uint256 margin);
  event unregistered(address indexed operateAddr, address indexed consensusAddr);
  event updated(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths);
  event addedMargin(address indexed operateAddr, uint256 margin, uint256 totalMargin);
  event deductedMargin(address indexed operateAddr, uint256 margin, uint256 totalMargin);
  event statusChanged(address indexed operateAddr, uint256 oldStatus, uint256 newStatus);
  event paramChange(string key, bytes value);

  /*********************** init **************************/
  function init() external onlyNotInit { //see @dev:init
    requiredMargin = INIT_REQUIRED_MARGIN;
    dues = INIT_DUES;
    roundInterval = _initRoundInterval();
    validatorCount = _initValidatorCount();
    maxCommissionChange = MAX_COMMISSION_CHANGE;
    roundTag = 7;
    alreadyInit = true;
  }
  
  /********************* ICandidateHub interface ****************************/
  /// Whether users can delegate on a validator candidate
  /// @param agent The operator address of the validator candidate
  /// @return true/false
  function canDelegate(address agent) external override view returns(bool) {
    uint256 indexPlus1 = operateMap[agent];
    if (indexPlus1 == 0) {
      return false;
    }
    uint index_ = indexPlus1 - 1;
    uint256 status = candidateSet[index_].status;
    return status == (status & ACTIVE_STATUS);
  }

  function isCandidate(address _addr) public view returns(bool) {
    return _isCandidate(_addr);
  }

  function _isCandidate(address _addr) internal virtual view returns(bool) {
    return operateMap[_addr] != 0;
  }


/* @product Jail a validator for some rounds and slash some amount of deposits
   @param operateAddress: The operator address of the validator
   @param round: The number of rounds to jail
   @param fine: The amount of deposits to slash
   @logic
      1. if the candidate's margin is greater or equal to the sum of the candidate's fine plus
         the global dues
          a. set the release round of the candidate to be the current round plus the
             'round' parameter (if the candidate has prior jail period - add to it
             the current 'round' parameter)
          b. subtract the fine's value from the candidate's margin
          c. and transfer the fine value to the SystemReward contarct

      2. Else:
          a. remove the candidate from internal structures, and
          b. transfer the candidate's margin eth value to the SystemReward contract
  */
  function jailValidator(address operateAddress, uint256 round, uint256 fine)
        external override onlyValidator nonReentrant { 
    
    uint256 indexPlus1 = operateMap[operateAddress];
    if (indexPlus1 == 0) {
      // not a candidate
      return;
    }
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];
    uint256 margin = c.margin;
    if (margin >= dues && margin - dues >= fine) {
      uint256 status = c.status | SET_JAIL;
      // update jailMap
      if (jailMap[operateAddress] > 0) {
        jailMap[operateAddress] = jailMap[operateAddress] + round;
      } else {
        jailMap[operateAddress] = roundTag + round;
      }
      // deduct margin
      uint256 totalMargin = margin - fine;
      c.margin = totalMargin;
      emit deductedMargin(operateAddress, fine, totalMargin);
      if (totalMargin < requiredMargin) {
        status = status | SET_MARGIN;
      }
      changeStatus(c, status);
      if (fine != 0) {
        Address.sendValue(payable(_systemReward()), fine);
      }
    } else {
      removeCandidate(indexPlus1);
      Address.sendValue(payable(_systemReward()), margin);    
      emit deductedMargin(operateAddress, margin, 0);
    }
  }

  function _initValidatorCount() internal virtual view returns(uint256) {
    return INIT_VALIDATOR_COUNT;
  }

  function _initRoundInterval() internal virtual view returns(uint256) {
    return INIT_ROUND_INTERVAL;
  }

  /// Simple return the round tag.
  function getRoundTag() external override view returns(uint256) {
    return roundTag;
  }

  /********************* External methods  ****************************/

/* @product The `turn round` workflow function
   @dev this method is called by Golang consensus engine at the end of a round
   @logic
      1. call ValidatorSet's distributeReward to distribute rewards for now-ending round
      2. distribute rewards to all BTC miners who delegated hash power for the now-ending round
      3. update the system's round tag to the current block.timestamp divided by roundInterval
      4. reset validator flags for all candidates.
      5. create a list of all valid candidates and use it to:
          a. fetch hash power delegated on list of the valid candidates, which is used to
             calculate hybrid score for validators in the new round
          b. calculate the hybrid score for all valid candidates and choose top ones to
             form the validator set of the new round. See the documentation of
             PledgeAgent.getHybridScore() for the details of the hybrid score calculation
      6. if a validator's hybrid score is zero - correct its commissionThousandths value to be 1000
      7. call ValidatorSet's updateValidatorSet() to set the new validators
      8. clean slash contract decreasing validators' accrued slash indicator points by the system's
         per-round point reduction rate
      9. notify PledgeAgent contract of the new round and the new validators
      10. remove validators from jail if their jailedRound is <= than the new roundTag
*/
  function turnRound() external onlyCoinbase onlyInit onlyZeroGasPrice {
    // distribute rewards for the about to end round
    address[] memory lastCandidates = IValidatorSet(_validatorSet()).distributeReward();

    // fetch BTC miners who delegated hash power in the about to end round;
    // and distribute rewards to them
    uint256 lastCandidateSize = lastCandidates.length;
    for (uint256 i = 0; i < lastCandidateSize; i++) {
      address[] memory miners = ILightClient(_lightClient()).getRoundMiners(roundTag-7, lastCandidates[i]);
      IPledgeAgent(_pledgeAgent()).distributePowerReward(lastCandidates[i], miners);
    }

    // update the system round tag; new round starts
    
    _updateRoundTag();    

    // reset validator flags for all candidates.
    uint256 candidateSize = candidateSet.length;
    uint256 validCount = 0;
    uint256[] memory statusList = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; i++) {
      statusList[i] = candidateSet[i].status & DEL_VALIDATOR;
      if (statusList[i] == SET_CANDIDATE) validCount++;
    }


    uint256[] memory powers;
    address[] memory candidates = new address[](validCount);
    uint256 j = 0;
    for (uint256 i = 0; i < candidateSize; i++) {
      if (statusList[i] == SET_CANDIDATE) {
        candidates[j++] = candidateSet[i].operateAddr;
      }
    }
    // fetch hash power delegated on list of candidates
    // which is used to calculate hybrid score for validators in the new round
    powers = ILightClient(_lightClient()).getRoundPowers(roundTag-7, candidates);

    // calculate the hybrid score for all valid candidates and
    // choose top ones to form the validator set of the new round
    (uint256[] memory scores, uint256 totalPower, uint256 totalCoin) =
      IPledgeAgent(_pledgeAgent()).getHybridScore(candidates, powers);
    address[] memory validatorList = getValidators(candidates, scores, validatorCount);

    // prepare arguments, and notify ValidatorSet contract
    uint256 totalCount = validatorList.length;
    address[] memory consensusAddrList = new address[](totalCount);
    address payable[] memory feeAddrList = new address payable[](totalCount);
    uint256[] memory commissionThousandthsList = new uint256[](totalCount);

    for (uint256 i = 0; i < totalCount; ++i) {
      uint256 indexPlus1 = operateMap[validatorList[i]];
      Candidate storage c = candidateSet[indexPlus1-1];
      consensusAddrList[i] = c.consensusAddr;
      feeAddrList[i] = c.feeAddr;
      if (scores[i] == 0) {
        commissionThousandthsList[i] = 1000;
      } else {
        commissionThousandthsList[i] = c.commissionThousandths;
      }
      statusList[indexPlus1-1] |= SET_VALIDATOR;
    }

    IValidatorSet(_validatorSet()).updateValidatorSet(validatorList, consensusAddrList, feeAddrList, commissionThousandthsList);

    // clean slash contract
    ISlashIndicator(_slash()).clean();

    // notify PledgeAgent contract
    IPledgeAgent(_pledgeAgent()).setNewRound(validatorList, totalPower, totalCoin, roundTag);

    // update validator jail status
    address opAddr; // avoiding 'Stack too deep'
    for (uint256 i = 0; i < candidateSize; i++) {
      opAddr = candidateSet[i].operateAddr;
      uint256 jailedRound = jailMap[opAddr];
      if (jailedRound != 0 && jailedRound <= roundTag) {
        statusList[i] = statusList[i] & DEL_JAIL;
        delete jailMap[opAddr];
      }
    }

    for (uint256 i = 0; i < candidateSize; i++) {
      changeStatus(candidateSet[i], statusList[i]);
    }
  }

  function _updateRoundTag() internal virtual {
    uint256 roundTimestamp = block.timestamp / roundInterval;
    require(roundTimestamp > roundTag, "not allowed to turn round, wait for more time");
    roundTag = roundTimestamp;
  }

  /****************** register/unregister ***************************/

/* @product Called by a non-validator address aiming to become a validator candidate on the Core blockchain
   @param consensusAddr: Consensus address configured on the validator node
   @param feeAddr: Fee address set to collect system rewards
   @param commissionThousandths: The commission fee taken by the validator, measured in thousandths (=promils)
   @logic:
        1. Apply the following verifications:
              a. Verify that the candidate limit of CANDIDATE_COUNT_LIMIT (=1000) was not reached
              b. No double-booking: Verifies that the candidate is not already registered
              c. Verify that the ether sum carried by this Tx is >= the global
                 requiredMargin value
              d. Verify that the commissionThousandths value is in the open range (0, 1000)
              e. Verify that the consensusAddr has not been registered before
              f. Verify that the fee address is valid
              g. Verify that the Tx sender is not jailed, or that his jail time has ended
                 before current roundTag
        2. And, if all of these tests have passed - register the validator candidate into the system
 */
  function register(address consensusAddr, address payable feeAddr, uint32 commissionThousandths)
    external payable
    onlyInit onlyIfNotCandidate onlyIfValueExceedsMargin onlyIfConsensusAddrNotExist(consensusAddr)
  {
    require(candidateSet.length <= CANDIDATE_COUNT_LIMIT, "maximum candidate size reached");
    require(commissionThousandths != 0 && commissionThousandths < 1000, "commissionThousandths should be in (0, 1000)");
    require(consensusAddr != address(0), "consensus address should not be zero");
    require(feeAddr != address(0), "fee address should not be zero");
    // check jail status
    require(jailMap[msg.sender] < roundTag, "it is in jail");

    uint256 status = SET_CANDIDATE;
    candidateSet.push(Candidate(msg.sender, consensusAddr, feeAddr, commissionThousandths, msg.value, status, roundTag, commissionThousandths));
    uint256 index = candidateSet.length;
    operateMap[msg.sender] = index;
    consensusMap[consensusAddr] = index;

    emit registered(msg.sender, consensusAddr, feeAddr, commissionThousandths, msg.value);
  }

  function getMargin(address _addr) external view returns(uint256) {
    uint256 indexPlus1 = operateMap[_addr];
    require(indexPlus1 > 0, "candidate does not exist");
    uint index_ = indexPlus1 - 1;
    return candidateSet[index_].margin;
  }

  /* @product Unregister the validator candidate role on Core blockchain
     @logic
      1. if candidate margin exceeds global dues value - transfer the difference to the
         candidate and the dues value to the system reward contract
      2. if candidate margin does not exceed global dues value - only transfer the margin
         value to the system reward contract
  */
  function unregister() external nonReentrant onlyInit onlyIfCandidate {
    uint256 indexPlus1 = operateMap[msg.sender];
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];
    uint status_ = _getCandidateStatus(index_);
    require(status_ == (status_ & UNREGISTER_STATUS), "candidate status is not cleared");
    uint256 margin = c.margin;

    removeCandidate(indexPlus1);

    if (margin > dues) {
      uint256 value = margin - dues;
      Address.sendValue(payable(msg.sender), value); //@dev:unsafe(reentry)
      Address.sendValue(payable(_systemReward()), uint256(dues));
    } else {
      Address.sendValue(payable(_systemReward()), margin);
    }
  }

  function _getCandidateStatus(uint index_) internal virtual view returns(uint256) {
    return candidateSet[index_].status;
  }

  /// Update validator candidate information
  /// @param consensusAddr Consensus address configured on the validator node
  /// @param feeAddr Fee address set to collect system rewards
  /// @param commissionThousandths The commission fee taken by the validator, measured in thousandths
  function update(address consensusAddr, address payable feeAddr, uint32 commissionThousandths) external onlyInit onlyIfCandidate {
    require(commissionThousandths != 0 && commissionThousandths < 1000, "commissionThousandths should in range (0, 1000)");
    require(consensusAddr != address(0), "consensus address should not be zero");
    require(feeAddr != address(0), "fee address should not be zero");
    uint256 indexPlus1 = operateMap[msg.sender];
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];
    uint256 commissionLastRoundValue = roundTag == c.commissionLastChangeRound
      ? c.commissionLastRoundValue
      : c.commissionThousandths;
    require(
      commissionThousandths + maxCommissionChange >= commissionLastRoundValue &&
        commissionLastRoundValue + maxCommissionChange >= commissionThousandths,
      "commissionThousandths out of adjustment range"
    );
    if (roundTag != c.commissionLastChangeRound) {
      c.commissionLastChangeRound = roundTag;
      c.commissionLastRoundValue = c.commissionThousandths;
    }
    if (c.consensusAddr != consensusAddr) {
      require(consensusMap[consensusAddr] == 0, "the consensus already exists");
      delete consensusMap[c.consensusAddr];
      c.consensusAddr = consensusAddr;
      consensusMap[consensusAddr] = indexPlus1;
    }
    c.feeAddr = feeAddr;
    c.commissionThousandths = commissionThousandths;
    emit updated(msg.sender, consensusAddr, feeAddr, commissionThousandths);
  }

  /// Refuse to accept delegate from others
  /// @dev Candidate will not be elected in this state
  function refuseDelegate() external onlyInit onlyIfCandidate {
    uint256 indexPlus1 = operateMap[msg.sender];
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];
    uint256 status = c.status | SET_INACTIVE;
    changeStatus(c, status);
  }

  /// Accept delegate from others
  function acceptDelegate() external onlyInit onlyIfCandidate {
    uint256 indexPlus1 = operateMap[msg.sender];
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];
    uint256 status = c.status & DEL_INACTIVE;
    changeStatus(c, status);
  }

/* @product Called by a candidate to add refundable deposits
   Motivation: Candidate will not be elected if there are not enough deposits
   @logic
      1. Tx eth value (must be >0) will be appended to candidate's margin value
      2. If the new candidate's margin value exceeds or is equal to the global requiredMargin
         value - the candidate will be promoted to be a validator
*/
  function addMargin() external payable onlyInit onlyIfCandidate {
    require(msg.value != 0, "value should not be zero");
    uint256 indexPlus1 = operateMap[msg.sender];
    uint index_ = indexPlus1 - 1;
    uint256 totalMargin = candidateSet[index_].margin + msg.value;
    candidateSet[index_].margin = totalMargin;
    emit addedMargin(msg.sender, msg.value, totalMargin);

    if (totalMargin >= requiredMargin) {
      Candidate storage c = candidateSet[index_];
      uint256 status = c.status & DEL_MARGIN;
      changeStatus(c, status);
    }
  }

  /*************************** internal methods ******************************/
  function changeStatus(Candidate storage c, uint256 newStatus) internal {
    uint256 oldStatus = c.status;
    if (oldStatus != newStatus) {
      c.status = newStatus;
      emit statusChanged(c.operateAddr, oldStatus, newStatus);
    }
  }

/* @product internal function for candidate removal, called by other CandidateHub
   functions in the flows of jailing or unregistering candidates
   @logic
      2. Candidate gets removed from contract internal structures
      3. No eth transfer takes place as part of this function
 */
  function removeCandidate(uint256 indexPlus1) internal {
    uint index_ = indexPlus1 - 1;
    Candidate storage c = candidateSet[index_];

    emit unregistered(c.operateAddr, c.consensusAddr);

    delete operateMap[c.operateAddr];
    delete consensusMap[c.consensusAddr];

    if (indexPlus1 != candidateSet.length) {
      candidateSet[index_] = candidateSet[candidateSet.length - 1];
      operateMap[candidateSet[index_].operateAddr] = indexPlus1;
      consensusMap[candidateSet[index_].consensusAddr] = indexPlus1;
    }
    candidateSet.pop();
  }

  /// Rank validator candidates on hybrid score using quicksort
  function getValidators(address[] memory candidateList, uint256[] memory scoreList, uint256 count) internal pure returns (address[] memory validatorList){
    uint256 candidateSize = candidateList.length;
    // quicksort by scores O(nlogk)
    uint256 l = 0;
    uint256 r = 0;
    if (count < candidateSize) {
      r = candidateSize - 1;
    } else {
      count = candidateSize;
    }
    while (l < r) {
      // partition
      uint256 ll = l;
      uint256 rr = r;
      address back = candidateList[ll];
      uint256 p = scoreList[ll];
      while (ll < rr) {
        while (ll < rr && scoreList[rr] < p) {
          rr = rr - 1;
        }
        candidateList[ll] = candidateList[rr];
        scoreList[ll] = scoreList[rr];
        while (ll < rr && scoreList[ll] >= p) {
          ll = ll + 1;
        }
        candidateList[rr] = candidateList[ll];
        scoreList[rr] = scoreList[ll];
      }
      candidateList[ll] = back;
      scoreList[ll] = p;
      uint256 mid = ll;
      // sub sort
      if (mid < count) {
        l = mid + 1;
      } else if (mid > count) {
        r = mid - 1;
      } else {
        break;
      }
    }
    uint256 d = candidateSize - count;
    if (d != 0) {
      assembly {
        mstore(candidateList, sub(mload(candidateList), d))
      }
    }
    return candidateList;
  }

  /*********************** Param update ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "requiredMargin")) {
      uint256 newRequiredMargin = BytesToTypes.bytesToUint256(32, value);
      if (newRequiredMargin <= dues) {
        revert OutOfBounds(key, newRequiredMargin, dues+1, type(uint256).max);
      }
      requiredMargin = newRequiredMargin;
    } else if (Memory.compareStrings(key, "dues")) {
      uint256 newDues = BytesToTypes.bytesToUint256(32, value);
      if (newDues == 0 || newDues >= requiredMargin) {
        revert OutOfBounds(key, newDues, 1, requiredMargin - 1);
      }
      dues = newDues;
    } else if (Memory.compareStrings(key, "validatorCount")) {
      uint256 newValidatorCount = BytesToTypes.bytesToUint256(32, value);
      if (newValidatorCount <= 5 || newValidatorCount >= 42) {
        revert OutOfBounds(key, newValidatorCount, 6, 41);
      }
      validatorCount = newValidatorCount;
    } else if (Memory.compareStrings(key, "maxCommissionChange")) {
      uint256 newMaxCommissionChange = BytesToTypes.bytesToUint256(32, value);
      if (newMaxCommissionChange == 0) {
        revert OutOfBounds(key, newMaxCommissionChange, 1, type(uint256).max);
      }
      maxCommissionChange = newMaxCommissionChange;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /// Get list of validator candidates
  /// @return List of operator addresses
  function getCandidates() external view returns (address[] memory) {
    uint256 candidateSize = candidateSet.length;
    address[] memory opAddrs = new address[](candidateSize);
    for (uint256 i = 0; i < candidateSize; i++) {
      opAddrs[i] = candidateSet[i].operateAddr;
    }
    return opAddrs;
  }

  /// Whether the input address is operator address of a validator candidate
  /// @param operateAddr Operator address of validator candidate
  /// @return true/false
  function isCandidateByOperate(address operateAddr) external view returns (bool) {
    return operateMap[operateAddr] != 0;
  }

  /// Whether the input address is consensus address a validator candidate
  /// @param consensusAddr Consensus address of validator candidate
  /// @return true/false
  function isCandidateByConsensus(address consensusAddr) external view returns (bool) {
    return consensusMap[consensusAddr] != 0;
  }

  /// Whether the validator is jailed
  /// @param operateAddr Operator address of validator
  /// @return true/false
  function isJailed(address operateAddr) external view returns (bool) {
    return jailMap[operateAddr] >= roundTag;
  }
}
