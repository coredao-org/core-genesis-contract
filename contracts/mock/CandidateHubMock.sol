// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../CandidateHub.sol";
import "../registry/Registry.sol";

contract CandidateHubMock is CandidateHub {
    uint256[] public scores;
    uint256 public totalPower;
    uint256 public totalCoin;

    address private blockcoinbase;
    uint private txgasprice;

    constructor(Registry registry, uint256 roundInterval_, uint256 validatorCount) 
        CandidateHub(registry, roundInterval_, validatorCount) {
    }

    function developmentInit() external {
        roundInterval = 1;
        requiredMargin = requiredMargin / 1e16;
        dues = dues / 1e16;
        maxCommissionChange = 100;
        roundTag = 7;
    }

    function turnRound() public override {
      txgasprice = 0;
      blockcoinbase = msg.sender;
      super.turnRound();
    }

    function _gasprice() internal override view returns (uint) {
      return txgasprice;
    }

    function _coinbase() internal override view returns (address) {
      return blockcoinbase;
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

  function getCandidate(address k) public view returns (Candidate memory) {
    return candidateSet[operateMap[k] - 1];
  }

  function getScoreMock(address[] memory candidates, uint256[] memory powers) external {
    (scores, totalPower, totalCoin) = safe_pledgeAgent().getHybridScore(
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
    safe_slashIndicator().clean();
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
}
