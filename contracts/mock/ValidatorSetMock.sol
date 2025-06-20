pragma solidity 0.8.4;

import "../ValidatorSet.sol";
import "./interface/IPledgeAgentMock.sol";

contract ValidatorSetMock is ValidatorSet {
    function developmentInit() external {
        blockReward = blockReward / 1e14;

        for (uint i = 0; i < currentValidatorSet.length; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        delete currentValidatorSet;

        bytes memory initValidatorSet = hex"f8d7ea9401bca3615d24d3c638836691517b2b9b49b054b1943ae030dc3717c66f63d6e8f1d1508a5c941ff46dea94a458499604a85e90225a14946f36368ae24df16d94de442f5ba55687a24f04419424e0dc2593cc9f4cea945e00c0d5c4c10d4c805aba878d51129a89d513e094cb089be171e256acdaac1ebbeb32ffba0dd438eeea941cd652bc64af3f09b490daae27f46e53726ce230940a53b7e0ffd97357e444b85f4d683c1d8e22879aea94da37ccecbb2d7c83ae27ee2bebfe8ebce162c60094d82c24274ebbfe438788d684dc6034c3c67664a4";
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

    struct ValidatorOld {
        address operateAddress;
        address consensusAddress;
        address payable feeAddress;
        uint256 commissionThousandths;
        uint256 income;

    }

    function checkValidatorSetOld(
        address[] memory operateAddrList,
        address[] memory consensusAddrList,
        address payable[] memory feeAddrList,
        uint256[] memory commissionThousandthsList
    ) private pure {
        require(
            consensusAddrList.length == operateAddrList.length,
            "the numbers of consensusAddresses and operateAddresses should be equal"
        );
        require(
            consensusAddrList.length == feeAddrList.length,
            "the numbers of consensusAddresses and feeAddresses should be equal"
        );
        require(
            consensusAddrList.length == commissionThousandthsList.length,
            "the numbers of consensusAddresses and commissionThousandthss should be equal"
        );
        for (uint256 i = 0; i < consensusAddrList.length; i++) {
            for (uint256 j = 0; j < i; j++) {
                require(consensusAddrList[i] != consensusAddrList[j], "duplicate consensus address");
            }
            require(commissionThousandthsList[i] <= 1000, "commissionThousandths out of bound");
        }
    }
    /// Update validator set of the new round with elected validators 
    /// @param operateAddrList List of validator operator addresses
    /// @param consensusAddrList List of validator consensus addresses
    /// @param feeAddrList List of validator fee addresses
    /// @param commissionThousandthsList List of validator commission fees in thousandth
    function updateValidatorSetOld(
        address[] calldata operateAddrList,
        address[] calldata consensusAddrList,
        address payable[] calldata feeAddrList,
        uint256[] calldata commissionThousandthsList
    ) external onlyCandidate {
        // do verify.
        checkValidatorSetOld(operateAddrList, consensusAddrList, feeAddrList, commissionThousandthsList);
        if (consensusAddrList.length == 0) {
            return;
        }
        // do update validator set state
        uint256 i;
        uint256 lastLength = currentValidatorSet.length;
        uint256 currentLength = consensusAddrList.length;
        for (i = 0; i < lastLength; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        for (i = currentLength; i < lastLength; i++) {
            currentValidatorSet.pop();
        }

        for (i = 0; i < currentLength; ++i) {
            if (i >= lastLength) {
                currentValidatorSet.push(Validator(operateAddrList[i], consensusAddrList[i], feeAddrList[i], commissionThousandthsList[i], 0, '', 0));
            } else {
                currentValidatorSet[i] = Validator(operateAddrList[i], consensusAddrList[i], feeAddrList[i], commissionThousandthsList[i], 0, '', 0);
            }
            currentValidatorSetMap[consensusAddrList[i]] = i + 1;
        }

        emit validatorSetUpdated();
    }

    function updateBlockReward(uint256 _blockReward) external {
        blockReward = _blockReward;
    }

    function updateSubsidyReduceInterval(uint256 _internal) external {
        SUBSIDY_REDUCE_INTERVAL = _internal;
    }

    function addRoundRewardMock(address[] memory agentList, uint256[] memory rewardList, uint roundTag)
    external payable {
        uint256 rewardSum = 0;
        for (uint256 i = 0; i < rewardList.length; i++) {
            rewardSum += rewardList[i];
        }
        IStakeHub(STAKE_HUB_ADDR).addRoundReward{value: rewardSum}(agentList, rewardList, roundTag);
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
    /// Distribute rewards to validators (and delegators through PledgeAgent)
    /// @dev this method is called by the CandidateHub contract at the beginning of turn round
    /// @dev this is where we deal with reward distribution logics
    function distributeRewardOld() external onlyCandidate returns (address[] memory operateAddressList) {
        address payable feeAddress;
        uint256 validatorReward;

        uint256 incentiveSum = 0;
        uint256 validatorSize = currentValidatorSet.length;
        for (uint256 i = 0; i < validatorSize; i++) {
            Validator storage v = currentValidatorSet[i];
            uint256 incentiveValue = (v.income * blockRewardIncentivePercent) / 100;
            incentiveSum += incentiveValue;
            v.income -= incentiveValue;
        }
        ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{value: incentiveSum}();

        operateAddressList = new address[](validatorSize);
        uint256[] memory rewardList = new uint256[](validatorSize);
        uint256 rewardSum = 0;
        uint256 tempIncome;
        for (uint256 i = 0; i < validatorSize; i++) {
            Validator storage v = currentValidatorSet[i];
            operateAddressList[i] = v.operateAddress;
            tempIncome = v.income;
            if (tempIncome != 0) {
                feeAddress = v.feeAddress;
                validatorReward = (tempIncome * v.commissionThousandths) / 1000;
                if (tempIncome > validatorReward) {
                    rewardList[i] = tempIncome - validatorReward;
                    rewardSum += rewardList[i];
                }

                v.income = 0;
                bool success = feeAddress.send(validatorReward);
                if (success) {
                    emit directTransfer(v.operateAddress, feeAddress, validatorReward, tempIncome);
                } else {
                    emit directTransferFail(v.operateAddress, feeAddress, validatorReward, tempIncome);
                }
            }
        }

        IPledgeAgentMock(PLEDGE_AGENT_ADDR).addRoundRewardOld{value: rewardSum}(operateAddressList, rewardList);
        totalInCome = 0;
        return operateAddressList;
    }
}
