pragma solidity 0.6.12;
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IValidatorSet.sol";
import "./interface/ICandidateHub.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ISlashIndicator.sol";
import "./System.sol";
import "./lib/SafeMath.sol";

contract CandidateHub is ICandidateHub, System, IParamSubscriber {
  using SafeMath for uint256;

  int256 public constant INIT_REQUIRED_MARGIN = 1e22;
  int256 public constant INIT_DUES = 1e18;
  uint256 public constant INIT_ROUND_INTERVAL = 1800;
  uint256 public constant INIT_VALIDATOR_COUNT = 42;
  uint256 public constant MAX_COMMISSION_CHANGE = 10;

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

  int256 public requiredMargin;
  int256 public dues;

  uint256 public roundInterval;
  uint256 public validatorCount;
  uint256 public maxCommissionChange;

  // candidate list.
  Candidate[] public candidateSet;
  // key is the `operateAddr` of `Candidate`,
  // value is the index of `candidateSet`.
  mapping(address => uint256) public operateMap;

  // key is the `consensusAddr`,
  // value is the index of `candidateSet`.
  mapping(address => uint256) consensusMap;

  // key is consensus address of validator,
  // value is release round
  mapping(address => uint256) public jailMap;

  uint256 public roundTag;
  

  struct Candidate {
    address operateAddr;
    address consensusAddr;
    address payable feeAddr;
    uint256 commissionThousandths;
    int256 margin;
    uint256 status;
    uint256 commissionLastChangeRound;
    uint256 commissionLastRoundValue;
  }

  modifier exist() {
    require(operateMap[msg.sender] > 0, "candidate does not exist");
    _;
  }

  event registered(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths, int256 margin);
  event unregistered(address indexed operateAddr, address indexed consensusAddr);
  event updated(address indexed operateAddr, address indexed consensusAddr, address indexed feeAddress, uint256 commissionThousandths);
  event addedMargin(address indexed operateAddr, int256 margin, int256 totalMargin);
  event deductedMargin(address indexed operateAddr, int256 margin, int256 totalMargin);
  event statusChanged(address indexed operateAddr, uint256 oldStatus, uint256 newStatus);
  event paramChange(string key, bytes value);

  function init() external onlyNotInit {
    requiredMargin = INIT_REQUIRED_MARGIN;
    dues = INIT_DUES;
    roundInterval = INIT_ROUND_INTERVAL;
    validatorCount = INIT_VALIDATOR_COUNT;
    maxCommissionChange = MAX_COMMISSION_CHANGE;
    roundTag = 1;
    alreadyInit = true;
  }

  

  /********************* ICandidateHub interface ****************************/
  function canDelegate(address agent) external override view returns(bool) {
    uint256 index = operateMap[agent];
    if (index == 0) {
      return false;
    }
    uint256 status = candidateSet[index - 1].status;
    return status == (status & ACTIVE_STATUS);
  }

  function jailValidator(address operateAddress, uint256 round, int256 fine) external override onlyValidator {
    if (fine < 0) return;
    
    uint256 index = operateMap[operateAddress];
    if (index == 0) return;

    Candidate storage c = candidateSet[index - 1];

    uint256 status = c.status | SET_JAIL;
    // store in jail
    uint256 jailRound = roundTag + round;
    if (jailRound < roundTag) jailMap[operateAddress] = type(uint256).max;
    else jailMap[operateAddress] = jailRound;
    // deduct margin
    int256 totalMargin = c.margin - fine;
    candidateSet[index - 1].margin = totalMargin;
    emit deductedMargin(operateAddress, fine, totalMargin);
    if (totalMargin < requiredMargin) {
      status = status | SET_MARGIN;
    }
    changeStatus(c, status);
  }

  /********************* External methods  ****************************/
  function turnRound() external onlyCoinbase onlyInit onlyZeroGasPrice {

    // distribute last round.
    IValidatorSet(VALIDATOR_CONTRACT_ADDR).distributeReward();

    bytes20[] memory lastMiners = ILightClient(LIGHT_CLIENT_ADDR).getRoundMiners(roundTag-7);

    // oncePerRound
    
    uint256 roundTimestamp = block.timestamp / roundInterval;
    require(roundTimestamp > roundTag, "can not turn round twice in one round");
    roundTag = roundTimestamp;
    

    // step 1. get round power.
    (bytes20[] memory miners, uint256[] memory powers) = ILightClient(LIGHT_CLIENT_ADDR).getRoundPowers(roundTag-7);

    // step 2. update slashed votingPower
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

    // step 3. calc the terminal validatorsSet 
    (uint256[] memory integrals, uint256 totalPower, uint256 totalCoin) =
      IPledgeAgent(PLEDGE_AGENT_ADDR).getIntegral(candidates, lastMiners, miners, powers);
    address[] memory validatorList = getValidators(candidates, integrals, validatorCount);

    // step 4. prepare arguments, and notify ValidatorSet contract.
    uint256 totalCount = validatorList.length;
    address[] memory consensusAddrList = new address[](totalCount);
    address payable[] memory feeAddrList = new address payable[](totalCount);
    uint256[] memory commissionThousandthsList = new uint256[](totalCount);

    for (uint256 i = 0; i < totalCount; ++i) {
      uint256 index = operateMap[validatorList[i]];
      Candidate storage c = candidateSet[index - 1];
      consensusAddrList[i] = c.consensusAddr;
      feeAddrList[i] = c.feeAddr;
      if (integrals[i] == 0) {
        commissionThousandthsList[i] = 1000;
      } else {
        commissionThousandthsList[i] = c.commissionThousandths;
      }
      statusList[index - 1] |= SET_VALIDATOR;
    }

    IValidatorSet(VALIDATOR_CONTRACT_ADDR).updateValidatorSet(validatorList, consensusAddrList, feeAddrList, commissionThousandthsList);

    // clean slash contract
    ISlashIndicator(SLASH_CONTRACT_ADDR).clean();

    IPledgeAgent(PLEDGE_AGENT_ADDR).setNewRound(validatorList, totalPower, totalCoin, roundTag);
    for (uint256 i = 0; i < candidateSize; i++) {
      address opAddr = candidateSet[i].operateAddr;
      uint256 jailedRound = jailMap[opAddr];
      if (jailedRound > 0 && jailedRound <= roundTag) {
        statusList[i] = statusList[i] & DEL_JAIL;
        delete jailMap[opAddr];
      }
    }

    for (uint256 i = 0; i < candidateSize; i++) {
      changeStatus(candidateSet[i], statusList[i]);
    }
  }

  /****************** register/unregister ***************************/
  function register(address consensusAddr, address payable feeAddr, uint32 commissionThousandths)
    external payable
    onlyInit
  {
    require(operateMap[msg.sender] == 0, "candidate already exists");
    require(int256(msg.value) >= requiredMargin, "deposit is not enough");
    require(commissionThousandths > 0 && commissionThousandths < 1000, "commissionThousandths should in range (0, 1000)");
    require(consensusMap[consensusAddr] == 0, "consensus already exists");
    require(!isContract(consensusAddr), "contract is not allowed to be consensus address");
    require(!isContract(feeAddr), "contract is not allowed to be fee address");
    // check jail.
    require(jailMap[msg.sender] < roundTag, "it is in jail");

    uint256 status = SET_CANDIDATE;
    candidateSet.push(Candidate(msg.sender, consensusAddr, feeAddr, commissionThousandths, int256(msg.value), status, roundTag, commissionThousandths));
    uint256 index = candidateSet.length;
    operateMap[msg.sender] = index;
    consensusMap[consensusAddr] = index;

    emit registered(msg.sender, consensusAddr, feeAddr, commissionThousandths, int256(msg.value));
  }

  function unregister() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate memory c = candidateSet[index - 1];
    require(c.status == (c.status & UNREGISTER_STATUS), "candidate status is not cleared");
    require(c.margin >= dues, "margin is not enough to cover dues");

    delete operateMap[msg.sender];
    delete consensusMap[c.consensusAddr];

    if (index != candidateSet.length) {
      candidateSet[index-1] = candidateSet[candidateSet.length - 1];
      operateMap[candidateSet[index-1].operateAddr] = index;
      consensusMap[candidateSet[index-1].consensusAddr] = index;
    }
    candidateSet.pop();

    address payable systemPayable = address(uint160(SYSTEM_REWARD_ADDR));
    uint256 value = uint256(c.margin - dues);
    if (value > 0)  msg.sender.transfer(value);
    systemPayable.transfer(uint256(dues));
    emit unregistered(msg.sender, c.consensusAddr);

    IPledgeAgent(PLEDGE_AGENT_ADDR).inactiveAgent(msg.sender);
  }

  function update(address consensusAddr, address payable feeAddr, uint32 commissionThousandths) external onlyInit exist{
    require(commissionThousandths > 0 && commissionThousandths < 1000, "commissionThousandths should in range (0, 1000)");
    require(!isContract(consensusAddr), "contract is not allowed to be consensus address");
    require(!isContract(feeAddr), "contract is not allowed to be fee address");
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
      c.commissionLastRoundValue = commissionThousandths;
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

  function refuseDelegate() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
    uint256 status = c.status | SET_INACTIVE;
    changeStatus(c, status);
  }

  function acceptDelegate() external onlyInit exist {
    uint256 index = operateMap[msg.sender];
    Candidate storage c = candidateSet[index - 1];
    uint256 status = c.status & DEL_INACTIVE;
    changeStatus(c, status);
  }

  function addMargin() external payable onlyInit exist {
    require(msg.value > 0, "value should be not nil");
    uint256 index = operateMap[msg.sender];
    int256 totalMargin = candidateSet[index - 1].margin + int256(msg.value);
    candidateSet[index - 1].margin = totalMargin;
    emit addedMargin(msg.sender, int256(msg.value), totalMargin);

    if (totalMargin >= requiredMargin) {
      Candidate storage c = candidateSet[index - 1];
      uint256 status = c.status & DEL_MARGIN;
      changeStatus(c, status);
    }
  }

  /*************************** inner methods ******************************/
  function changeStatus(Candidate storage c, uint256 newStatus) internal {
    uint256 oldStatus = c.status;
    if (oldStatus != newStatus) {
      if (oldStatus | ACTIVE_STATUS == ACTIVE_STATUS && newStatus | ACTIVE_STATUS != ACTIVE_STATUS) {
        IPledgeAgent(PLEDGE_AGENT_ADDR).inactiveAgent(c.operateAddr);
      }
      c.status = newStatus;
      statusChanged(c.operateAddr, oldStatus, newStatus);
    }
  }

  function getValidators(address[] memory candidateList, uint256[] memory integralList, uint256 count) internal pure returns (address[] memory validatorList){
    uint256 candidateSize = candidateList.length;
    // quick order by totalDeposit O(nlogk)
    uint256 l = 0;
    uint256 r = 0;
    if (count < candidateSize) {
      r = candidateSize - 1;
    } else {
      count = candidateSize;
    }
    while (l < r) {
      // partition candidateList
      uint256 ll = l;
      uint256 rr = r;
      address back = candidateList[ll];
      uint256 p = integralList[ll];
      while (ll < rr) {
        while (ll < rr && integralList[rr] < p) {
          rr = rr - 1;
        }
        candidateList[ll] = candidateList[rr];
        integralList[ll] = integralList[rr];
        while (ll < rr && integralList[ll] >= p) {
          ll = ll + 1;
        }
        candidateList[rr] = candidateList[ll];
        integralList[rr] = integralList[ll];
      }
      candidateList[ll] = back;
      integralList[ll] = p;
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
    if (d > 0) {
      assembly {
        mstore(candidateList, sub(mload(candidateList), d))
      }
    }
    return candidateList;
  }

  /*********************** Param update ********************************/
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "requiredMargin")) {
      require(value.length == 32, "length of requiredMargin mismatch");
      int256 newRequiredMargin = BytesToTypes.bytesToInt256(32, value);
      require(newRequiredMargin > dues, "the requiredMargin out of range");
      requiredMargin = newRequiredMargin;
    } else if (Memory.compareStrings(key, "dues")) {
      require(value.length == 32, "length of dues mismatch");
      int256 newDues = BytesToTypes.bytesToInt256(32, value);
      require(newDues > 0 && newDues < requiredMargin, "the dues out of range");
      dues = newDues;
    } else if (Memory.compareStrings(key, "validatorCount")) {
      require(value.length == 32, "length of validatorCount mismatch");
      uint256 newValidatorCount = BytesToTypes.bytesToUint256(32, value);
      require(newValidatorCount > 5 && newValidatorCount < 42, "the newValidatorCount out of range");
      validatorCount = newValidatorCount;
    } else if (Memory.compareStrings(key, "maxCommissionChange")) {
      require(value.length == 32, "length of maxCommissionChange mismatch");
      uint256 newMaxCommissionChange = BytesToTypes.bytesToUint256(32, value);
      require(newMaxCommissionChange > 0, "the newMaxCommissionChange out of range");
      maxCommissionChange = newMaxCommissionChange;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  function getCandidates() external view returns (address[] memory) {
    address[] memory opAddrs = new address[](candidateSet.length);
    for (uint256 i = 0; i < candidateSet.length; i++) {
      opAddrs[i] = candidateSet[i].operateAddr;
    }
    return opAddrs;
  }

  function isCandidateByOperate(address operateAddr) external view returns (bool) {
    return operateMap[operateAddr] > 0;
  }

  function isCandidateByConsensus(address consensusAddr) external view returns (bool) {
    return consensusMap[consensusAddr] > 0;
  }

  function isJailed(address operateAddr) external view returns (bool) {
    return jailMap[operateAddr] >= roundTag;
  }
}
