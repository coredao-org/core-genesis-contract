// SPDX-License-Identifier: Apache2.0
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
import "../System.sol";
import "../lib/Address.sol";
import "../lib/SatoshiPlusHelper.sol";

contract CandidateHubMock is CandidateHub {
    bool public controlRoundTimeTag = false;
    bool public turnroundFailed = false;
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

    function setControlRoundTimeTag(bool value) external {
        controlRoundTimeTag = value;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function setDues(uint value) external {
        dues = value;
    }

    function mockRegister(uint256 value) external {
        for (uint256 i = 0; i < value; i++) {
            candidateSet.push();
        }
    }


    function setValidatorCount(uint256 value) external {
        validatorCount = value;
    }

    function getCanDelegateCandidates() external view returns (address[] memory) {
        uint count;
        for (uint256 i = 0; i < candidateSet.length; i++) {
            if (this.canDelegate(candidateSet[i].operateAddr)) {
                count++;
            }
        }
        address[] memory opAddrs = new address[](count);
        uint n;
        for (uint256 i = 0; i < candidateSet.length; i++) {
            if (this.canDelegate(candidateSet[i].operateAddr)) {
                opAddrs[n] = candidateSet[i].operateAddr;
                n++;
            }
        }
        return opAddrs;
    }

    function getRefusedCandidates() external view returns (address[] memory) {
        uint count;
        for (uint256 i = 0; i < candidateSet.length; i++) {
            if ((candidateSet[i].status & SET_INACTIVE) == SET_INACTIVE) {
                count++;
            }
        }
        address[] memory opAddrs = new address[](count);
        uint n;
        for (uint256 i = 0; i < candidateSet.length; i++) {
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

    function getConsensusMap(address consensusAddr) public view returns (uint256) {
        return consensusMap[consensusAddr];
    }

    function getScoreMock(address[] memory candidates, uint256 round) external returns (uint256[] memory hybridScores) {
        hybridScores = IStakeHub(STAKE_HUB_ADDR).getHybridScore(
            candidates,
            round
        );
        return hybridScores;
    }

    function getScores() external view returns (uint256[] memory) {
        return scores;
    }

    function getValidatorsMock(
        address[] memory candidateList,
        uint256[] memory scoreList,
        uint256 count,
        uint256 sortedCount
    ) public pure returns (address[] memory validatorList) {
        return getValidators(candidateList, scoreList, count, sortedCount);
    }
    function getAlternateCountMock(
        uint256 maxAlternateCount,
        uint256 count,
        uint256 candidateSize
    ) public pure returns (uint256) {
        return getAlternateCount(maxAlternateCount, count, candidateSize);
    }


    function cleanMock() public {
        ISlashIndicator(SLASH_CONTRACT_ADDR).clean();
    }

    function registerMock(
        address operateAddr,
        address consensusAddr,
        address payable feeAddr,
        uint32 commissionThousandths,
        bytes calldata voteAddr
    ) external payable onlyInit {
        uint256 status = SET_CANDIDATE;
        candidateSet.push(
            Candidate({
                operateAddr: operateAddr,
                consensusAddr: consensusAddr,
                feeAddr: feeAddr,
                commissionThousandths: commissionThousandths,
                margin: msg.value,
                status: status,
                commissionLastChangeRound: roundTag,
                commissionLastRoundValue: commissionThousandths
            })
        );
        exMap[operateAddr] = CandidateEx({
            voteAddr: voteAddr,
            agent: address(0)
        });
        uint256 index = candidateSet.length;
        operateMap[operateAddr] = index;
        consensusMap[consensusAddr] = index;

        emit registered(operateAddr, consensusAddr, feeAddr, commissionThousandths, msg.value, voteAddr);
    }
    /********************* External methods  ****************************/

    function turnRound() public virtual override onlyCoinbase onlyInit onlyZeroGasPrice {
        require(!turnroundFailed, "turnRound failed");
        super.turnRound();
    }

    function nextRound() internal virtual override {
        if (controlRoundTimeTag) {
            roundTag++;
        } else {
            super.nextRound();
        }
    }
    
    function setMaxAlternateCount(uint256 _maxAlternateCount) external {
        maxAlternateCount = _maxAlternateCount;
    }
    function mockGetAlternateCount(uint256 maxAlternateCount, uint256 count, uint256 candidateSize) public pure returns (uint256) {
        return getAlternateCount(maxAlternateCount, count, candidateSize);
    }
    receive() external payable {}
    // for unit test
    function removeCandidateMock(uint256 index) external {
        removeCandidate(index);
    }
}
