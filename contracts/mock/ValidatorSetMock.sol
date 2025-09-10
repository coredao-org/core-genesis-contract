// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../ValidatorSet.sol";

contract ValidatorSetMock is ValidatorSet {
    function developmentInit() external {
        blockReward = blockReward / 1e14;
        voteRewardPercent = 10;

        for (uint i = 0; i < currentValidatorSet.length; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        delete currentValidatorSet;

        bytes memory initValidatorSet = hex"f901d1f85b9401bca3615d24d3c638836691517b2b9b49b054b1943ae030dc3717c66f63d6e8f1d1508a5c941ff46db099a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8f85b94a458499604a85e90225a14946f36368ae24df16d94de442f5ba55687a24f04419424e0dc2593cc9f4cb099a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8f85b945e00c0d5c4c10d4c805aba878d51129a89d513e094cb089be171e256acdaac1ebbeb32ffba0dd438eeb099a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8f85b941cd652bc64af3f09b490daae27f46e53726ce230940a53b7e0ffd97357e444b85f4d683c1d8e22879ab099a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8f85b94da37ccecbb2d7c83ae27ee2bebfe8ebce162c60094d82c24274ebbfe438788d684dc6034c3c67664a4b099a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8";
        bytes memory initVoteAddress = hex"99a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8";
        (Validator[] memory validatorSet, bool valid) = decodeValidatorSet(initValidatorSet);
        require(valid, "failed to parse init validatorSet");
        uint256 validatorSize = validatorSet.length;
        for (uint256 i = 0; i < validatorSize; i++) {
            validatorSet[i].voteAddr = initVoteAddress;
            validatorSet[i].voteWeight = 0;
            currentValidatorSet.push(validatorSet[i]);
            currentValidatorSetMap[validatorSet[i].consensusAddress] = i + 1;
        }
    }
    
    function updateBlockReward(uint256 _blockReward) external {
        blockReward = _blockReward;
    }

    function updateSubsidyReduceInterval(uint256 _internal) external {
        SUBSIDY_REDUCE_INTERVAL = _internal;
    }

    function jailValidator(address operateAddress, uint256 round, uint256 fine) external {
        ICandidateHub(CANDIDATE_HUB_ADDR).jailValidator(operateAddress, round, fine);
    }

    function getValidatorByConsensus(address consensus) external view returns (Validator memory) {
        uint index = currentValidatorSetMap[consensus];
        require(index > 0, "no match validator");
        return currentValidatorSet[index - 1];
    }

    function getVoteRewardPercent() external view returns (uint256) {
        return voteRewardPercent;
    }


    function setValidatorSetMap(address validator) external {
        currentValidatorSetMap[validator] = 1;
    }

    function setValidatorCount(uint256 _validatorCount) external {
        validatorCount = _validatorCount;
    }

    function getCurrentValidatorSet() external view returns (Validator[] memory) {
        return currentValidatorSet;
    }
    function setMaintainSlashPercent(uint256 _maintainSlashPercent) external {
        maintainSlashPercent = _maintainSlashPercent;
    }

    // for unit test
    function mockUpdateRankedValidatorList(address[] calldata consensusAddrList) external {
        updateRankedValidatorList(consensusAddrList);
    }
    
    function clearCurrentValidatorSet() external {
        for (uint i = 0; i < currentValidatorSet.length; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        delete currentValidatorSet;
    }
    
    function addRoundRewardMock(address[] memory agentList, uint256[] memory rewardList, uint roundTag)
    external payable {
        uint256 rewardSum = 0;
        for (uint256 i = 0; i < rewardList.length; i++) {
            rewardSum += rewardList[i];
        }
        IStakeHub(STAKE_HUB_ADDR).addRoundReward{value: rewardSum}(agentList, rewardList, roundTag);
    }
}
