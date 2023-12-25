// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../PledgeAgent.sol";
import {BaseMock} from "./BaseMock.sol";


contract PledgeAgentMock is PledgeAgent , BaseMock {
    uint private MOCK_POWER_BLOCK_FACTOR = 1;
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

    function _powerBlockFactor() internal view override returns(uint) { 
        return MOCK_POWER_BLOCK_FACTOR;
    }

    function getPowerBlockFactor() external view returns (uint) {
        return _powerBlockFactor();
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

