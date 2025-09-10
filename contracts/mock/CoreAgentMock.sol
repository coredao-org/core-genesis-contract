// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {CoreAgent} from "../CoreAgent.sol";
import "../lib/SatoshiPlusHelper.sol";
import "@openzeppelin/contracts/utils/Address.sol";

contract CoreAgentMock is CoreAgent {
    uint256 public rewardAmountM;

    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
        roundTag = 7;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function setRequiredCoinDeposit(uint newRequiredCoinDeposit) external {
        requiredCoinDeposit = newRequiredCoinDeposit;
    }

    function getDelegatorMap(address delegator) external view returns (address[] memory, uint256, uint256) {
        address[] memory candidates = delegatorMap[delegator].candidates;
        uint256 amount = delegatorMap[delegator].amount;
        uint256 channelAmount = delegatorMap[delegator].channelAmount;
        return (candidates, amount, channelAmount);
    }

    function getAccruedRewardMap(address validator, uint256 round) external view returns (uint256) {
        uint256 accruedReward = accruedRewardMap[validator][round];
        return accruedReward;
    }

    function setAccruedRewardMap(address candidate, uint256 round, uint256 amount) public {
        accruedRewardMap[candidate][round] = amount;
    }

    function setCoreRewardMap(address delegator, uint256 reward, uint256 accStakedAmount) external {
        uint256 accrueRound = roundTag - 1;
        address[] memory candidates = delegatorMap[delegator].candidates;
        for (uint256 i = 0; i < candidates.length; ++i) {
            setAccruedRewardMap(candidates[i], accrueRound, 0);
        }
        rewardMap[delegator] = Reward(reward, accStakedAmount);
    }
    

    function setCandidateMapAmount(address candidate, uint256 amount, uint256 realAmount, uint256 endRound) external {
        candidateMap[candidate].amount = amount;
        candidateMap[candidate].realtimeAmount = realAmount;
        if (endRound > 0) {
            candidateMap[candidate].continuousRewardEndRounds.push(endRound);
        }
    }
    function setCoinDelegatorMap(address candidate, address delegator, uint256 stakedAmount, uint256 realtimeAmount) external {
        CoinDelegator storage d = candidateMap[candidate].cDelegatorMap[delegator];
        d.stakedAmount = stakedAmount;
        d.realtimeAmount = realtimeAmount; 
    }

    function getRewardAmount() external view returns (uint256) {
        return rewardAmountM;
    }
    //  for unit test
    function collectCoinRewardMock(address agent, address delegator) external returns (uint256 reward, uint256 stakedAmount1, uint256 stakedAmount2) {
        Candidate storage a = candidateMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        (reward, stakedAmount1, stakedAmount2) = _collectRewardFromCandidate(agent, d);
    }
    function deductTransferredAmountMock(address delegator, uint256 amount) external {
        _deductTransferredAmount(delegator, amount);
    }

}
