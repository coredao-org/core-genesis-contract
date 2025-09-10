// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../StakeHub.sol";
import "../interface/IPledgeAgent.sol";
import "../interface/IAgent.sol";

contract StakeHubMock is StakeHub {
    uint256 public rewardAmountM;

    uint256 public constant TEST_HASH_UNIT_CONVERSION = 10;
    uint256 public constant TEST_INIT_HASH_FACTOR = 50;
    uint256 public constant TEST_BTC_UNIT_CONVERSION = 5;
    uint256 public constant TEST_INIT_BTC_FACTOR = 2;


    function developmentInit() external {
    }

    function setOperators(address delegator, bool value) external {
        operators[delegator] = value;
    }

    function getCandidateScoresMap(address candidate) external view returns (uint256[] memory) {
        return candidateScoresMap[candidate];
    }

    function getDelegatorMap(address account) external view returns (Delegator memory) {
        Delegator memory DelegatorMap = delegatorMap[account];
        return DelegatorMap;
    }

    function setDelegatorMap(address account, uint256 changeRound_, uint256 [] memory rewards) external {
        delegatorMap[account].changeRound = changeRound_;
        delegatorMap[account].rewards = rewards;
    }


    function setCandidateScoresMap(address candidate, uint256 core, uint256 power, uint256 btc) external {
        candidateScoresMap[candidate][0] = (core + power + btc);
        candidateScoresMap[candidate][1] = core;
        candidateScoresMap[candidate][2] = power;
        candidateScoresMap[candidate][3] = btc;
    }


    function setStateMapDiscount(address agent, uint256 value, uint256 value1) external {
        stateMap[agent] = AssetState(value, value1);
    }

    function setSurplus(uint256 value) external {
        surplus = value;
    }

    // for unit test
    function calculateRewardMock(address delegator) external returns (uint256[] memory rewards) {
        (rewards) = _calculateReward(delegator, false);
    }

    function coreAgentDistributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 round) external {
        IAgent(CORE_AGENT_ADDR).distributeReward(validators, rewardList, round);
    }

}
