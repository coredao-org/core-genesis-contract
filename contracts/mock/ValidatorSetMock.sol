pragma solidity 0.8.4;
import "../ValidatorSet.sol";
import "./interface/IPledgeAgentMock.sol";

contract ValidatorSetMock is ValidatorSet {
    function developmentInit() external {
        blockReward = blockReward / 1e14;

        for (uint i=0; i<currentValidatorSet.length; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        delete currentValidatorSet;

        bytes memory initValidatorSet = hex"f8d7ea9401bca3615d24d3c638836691517b2b9b49b054b1943ae030dc3717c66f63d6e8f1d1508a5c941ff46dea94a458499604a85e90225a14946f36368ae24df16d94de442f5ba55687a24f04419424e0dc2593cc9f4cea945e00c0d5c4c10d4c805aba878d51129a89d513e094cb089be171e256acdaac1ebbeb32ffba0dd438eeea941cd652bc64af3f09b490daae27f46e53726ce230940a53b7e0ffd97357e444b85f4d683c1d8e22879aea94da37ccecbb2d7c83ae27ee2bebfe8ebce162c60094d82c24274ebbfe438788d684dc6034c3c67664a4";
        (Validator[] memory validatorSet, bool valid) = decodeValidatorSet(initValidatorSet);
        require(valid, "failed to parse init validatorSet");
        uint256 validatorSize = validatorSet.length;
        for (uint256 i = 0; i < validatorSize; i++) {
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
    function addRoundRewardMock(address[] memory agentList, uint256[] memory rewardList,uint roundTag)
    external payable {
        uint256 rewardSum = 0;
        for (uint256 i = 0; i < rewardList.length; i++) {
        	rewardSum += rewardList[i];
        }
        IStakeHub(STAKE_HUB_ADDR).addRoundReward{ value: rewardSum }(agentList, rewardList,roundTag);
    }

    function jailValidator(address operateAddress, uint256 round, uint256 fine) external {
        ICandidateHub(CANDIDATE_HUB_ADDR).jailValidator(operateAddress, round, fine);
    }

    function getValidatorByConsensus(address consensus) external view returns(Validator memory) {
        uint index = currentValidatorSetMap[consensus];
        require(index > 0, "no match validator");
        return currentValidatorSet[index-1];
    }

    function setValidatorSetMap(address validator) external {
        currentValidatorSetMap[validator] = 1;
    }
    /// Distribute rewards to validators (and delegators through PledgeAgent)
  /// @dev this method is called by the CandidateHub contract at the beginning of turn round
  /// @dev this is where we deal with reward distribution logics
  function distributeRewardOld() external  onlyCandidate returns (address[] memory operateAddressList) {
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
    ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: incentiveSum }();

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

    IPledgeAgentMock(PLEDGE_AGENT_ADDR).addRoundRewardOld{ value: rewardSum }(operateAddressList, rewardList);
    totalInCome = 0;
    return operateAddressList;
  } 
}
