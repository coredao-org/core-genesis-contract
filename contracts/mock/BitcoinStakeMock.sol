// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../BitcoinStake.sol";
import "../lib/BytesLib.sol";

contract BitcoinStakeMock is BitcoinStake {
    uint256 public minBtcLockRound;
    uint64 public MONTH_TIMESTAMP = 2592000;

    event migrated(bytes32 indexed txid);
    event mockDelegatedBtc(bytes32 indexed txid, address indexed candidate, address indexed delegator, uint32 outputIndex, uint64 amount, uint256 endRound, uint32 channelId);
    event mockTransferredBtc(
        bytes32 indexed txid,
        address sourceCandidate,
        address targetCandidate,
        address delegator,
        uint256 amount
    );

    function developmentInit() external {
        minBtcLockRound = 1;
        gradeActive = true;
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
        candidateList = expireInfo.candidateList;
        amounts = new uint256[](candidateList.length);
        for (uint256 i = 0; i < candidateList.length; i++) {
            amounts[i] = expireInfo.amountMap[candidateList[i]];
        }
        return (candidateList, amounts);
    }


    function setCandidateMap(address validator, uint256 stakedAmount, uint256 realtimeAmount, uint256 [] memory value) external {
        candidateMap[validator] = Candidate(stakedAmount, realtimeAmount, value);
    }

    function setAccruedRewardPerBTCMap(address validator, uint256 round, uint256 value) external {
        accruedRewardPerBTCMap[validator][round] = value;
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

    function initializeFromPledgeAgentMock(address[] memory candidates, uint256[] memory amounts, uint256[] memory realtimeAmounts) external {
        uint256 s = candidates.length;
        for (uint256 i = 0; i < s; ++i) {
            Candidate storage c = candidateMap[candidates[i]];
            c.stakedAmount = amounts[i];
            c.realtimeAmount = realtimeAmounts[i];
        }
    }





    function mockDelegateBtc(bytes32 txid, uint64 btcValue, address candidate, address delegator, uint32 lockTime, uint64 blockTimestamp, uint32 outputIndex, uint32 channelId) external nonReentrant {
        BtcTx storage bt = btcTxMap[txid];
        require(bt.amount == 0, "btc tx is already delegated.");
        {
            uint256 endRound = lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
            require(endRound > roundTag + 1, "insufficient locking rounds");
            bt.lockTime = lockTime;
            bt.blockTimestamp = blockTimestamp;
        }
        DepositReceipt storage dr = receiptMap[txid];
        uint64 btcAmount;
        {
            (btcAmount, outputIndex, delegator, candidate) = (btcValue, outputIndex, delegator, candidate);
            bt.amount = btcAmount;
            bt.outputIndex = outputIndex;
            bt.channelId = channelId;
            emit mockDelegatedBtc(txid, candidate, delegator, outputIndex, btcAmount, lockTime / SatoshiPlusHelper.ROUND_INTERVAL, channelId);
        }
        delegatorMap[delegator].txids.push(txid);
        candidateMap[candidate].realtimeAmount += btcAmount;
        dr.delegator = delegator;
        dr.candidate = candidate;
        dr.round = roundTag;
        _addExpire(dr, lockTime, btcAmount);
    }

    function _mockCollectReward(bytes32 txid) internal returns (uint256 reward, bool expired, uint256 accStakedAmount) {
        BtcTx storage bt = btcTxMap[txid];
        DepositReceipt storage dr = receiptMap[txid];
        uint256 drRound = dr.round;
        require(drRound != 0, "invalid deposit receipt");
        uint256 lastRound = roundTag - 1;
        uint256 unlockRound1 = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL - 1;
        if (drRound < lastRound && drRound < unlockRound1) {
            uint256 minRound = lastRound < unlockRound1 ? lastRound : unlockRound1;
            // full reward
            reward = (_getRoundAccruedReward(dr.candidate, minRound) - _getRoundAccruedReward(dr.candidate, drRound)) * bt.amount / SatoshiPlusHelper.BTC_DECIMAL;
            accStakedAmount = bt.amount * (minRound - drRound);

            // apply time grading to BTC rewards
            uint256 rewardUnclaimed = 0;
            if (gradeActive && grades.length != 0) {
                uint64 lockDuration = bt.lockTime - bt.blockTimestamp;
                uint256 p = grades[0].percentage;
                for (uint256 j = grades.length - 1; j != 0; j--) {
                    if (lockDuration >= grades[j].lockDuration) {
                        p = grades[j].percentage;
                        break;
                    }
                }
                uint256 rewardClaimed = reward * p / SatoshiPlusHelper.DENOMINATOR;
                rewardUnclaimed = reward - rewardClaimed;
                reward = rewardClaimed;
            }

            dr.round = minRound;
            if (reward != 0) {
                rewardMap[dr.delegator].reward += reward;
            }
            if (rewardUnclaimed != 0) {
                rewardMap[dr.delegator].unclaimedReward += rewardUnclaimed;
            }
            if (accStakedAmount != 0) {
                rewardMap[dr.delegator].accStakedAmount += accStakedAmount;
            }
        }

        if (unlockRound1 < roundTag) {
            emit btcExpired(txid, dr.delegator);
            delete receiptMap[txid];
            return (reward, true, accStakedAmount);
        }
        return (reward, false, accStakedAmount);
    }
/// transfer BTC delegate to a new validator
/// @param txid the staked BTC transaction to transfer
/// @param targetCandidate the new validator to stake to
    function mockTransferBtc(bytes32 txid, address targetCandidate) external nonReentrant {
        BtcTx storage bt = btcTxMap[txid];
        DepositReceipt storage dr = receiptMap[txid];
        uint64 amount = bt.amount;
        require(amount != 0, "btc tx not found");
        require(dr.delegator == msg.sender, "not the delegator of this btc receipt");

        address candidate = dr.candidate;
        require(candidate != targetCandidate, "can not transfer to the same validator");
        uint256 endRound = bt.lockTime / SatoshiPlusHelper.ROUND_INTERVAL;
        require(endRound > roundTag + 1, "insufficient locking rounds");

        if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
            revert InactiveCandidate(targetCandidate);
        }
        _mockCollectReward(txid);

        Candidate storage c = candidateMap[candidate];
        c.realtimeAmount -= amount;
        round2expireInfoMap[endRound].amountMap[candidate] -= amount;

        // Set candidate to targetCandidate
        dr.candidate = targetCandidate;
        dr.round = roundTag;
        _addExpire(dr, bt.lockTime, amount);

        Candidate storage tc = candidateMap[targetCandidate];
        tc.realtimeAmount += amount;

        emit mockTransferredBtc(txid, candidate, targetCandidate, msg.sender, bt.amount);
    }

    // mock contract for test
    function collectRewardMock(bytes32 txid, uint256 coreAmount, uint256 drRound, uint256 settleRound, bool claim) external returns (uint256 reward, bool expired, int256 floatReward, uint256 remainingCoreAmount) {
        return _collectReward(txid, coreAmount, drRound, settleRound, claim);
    }
    function getCalculateRoundMock(bytes32 txid, uint256 settleRound) external view returns (uint calculateRound, bool expired) {
        return _getCalculateRound(txid, settleRound);
    }
    function applyDualStakingMock(uint256 coreAmount, uint256 bctAmount) external view returns (uint256, uint256) {
        return _applyDualStaking(coreAmount, bctAmount);
    }


}
