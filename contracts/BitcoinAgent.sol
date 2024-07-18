// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBitcoinStake.sol";
import "./lib/Memory.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";

/// This contract manages user delegate BTC.
/// Including both BTC independent delegate and LST delegate.
contract BitcoinAgent is IAgent, System, IParamSubscriber {

  // Key: candidate
  // value: btc amount;
  mapping (address => StakeAmount) public candidateMap;

  struct StakeAmount {
    uint256 lstStakeAmount;
    uint256 stakeAmount;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);

  function init() external onlyNotInit {
    alreadyInit = true;
  }

  /*********************** IAgent implementations ***************************/
  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    IBitcoinStake(BTC_STAKE_ADDR).prepare(round);
    IBitcoinStake(BTCLST_STAKE_ADDR).prepare(round);
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round
  /// @param validatorList List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validatorList, uint256[] calldata rewardList, uint256 /*roundTag*/) external override onlyStakeHub {
    uint256 validatorSize = validatorList.length;
    require(validatorSize == rewardList.length, "the length of validatorList and rewardList should be equal");

    uint256[] memory rewards = new uint256[](validatorSize);
    uint256 avgReward;
    uint256 rewardValue;
    StakeAmount memory sa;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      sa = candidateMap[validatorList[i]];
      avgReward = rewardList[i] * SatoshiPlusHelper.BTC_DECIMAL / (sa.lstStakeAmount + sa.stakeAmount);
      rewards[i] = avgReward * sa.lstStakeAmount / SatoshiPlusHelper.BTC_DECIMAL;
      rewardValue += rewards[i];
    }
    IBitcoinStake(BTCLST_STAKE_ADDR).distributeReward(validatorList, rewards);
    rewardValue = 0;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      rewards[i] = rewardList[i] - rewards[i];
      rewardValue += rewards[i];
    }
    IBitcoinStake(BTC_STAKE_ADDR).distributeReward(validatorList, rewards);
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  ///
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmounts(address[] calldata candidates, uint256 /*roundTag*/) external override returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    uint256[] memory lstAmounts = IBitcoinStake(BTCLST_STAKE_ADDR).getStakeAmounts(candidates);
    amounts = IBitcoinStake(BTC_STAKE_ADDR).getStakeAmounts(candidates);

    for (uint256 i = 0; i < candidateSize; ++i) {
      amounts[i] += lstAmounts[i];
      totalAmount += amounts[i];
      candidateMap[candidates[i]].lstStakeAmount = lstAmounts[i];
      candidateMap[candidates[i]].stakeAmount = amounts[i];
    }
  }


  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    IBitcoinStake(BTC_STAKE_ADDR).setNewRound(validators, round);
    IBitcoinStake(BTCLST_STAKE_ADDR).setNewRound(validators, round);
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  function claimReward(address delegator) external override onlyStakeHub returns (uint256 reward) {
    reward = IBitcoinStake(BTC_STAKE_ADDR).claimReward(delegator);
    reward += IBitcoinStake(BTCLST_STAKE_ADDR).claimReward(delegator);
    return reward;
  }

  function updateStakeAmount(address candidate, uint256 stakeAmount) external onlyBtcStake {
    candidateMap[candidate].stakeAmount = stakeAmount;
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    require(false, "unknown param");
    emit paramChange(key, value);
  }
}