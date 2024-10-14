pragma solidity 0.8.4;

import "../BitcoinStake.sol";
import "../lib/BytesLib.sol";

contract BitcoinStakeMock is BitcoinStake {
    uint256 public minBtcLockRound;
    uint64 public MONTH_TIMESTAMP = 2592000;

    function developmentInit() external {
        minBtcLockRound = 1;
        gradeActive = true;
    }

    function getDelegatorBtcMap(address delegator) external view returns (bytes32[] memory) {
        return delegatorMap[delegator].txids;
    }

    function getRewardMap(address delegator) external view returns (uint256, uint256) {
        uint256 reward;
        uint256 unclaimedReward;
        reward = rewardMap[delegator].reward;
        unclaimedReward = rewardMap[delegator].unclaimedReward;
        return (reward, unclaimedReward);
    }

    function setRewardMap(address delegator, uint256 reward, uint256 unclaimedReward) external {
        rewardMap[delegator].reward = reward;
        rewardMap[delegator].unclaimedReward = unclaimedReward;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function setInitTlpRates(uint64 value1, uint32 value01, uint64 value2, uint32 value02, uint64 value3, uint32 value03, uint64 value4, uint32 value04, uint64 value5, uint32 value05) external {
        grades.push(LockLengthGrade(value1 * MONTH_TIMESTAMP, value01));
        grades.push(LockLengthGrade(value2 * MONTH_TIMESTAMP, value02));
        grades.push(LockLengthGrade(value3 * MONTH_TIMESTAMP, value03));
        grades.push(LockLengthGrade(value4 * MONTH_TIMESTAMP, value04));
        grades.push(LockLengthGrade(value5 * MONTH_TIMESTAMP, value05));
    }

    function setTlpRates(uint64 value1, uint32 value01) external {
        grades.push(LockLengthGrade(value1, value01));
    }

    function popTtlpRates() external {
        delete grades;
    }

    function getGradesLength() external view returns (uint256) {
        return grades.length;
    }

    function setBtcRewardMap(address delegator, uint256 reward, uint256 unclaimed, uint256 accStakedAmount) external {
        rewardMap[delegator] = Reward(reward, unclaimed, accStakedAmount);
    }

    function setIsActive(bool value) external {
        gradeActive = value;
    }

    function setDelegatorMap(address delegator, bytes32 value) external {
        delegatorMap[delegator].txids.push(value);
    }

    function getRound2expireInfoMap(uint256 round) external view returns (address[] memory candidateList, uint256[] memory amounts) {
        ExpireInfo storage expireInfo = round2expireInfoMap[round];
        address[] memory candidateList = expireInfo.candidateList;
        amounts = new uint256[](candidateList.length);
        for (uint256 i = 0; i < candidateList.length; i++) {
            amounts[i] = expireInfo.amountMap[candidateList[i]];
        }
        return (candidateList, amounts);
    }


    function setCandidateMap(address validator, uint256 stakedAmount, uint256 realtimeAmount, uint256 [] memory value) external {
        candidateMap[validator] = Candidate(stakedAmount, realtimeAmount, value);
    }

    function setAccuredRewardPerBTCMap(address validator, uint256 round, uint256 value) external {
        accuredRewardPerBTCMap[validator][round] = value;
    }

    function getAgentAddrList(uint256 index) external view returns (address[] memory) {
        ExpireInfo storage expireInfo = round2expireInfoMap[index];
        uint256 length = expireInfo.candidateList.length;
        address[] memory agentAddresses = new address[](length);
        for (uint256 i = 0; i < length; i++) {
            agentAddresses[i] = expireInfo.candidateList[i];
        }
        return agentAddresses;
    }

    function getContinuousRewardEndRounds(address candidate) external view returns (uint256[] memory) {
        return candidateMap[candidate].continuousRewardEndRounds;
    }

    function calculateRewardMock(bytes32[] calldata txids) external returns (uint256 amount, uint256 accStakedAmount) {
        uint256 reward;
        uint256 stakedAmount;
        bool expired;
        for (uint256 i = txids.length; i != 0; i--) {
            (reward, expired, stakedAmount) = _collectReward(txids[i - 1]);
            amount += reward;
            accStakedAmount += stakedAmount;
        }
    }


}
