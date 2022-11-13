pragma solidity 0.8.4;
pragma experimental ABIEncoderV2;
import "../ValidatorSet.sol";

contract ValidatorSetMock is ValidatorSet {
    constructor() ValidatorSet() public {}

    receive() external payable{}

    function developmentInit() external {
        blockReward = blockReward / 1e14;
    }

    function updateBlockReward(uint256 _blockReward) external {
        blockReward = _blockReward;
    }

    function updateSubsidyReduceInterval(uint256 _internal) external {
        SUBSIDY_REDUCE_INTERVAL = _internal;
    }

    function addRoundRewardMock(address[] memory agentList, uint256[] memory rewardList)
    external {
        uint256 rewardSum = 0;
        for (uint256 i = 0; i < rewardList.length; i++) {
        	rewardSum += rewardList[i];
        }
        IPledgeAgent(PLEDGE_AGENT_ADDR).addRoundReward{ value: rewardSum }(agentList, rewardList);
    }

    function jailValidator(address operateAddress, uint256 round, int256 fine) external {
        ICandidateHub(CANDIDATE_HUB_ADDR).jailValidator(operateAddress, round, fine);
    }

    function getValidatorByConsensus(address consensus) external view returns(Validator memory) {
        uint index = currentValidatorSetMap[consensus];
        require(index > 0, "no match validator");
        return currentValidatorSet[index-1];
    }
}
