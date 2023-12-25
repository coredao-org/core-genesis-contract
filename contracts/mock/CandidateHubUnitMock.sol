// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../CandidateHub.sol";
import {BaseMock} from "./BaseMock.sol";


contract CandidateHubUnitMock is CandidateHub , BaseMock {
  uint256[] public scores;
  uint256 public totalPower;
  uint256 public totalCoin;

  function developmentInit() external {
    requiredMargin = 1e19;
    roundInterval = 1;
    roundTag = 7;
    maxCommissionChange = 100;
  }

  function setRoundTimeTag(uint256 value) external {
    roundTag = value;
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

  function getCandidate(address k) public view returns (Candidate memory) {
    return candidateSet[operateMap[k] - 1];
  }

  function getScoreMock(address[] memory candidates, uint256[] memory powers) external {
    (scores, totalPower, totalCoin) = IPledgeAgent(_pledgeAgent()).getHybridScore(
      candidates,
      powers
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
    ISlashIndicator(_slash()).clean();
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


    function _isBlockProducer() internal override pure returns (bool) {
        return true;
    }

    function _zeroGasPrice() internal override pure returns (bool) {
        return true;
    }


    // -- address mock overrides --

    function _validatorSet() view internal override returns (address) {
        return _notNull(s_validatorSet);
    }

    function _slash() view internal override returns (address) {
        return _notNull(s_slash);
    }

    function _systemReward() view internal override returns (address) {
        return _notNull(s_systemReward);   
    }

    function _lightClient() view internal override returns (address) {
        return _notNull(s_lightClient); 
    }

    function _relayerHub() view internal override returns (address) {
        return _notNull(s_relayerHub);  
    }

    function _candidateHub() view internal override returns (address) {
        return _notNull(s_candidateHub);  
    }

    function _govHub() view internal override returns (address) {
        return _notNull(s_govHub);
    }

    function _pledgeAgent() view internal override returns (address) {
        return _notNull(s_pledgeAgent);  
    }

    function _burn() view internal override returns (address) {
        return _notNull(s_burn);  
    }

    function _foundation() view internal override returns (address) {
        return _notNull(s_foundation);  
    }    
}

