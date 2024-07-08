pragma solidity 0.8.4;

import {CoreAgent} from "../CoreAgent.sol";

contract CoreAgentMock is CoreAgent {
    uint256 public rewardAmountM;

    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
        roundTag = 1;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function getDelegatorMap(address delegator) external view returns (address[] memory, uint256) {
        address[] memory candidates = delegatorMap[delegator].candidates;
        uint256 amount = delegatorMap[delegator].amount;
        return (candidates, amount);
    }

    function getAccuredRewardMap(address validator, uint256 round) external view returns (uint256) {
        uint256 accuredReward = accuredRewardMap[validator][round];
        return accuredReward;
    }

    function setAccuredRewardMap(address candidate, uint256 round, uint256 amount) external {
        accuredRewardMap[candidate][round] = amount;
    }


    function setCandidateMapAmount(address candidate, uint256 amount, uint256 realAmount) external {
        candidateMap[candidate].amount = amount;
        candidateMap[candidate].realtimeAmount = realAmount;
    }

    function getRewardAmount() external view returns (uint256) {
        return rewardAmountM;
    }


    function collectCoinRewardMock(address agent, address delegator) external returns (uint256) {
        Candidate storage a = candidateMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        rewardAmountM = collectCoinReward(agent, d);
        return rewardAmountM;
    }


}
