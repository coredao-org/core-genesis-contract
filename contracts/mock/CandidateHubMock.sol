pragma solidity 0.8.4;

import "../CandidateHub.sol";
import "../lib/BytesToTypes.sol";
import "../lib/Memory.sol";
import "../interface/IValidatorSet.sol";
import "../interface/ICandidateHub.sol";
import "../interface/IParamSubscriber.sol";
import "../interface/ISlashIndicator.sol";
import "../interface/IStakeHub.sol";
import "../interface/IPledgeAgent.sol";
import "../interface/ILightClient.sol";
import "./interface/IPledgeAgentMock.sol";
import "./interface/ILightClientMock.sol";
import "./interface/IValidatorSetMock.sol";
import "../System.sol";
import "../lib/Address.sol";
import "../lib/SatoshiPlusHelper.sol";

contract CandidateHubMock is CandidateHub {
    uint256[] public scores;
    uint256 public totalPower;
    uint256 public totalCoin;

    function developmentInit() external {
        roundInterval = 1;
        requiredMargin = requiredMargin / 1e16;
        dues = dues / 1e16;
        maxCommissionChange = 100;
        roundTag = 7;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }
    function setValidatorCount(uint256 value) external {
        validatorCount = value;
    }
    function getCanDelegateCandidates() external view returns(address[] memory) {
        uint count;
        for (uint256 i = 0; i < candidateSet.length; i++) {
            if (this.canDelegate(candidateSet[i].operateAddr)) {
                count++;
            }
        }
        address[] memory opAddrs = new address[](count);
        uint n;
        for (uint256 i=0; i<candidateSet.length; i++) {
            if (this.canDelegate(candidateSet[i].operateAddr)) {
                opAddrs[n] = candidateSet[i].operateAddr;
                n++;
            }
        }
        return opAddrs;
    }

    function getRefusedCandidates() external view returns(address[] memory) {
        uint count;
        for (uint256 i = 0; i < candidateSet.length; i++) {
            if ((candidateSet[i].status & SET_INACTIVE) == SET_INACTIVE) {
                count++;
            }
        }
        address[] memory opAddrs = new address[](count);
        uint n;
        for (uint256 i=0; i<candidateSet.length; i++) {
            if ((candidateSet[i].status & SET_INACTIVE) == SET_INACTIVE) {
                opAddrs[n] = candidateSet[i].operateAddr;
                n++;
            }
        }
        return opAddrs;
    }

    function setJailMap(address k, uint256 v) public {
    jailMap[k] = v;
  }

  function setCandidateMargin(address k, uint256 v) public {
    candidateSet[operateMap[k] - 1].margin = v;
  }

  function setCandidateStatus(address k, uint256 v) public {
    candidateSet[operateMap[k] - 1].status = v;
  }

    function setTurnroundFailed(bool value) public {
      turnroundFailed = value;
  }
    function setRoundInterval(uint256 value) public {
      roundInterval = value;
  }


  function getCandidate(address k) public view returns (Candidate memory) {
    return candidateSet[operateMap[k] - 1];
  }

 function getScoreMock(address[] memory candidates, uint256 round) external {
    scores = IStakeHub(STAKE_HUB_ADDR).getHybridScore(
      candidates,
      round
    );
  }

  function getScores() external view returns (uint256[] memory) {
    return scores;
  }

  function getValidatorsMock(
    address[] memory candidateList,
    uint256[] memory scoreList,
    uint256 count
  ) public pure returns (address[] memory validatorList) {
    return getValidators(candidateList, scoreList, count);
  }

  function cleanMock() public {
    ISlashIndicator(SLASH_CONTRACT_ADDR).clean();
  }

  function registerMock(
    address operateAddr,
    address consensusAddr,
    address payable feeAddr,
    uint32 commissionThousandths
  ) external payable onlyInit {
    uint256 status = SET_CANDIDATE;
    candidateSet.push(
      Candidate(
        operateAddr,
        consensusAddr,
        feeAddr,
        commissionThousandths,
        msg.value,
        status,
        roundTag,
        commissionThousandths
      )
    );
    uint256 index = candidateSet.length;
    operateMap[operateAddr] = index;
    consensusMap[consensusAddr] = index;

    emit registered(operateAddr, consensusAddr, feeAddr, commissionThousandths, msg.value);
  }
    /********************* External methods  ****************************/
  /// The `turn round` workflowf
  /// @dev this method is called by Golang consensus engine at the end of a round
  function turnRoundOld() external onlyCoinbase onlyInit onlyZeroGasPrice {
    
      if (turnroundFailed == true){
      require(false, "turnRound failed");
    }
    
    // distribute rewards for the about to end round
    address[] memory lastCandidates = IValidatorSetMock(VALIDATOR_CONTRACT_ADDR).distributeRewardOld();

    // fetch BTC miners who delegated hash power in the about to end round; 
    // and distribute rewards to them
    uint256 lastCandidateSize = lastCandidates.length;
    for (uint256 i = 0; i < lastCandidateSize; i++) {
      address[] memory miners = ILightClient(LIGHT_CLIENT_ADDR).getRoundMiners(roundTag-7, lastCandidates[i]);
      IPledgeAgentMock(PLEDGE_AGENT_ADDR).distributePowerRewardOld(lastCandidates[i], miners);
    }

    // update the system round tag; new round starts
    
    if (controlRoundTimeTag == false) {
    
    uint256 roundTimestamp = block.timestamp / roundInterval;
    require(roundTimestamp > roundTag, "not allowed to turn round, wait for more time");
    roundTag = roundTimestamp;
    
    } else {
        roundTag++;
    }
    

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
    powers = ILightClientMock(LIGHT_CLIENT_ADDR).getRoundPowersMock(roundTag-7, candidates);

    // calculate the hybrid score for all valid candidates and 
    // choose top ones to form the validator set of the new round
    (uint256[] memory scores) =
      IPledgeAgentMock(PLEDGE_AGENT_ADDR).getHybridScoreOld(candidates, powers, roundTag);
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

    // notify PledgeAgent contract
    IPledgeAgentMock(PLEDGE_AGENT_ADDR).setNewRoundOld(validatorList, roundTag);

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
  }
}
