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

    function initHybridScoreMock() external {
        _initializeFromPledgeAgent();
    }

    function calculateRewardMock(address delegator) external returns (uint256[] memory rewards) {
        (rewards) = _calculateReward(delegator, false);
    }

    function coreAgentDistributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 round) external {
        IAgent(CORE_AGENT_ADDR).distributeReward(validators, rewardList, round);
    }

    event _initializeFromPledgeAgent___(uint256 aa);

    function _initializeFromPledgeAgent() internal {
        // get stake summary of current round (snapshot values of last turn round)
        address[] memory validators = IValidatorSet(VALIDATOR_CONTRACT_ADDR).getValidatorOps();
        (bool success, bytes memory data) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("getStakeInfo(address[])", validators));
        require(success, "call PLEDGE_AGENT_ADDR.getStakeInfo() failed");
        (uint256[] memory cores, uint256[] memory hashs, uint256[] memory btcs) = abi.decode(data, (uint256[], uint256[], uint256[]));

        uint256[] memory factors = new uint256[](3);
        factors[0] = 1;
        // HASH_UNIT_CONVERSION * 1e6
        factors[1] = 1e18 * 1e6;
        // BTC_UNIT_CONVERSION * 2e4
        factors[2] = 1e10 * 2e4;
        // initialize hybrid score based on data migrated from PledgeAgent.getStakeInfo()
        uint256 validatorSize = validators.length;
        uint256[] memory totalAmounts = new uint256[](3);
        emit _initializeFromPledgeAgent___(cores[0]);
        for (uint256 i = 0; i < validatorSize; ++i) {
            address validator = validators[i];
            totalAmounts[0] += cores[i];
            totalAmounts[1] += hashs[i];
            totalAmounts[2] += btcs[i];
            candidateScoresMap[validator].push(cores[i] * factors[0] + hashs[i] * factors[1] + btcs[i] * factors[2]);
            candidateScoresMap[validator].push(cores[i] * factors[0]);
            candidateScoresMap[validator].push(hashs[i] * factors[1]);
            candidateScoresMap[validator].push(btcs[i] * factors[2]);

        }

        uint256 len = assets.length;
        for (uint256 j = 0; j < len; j++) {
            stateMap[assets[j].agent] = AssetState(totalAmounts[j], factors[j]);
        }

        // get active candidates.
        (success, data) = CANDIDATE_HUB_ADDR.call(abi.encodeWithSignature("getCandidates()"));
        require(success, "call CANDIDATE_HUB.getCandidates() failed");
        address[] memory candidates = abi.decode(data, (address[]));

        // move candidate amount.
        (success,) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("moveCandidateData(address[])", candidates));
        require(success, "call PLEDGE_AGENT_ADDR.moveCandidateData() failed");
    }


}
