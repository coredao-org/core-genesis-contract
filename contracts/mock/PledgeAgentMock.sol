pragma solidity 0.8.4;

import "../PledgeAgent.sol";

contract PledgeAgentMock is PledgeAgent {
    uint256 public rewardAmountM;

    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
    }

    function setRoundState(uint256 power, uint256 coin) external {
        stateMap[roundTag] = RoundState(power + 1, coin + 1, powerFactor);
    }

    function setAgentRound(address agent, uint256 power, uint256 coin) external {
    }

    function setAgentReward(address agent, uint index,
        uint256 totalReward,
        uint256 claimedReward,
        uint256 totalScore,
        uint256 coin,
        uint256 power,
        uint256 round) external {}

    function setAgentValidator(address agent, uint256 power, uint256 coin) external {
        RoundState memory rs = stateMap[roundTag];
        uint256 totalScore = coin * rs.power + power * rs.coin * rs.powerFactor / 10000;
        agentsMap[agent].rewardSet.push(Reward(0, 0, totalScore, coin, roundTag));
        agentsMap[agent].power = power;
        agentsMap[agent].coin = coin;
    }

    function setCoinDelegator(address agent) external {}

    function setBtcDelegator(address agent) external {}

    function getRewardLength(address agent) external view returns (uint) {
        return agentsMap[agent].rewardSet.length;
    }

    function getDebtDepositMap(uint256 rRound, address delegator) external view returns (uint) {
        uint256 debt = debtDepositMap[rRound][delegator];
        return debt;
    }

    function setPowerFactor(uint  newPowerFactor) external {
        powerFactor = newPowerFactor;
    }

    function collectCoinRewardMock(address agent, address delegator,
        int256 roundLimit) external {
        Agent storage a = agentsMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        rewardAmountM = collectCoinReward(a, d, roundLimit);
    }
}
