pragma solidity 0.8.4;

import "../BitcoinStake.sol";
import "../lib/BytesLib.sol";

contract BitcoinStakeMock is BitcoinStake {
    uint256 public minBtcLockRound;
    uint64 public MONTH_TIMESTAMP = 2592000;

    function developmentInit() external {
        minBtcLockRound = 1;
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


    function setIsActive(uint256 value) external {
        gradeActive = value;
    }

    function setAlreadyInit(bool value) external {
        alreadyInit = value;
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


}
