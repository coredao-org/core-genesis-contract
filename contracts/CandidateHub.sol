// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IValidatorSet.sol";
import "./interface/ICandidateHub.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ISlashIndicator.sol";
import "./interface/IStakeHub.sol";
import "./System.sol";
import "./lib/Address.sol";
import "./lib/SatoshiPlusHelper.sol";

/// This contract manages all validator candidates on Core blockchain
/// It also exposes the method `turnRound` for the consensus engine to execute the `turn round` workflow
contract CandidateHub is ICandidateHub, System, IParamSubscriber {

  uint256 public constant INIT_REQUIRED_MARGIN = 1e22;
  uint256 public constant INIT_DUES = 1e20;
  uint256 public constant INIT_VALIDATOR_COUNT = 21;
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

  modifier exist() {
    require(operateMap[msg.sender] != 0, "candidate does not exist");
    _;
  }

  /*********************** events **************************/
  event registered(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths, uint256 margin);
  event unregistered(address indexed operateAddr, address indexed consensusAddr);
  event updated(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths);
  event addedMargin(address indexed operateAddr, uint256 margin, uint256 totalMargin);
  event deductedMargin(address indexed operateAddr, uint256 margin, uint256 totalMargin);
  event statusChanged(address indexed operateAddr, uint256 oldStatus, uint256 newStatus);
  event turnedRound(uint256 round);

  /*********************** init **************************/
  function init() external onlyNotInit {
    requiredMargin = INIT_REQUIRED_MARGIN;
    dues = INIT_DUES;
    validatorCount = INIT_VALIDATOR_COUNT;
    maxCommissionChange = MAX_COMMISSION_CHANGE;
    roundTag = block.timestamp / SatoshiPlusHelper.ROUND_INTERVAL;
    alreadyInit = true;
  }
  
  /********************* ICandidateHub interface ****************************/
  /// Whether users can delegate on a validator candidate
  /// @param candidate The operator address of the validator candidate
  /// @return true/false
  function canDelegate(address candidate) external override view returns(bool) {
    uint256 index = operateMap[candidate];
    if (index == 0) {
      return false;
    }
    uint256 status = candidateSet[index - 1].status;
    return status == (status & ACTIVE_STATUS);
  }

  /// Whether the candidate is a validator
  /// @param candidate The operator address of the validator candidate
  /// @return true/false
  function isValidator(address candidate) external override view returns(bool) {
    uint256 index = operateMap[candidate];
    if (index == 0) {
      return false;
    }
    uint256 status = candidateSet[index - 1].status;
    return SET_VALIDATOR == (status & SET_VALIDATOR);  
  }

  /// Whether the input address is operator address of a validator candidate 
  /// @param operateAddr Operator address of validator candidate
  /// @return true/false
  function isCandidateByOperate(address operateAddr) external override view returns (bool) {
    return operateMap[operateAddr] != 0;
  }

  /// Jail a validator for some rounds and slash some amount of deposits
  /// @param operateAddress The operator address of the validator
  /// @param round The number of rounds to jail
  /// @param fine The amount of deposits to slash
  function jailValidator(address operateAddress, uint256 round, uint256 fine) external override onlyValidator {
    uint256 index = operateMap[operateAddress];
    if (index == 0) return;

    Candidate storage c = candidateSet[index - 1];
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
        payable(SYSTEM_REWARD_ADDR).transfer(fine);
      }
    } else {
      removeCandidate(index);

      payable(SYSTEM_REWARD_ADDR).transfer(margin);
      emit deductedMargin(operateAddress, margin, 0);
    }
  }

  /// Simple return the round tag.
  function getRoundTag() external override view returns(uint256) {
    return roundTag;
  }

  /********************* External methods  ****************************/
  /// The `turn round` workflow
  /// @dev this method is called by Golang consensus engine at the end of a round
  function turnRound() external onlyCoinbase onlyInit onlyZeroGasPrice {
    
    // distribute rewards for the about to end round
    IValidatorSet(VALIDATOR_CONTRACT_ADDR).distributeReward(roundTag);

    // update the system round tag; new round starts
    
    uint256 roundTimestamp = block.timestamp / SatoshiPlusHelper.ROUND_INTERVAL;
    require(roundTimestamp > roundTag, "not allowed to turn round, wait for more time");
    roundTag = roundTimestamp;
    

    // reset validator flags for all candidates.
    uint256 candidateSize = candidateSet.length;
    uint256 validCount = 0;
    uint256[] memory statusList = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; i++) {
      statusList[i] = candidateSet[i].status & DEL_VALIDATOR;
      if (statusList[i] == SET_CANDIDATE) validCount++;
    }

    address[] memory candidates = new address[](validCount);
    uint256 j = 0;
    for (uint256 i = 0; i < candidateSize; i++) {
      if (statusList[i] == SET_CANDIDATE) {
        candidates[j++] = candidateSet[i].operateAddr;
      }
    }

    // calculate the hybrid score for all valid candidates and 
    // choose top ones to form the validator set of the new round
    (uint256[] memory scores) =
      IStakeHub(STAKE_HUB_ADDR).getHybridScore(candidates, roundTag);
    address[] memory validatorList = getValidators(candidates, scores, validatorCount);

    // prepare arguments, and notify ValidatorSet contract
    uint256 totalCount = validatorList.length;
    address[] memory consensusAddrList = new address[](totalCount);
    address payable[] memory feeAddrList = new address payable[](totalCount);
    uint256[] memory commissionThousandthsList = new uint256[](totalCount);

    for (uint256 i = 0; i < totalCount; ++i) {
      uint256 index = operateMap[validatorList[i]];
      Candidate storage c = candidateSet[index - 1];
      consensusAddrList[i] = c.consensusAddr;
      feeAddrList[i] = c.feeAddr;
      if (scores[i] == 0) {
        commissionThousandthsList[i] = 1000;
      } else {
        commissionThousandthsList[i] = c.commissionThousandths;
      }
      statusList[index - 1] |= SET_VALIDATOR;
    }

    IValidatorSet(VALIDATOR_CONTRACT_ADDR).updateValidatorSet(validatorList, consensusAddrList, feeAddrList, commissionThousandthsList);

    // clean slash contract
    ISlashIndicator(SLASH_CONTRACT_ADDR).clean();

    // notify StakeHub contract
    IStakeHub(STAKE_HUB_ADDR).setNewRound(validatorList, roundTag);

    // update validator jail status
    for (uint256 i = 0; i < candidateSize; i++) {
      address opAddr = candidateSet[i].operateAddr;
      uint256 jailedRound = jailMap[opAddr];
      if (jailedRound != 0 && jailedRound <= roundTag) {
        statusList[i] = statusList[i] & DEL_JAIL;
        delete jailMap[opAddr];
      }
    }

    for (uint256 i = 0; i < candidateSize; i++) {
      changeStatus(candidateSet[i], statusList[i]);
    }
    emit turnedRound(roundTag);
  }

  /****************** register/unregister ***************************/
  /// Register as a validator candidate on Core blockchain
  /// @param consensusAddr Consensus address configured on the validator node
  /// @param feeAddr Fee address set to collect system rewards
  /// @param commissionThousandths The commission fee taken by the validator, measured in thousandths
  function register(address consensusAddr, address payable feeAddr, uint32 commissionThousandths)
    external payable
    onlyInit
  {
    require(candidateSet.length <= CANDIDATE_COUNT_LIMIT, "maximum candidate size reached");
    require(operateMap[msg.sender] == 0, "candidate already exists");
    require(msg.value >= requiredMargin, "deposit is not enough");
    require(commissionThousandths != 0 && commissionThousandths < 1000, "commissionThousandths should be in (0, 1000)");
    require(consensusMap[consensusAddr] == 0, "consensus already exists");
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

  /// Unregister the validator candidate role on Core blockchain
  function unregister() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
    require(c.status == (c.status & UNREGISTER_STATUS), "candidate status is not cleared");
    uint256 margin = c.margin;

    removeCandidate(index);

    if (margin > dues) {
      uint256 value = margin - dues;
      Address.sendValue(payable(msg.sender), value);
      payable(SYSTEM_REWARD_ADDR).transfer(uint256(dues));
    } else {
      payable(SYSTEM_REWARD_ADDR).transfer(margin);
    }
  }

  /// Update validator candidate information
  /// @param consensusAddr Consensus address configured on the validator node
  /// @param feeAddr Fee address set to collect system rewards
  /// @param commissionThousandths The commission fee taken by the validator, measured in thousandths  
  function update(address consensusAddr, address payable feeAddr, uint32 commissionThousandths) external onlyInit exist{
    require(commissionThousandths != 0 && commissionThousandths < 1000, "commissionThousandths should in range (0, 1000)");
    require(consensusAddr != address(0), "consensus address should not be zero");
    require(feeAddr != address(0), "fee address should not be zero");
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
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
      consensusMap[consensusAddr] = index;
    }
    c.feeAddr = feeAddr;
    c.commissionThousandths = commissionThousandths;
    emit updated(msg.sender, consensusAddr, feeAddr, commissionThousandths);
  }

  /// Refuse to accept delegate from others
  /// @dev Candidate will not be elected in this state
  function refuseDelegate() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
    uint256 status = c.status | SET_INACTIVE;
    changeStatus(c, status);
  }

  /// Accept delegate from others
  function acceptDelegate() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
    uint256 status = c.status & DEL_INACTIVE;
    changeStatus(c, status);
  }

  /// Add refundable deposits
  /// @dev Candidate will not be elected if there are not enough deposits
  function addMargin() external payable onlyInit exist {
    require(msg.value != 0, "value should not be zero");
    uint256 index = operateMap[msg.sender];
    uint256 totalMargin = candidateSet[index - 1].margin + msg.value;
    candidateSet[index - 1].margin = totalMargin;
    emit addedMargin(msg.sender, msg.value, totalMargin);

    if (totalMargin >= requiredMargin) {
      Candidate storage c = candidateSet[index - 1];
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

  function removeCandidate(uint256 index) internal {
    Candidate storage c = candidateSet[index - 1];

    emit unregistered(c.operateAddr, c.consensusAddr);

    delete operateMap[c.operateAddr];
    delete consensusMap[c.consensusAddr];

    if (index != candidateSet.length) {
      candidateSet[index-1] = candidateSet[candidateSet.length - 1];
      operateMap[candidateSet[index-1].operateAddr] = index;
      consensusMap[candidateSet[index-1].consensusAddr] = index;
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
      revert UnsupportedGovParam(key);
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

  /// Get init validator count
  /// @return count of init validator
  function getInitValidatorCount() external override pure returns(uint256) {
    return INIT_VALIDATOR_COUNT;
  }
}