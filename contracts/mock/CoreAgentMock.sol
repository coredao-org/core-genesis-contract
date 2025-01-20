pragma solidity 0.8.4;

import {CoreAgent} from "../CoreAgent.sol";
import "../lib/SatoshiPlusHelper.sol";
import "@openzeppelin/contracts/utils/Address.sol";

contract CoreAgentMock is CoreAgent {
    uint256 public rewardAmountM;

    event mockDelegatedCoin(address indexed candidate, address indexed delegator, uint256 amount, uint256 realtimeAmount);
    event mockUndelegatedCoin(address indexed candidate, address indexed delegator, uint256 amount);
    event mockTransferredCoin(
        address indexed sourceCandidate,
        address indexed targetCandidate,
        address indexed delegator,
        uint256 amount,
        uint256 realtimeAmount
    );


    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
        roundTag = 7;
    }

    function initializeFromPledgeAgentMock(address[] memory candidates, uint256[] memory amounts, uint256[] memory realtimeAmounts) external {
        uint256 s = candidates.length;
        for (uint256 i = 0; i < s; ++i) {
            Candidate storage c = candidateMap[candidates[i]];
            c.amount = amounts[i];
            c.realtimeAmount = realtimeAmounts[i];
        }
    }


    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function setRequiredCoinDeposit(uint newRequiredCoinDeposit) external {
        requiredCoinDeposit = newRequiredCoinDeposit;
    }

    function deductTransferredAmountMock(address delegator, uint256 amount) external {
        _deductTransferredAmount(delegator, amount);
    }


    function getDelegatorMap(address delegator) external view returns (address[] memory, uint256) {
        address[] memory candidates = delegatorMap[delegator].candidates;
        uint256 amount = delegatorMap[delegator].amount;
        return (candidates, amount);
    }

    function getAccruedRewardMap(address validator, uint256 round) external view returns (uint256) {
        uint256 accruedReward = accruedRewardMap[validator][round];
        return accruedReward;
    }

    function setAccruedRewardMap(address candidate, uint256 round, uint256 amount) external {
        accruedRewardMap[candidate][round] = amount;
    }

    function setCoreRewardMap(address delegator, uint256 reward, uint256 accStakedAmount) external {
        rewardMap[delegator] = Reward(reward, accStakedAmount);
    }
    

    function setCandidateMapAmount(address candidate, uint256 amount, uint256 realAmount, uint256 endRound) external {
        candidateMap[candidate].amount = amount;
        candidateMap[candidate].realtimeAmount = realAmount;
        if (endRound > 0) {
            candidateMap[candidate].continuousRewardEndRounds.push(endRound);
        }
    }

    function getRewardAmount() external view returns (uint256) {
        return rewardAmountM;
    }

    function collectCoinRewardMock(address agent, address delegator, uint256 settleRound) external returns (uint256, uint256) {
        uint256 avgStakedAmount;
        Candidate storage a = candidateMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        (rewardAmountM, avgStakedAmount) = _collectRewardFromCandidate(agent, d, settleRound);
        return (rewardAmountM, avgStakedAmount);
    }

    function _mockCollectReward(address candidate, uint256 stakedAmount, uint256 realtimeAmount, uint256 transferredAmount, uint256 changeRound) internal returns (uint256 reward, bool changed, uint256 accStakedAmount) {
        require(changeRound != 0, "invalid delegator");
        uint256 lastRoundTag = roundTag - 1;
        if (changeRound <= lastRoundTag) {
            uint256 lastRoundReward = _getRoundAccruedReward(candidate, lastRoundTag);
            uint256 lastChangeRoundReward = _getRoundAccruedReward(candidate, changeRound - 1);
            uint256 changeRoundReward;
            reward = stakedAmount * (lastRoundReward - lastChangeRoundReward);
            accStakedAmount = stakedAmount * (lastRoundTag - changeRound + 1);

            if (transferredAmount != 0) {
                changeRoundReward = _getRoundAccruedReward(candidate, changeRound);
                reward += transferredAmount * (changeRoundReward - lastChangeRoundReward);
                accStakedAmount += transferredAmount;
            }

            if (realtimeAmount != stakedAmount) {
                if (changeRound < lastRoundTag) {
                    if (changeRoundReward == 0) {
                        changeRoundReward = _getRoundAccruedReward(candidate, changeRound);
                    }
                    reward += (realtimeAmount - stakedAmount) * (lastRoundReward - changeRoundReward);
                    accStakedAmount += (realtimeAmount - stakedAmount) * (lastRoundTag - changeRound);
                }
            }
            reward /= SatoshiPlusHelper.CORE_STAKE_DECIMAL;
            return (reward, true, accStakedAmount);
        }
        return (0, false, 0);
    }

    function _mockCollectRewardFromCandidate(address candidate, CoinDelegator storage cd) internal returns (uint256 reward, uint256 accStakedAmount) {
        uint256 stakedAmount = cd.stakedAmount;
        uint256 realtimeAmount = cd.realtimeAmount;
        uint256 transferredAmount = cd.transferredAmount;
        bool changed;
        (reward, changed, accStakedAmount) = _mockCollectReward(candidate, stakedAmount, realtimeAmount, transferredAmount, cd.changeRound);
        if (changed) {
            if (transferredAmount != 0) {
                cd.transferredAmount = 0;
            }
            if (realtimeAmount != stakedAmount) {
                cd.stakedAmount = realtimeAmount;
            }
            cd.changeRound = roundTag;
        }
    }

    function _mockDelegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256) {
        Candidate storage a = candidateMap[candidate];
        CoinDelegator storage cd = a.cDelegatorMap[delegator];
        uint256 changeRound = cd.changeRound;
        if (changeRound == 0) {
            cd.changeRound = roundTag;
            delegatorMap[delegator].candidates.push(candidate);
        } else if (changeRound != roundTag) {
            (uint256 reward, uint256 accStakedAmount) = _mockCollectRewardFromCandidate(candidate, cd);
            rewardMap[delegator].reward += reward;
            rewardMap[delegator].accStakedAmount += accStakedAmount;
        }
        a.realtimeAmount += amount;
        cd.realtimeAmount += amount;
        if (!isTransfer) {
            delegatorMap[delegator].amount += amount;
        }

        return cd.realtimeAmount;
    }

    function mockDelegateCoin(address candidate) external payable {
        require(msg.value >= requiredCoinDeposit, "delegate amount is too small");
        uint256 realtimeAmount = _mockDelegateCoin(candidate, msg.sender, msg.value, false);
        emit mockDelegatedCoin(candidate, msg.sender, msg.value, realtimeAmount);
    }

    function _mockUndelegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256 undelegatedNewAmount) {
        require(amount != 0, 'Undelegate zero coin');
        Candidate storage a = candidateMap[candidate];
        CoinDelegator storage cd = a.cDelegatorMap[delegator];
        uint256 changeRound = cd.changeRound;
        require(changeRound != 0, 'no delegator information found');
        if (changeRound != roundTag) {
            (uint256 reward, uint256 accStakedAmount) = _mockCollectRewardFromCandidate(candidate, cd);
            rewardMap[delegator].reward += reward;
            rewardMap[delegator].accStakedAmount += accStakedAmount;
        }

        uint256 realtimeAmount = cd.realtimeAmount;
        require(realtimeAmount >= amount, "Not enough staked tokens");
        if (amount != realtimeAmount) {
            require(amount >= requiredCoinDeposit, "undelegate amount is too small");
            require(cd.realtimeAmount - amount >= requiredCoinDeposit, "remain amount is too small");
        }

        uint256 stakedAmount = cd.stakedAmount;
        a.realtimeAmount -= amount;
        if (isTransfer) {
            if (stakedAmount > amount) {
                cd.transferredAmount += amount;
            } else if (stakedAmount != 0) {
                cd.transferredAmount += stakedAmount;
            }
        } else {
            delegatorMap[delegator].amount -= amount;
        }
        if (!isTransfer && cd.realtimeAmount == amount && cd.transferredAmount == 0) {
            _removeDelegation(delegator, candidate);
        } else {
            cd.realtimeAmount -= amount;
            if (stakedAmount > amount) {
                cd.stakedAmount -= amount;
            } else if (stakedAmount != 0) {
                cd.stakedAmount = 0;
            }
        }
        undelegatedNewAmount = amount - (stakedAmount - cd.stakedAmount);
    }

    function mockUndelegateCoin(address candidate, uint256 amount) public {
        uint256 dAmount = _mockUndelegateCoin(candidate, msg.sender, amount, false);
        _deductTransferredAmount(msg.sender, dAmount);
        Address.sendValue(payable(msg.sender), amount);
        emit mockUndelegatedCoin(candidate, msg.sender, amount);
    }

    function mockTransferCoin(address sourceCandidate, address targetCandidate, uint256 amount) public {
        if (sourceCandidate == targetCandidate) {
            revert SameCandidate(sourceCandidate);
        }
        _mockUndelegateCoin(sourceCandidate, msg.sender, amount, true);
        uint256 newDeposit = _mockDelegateCoin(targetCandidate, msg.sender, amount, true);
        emit mockTransferredCoin(sourceCandidate, targetCandidate, msg.sender, amount, newDeposit);
    }


}
