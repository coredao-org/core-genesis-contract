// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBitcoinStake.sol";
import "./lib/Memory.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";

/// This contract handles BTC staking. 
/// It interacts with BitcoinStake.sol and BitcoinLSTStake.sol for non-custodial BTC staking and LST BTC staking correspondingly. 
contract BitcoinAgent is IAgent, System, IParamSubscriber {

  // key: candidate
  // value: staked BTC amount
  mapping (address => StakeAmount) public candidateMap;

  struct StakeAmount {
    // staked BTC amount from LST
    uint256 lstStakeAmount;
    // staked BTC amount from non custodial
    uint256 stakeAmount;
  }

  modifier onlyPledgeAgent() {
    require(msg.sender == PLEDGE_AGENT_ADDR, "the sender must be pledge agent contract");
    _;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);

  function init() external onlyNotInit {
    alreadyInit = true;
  }

  function _initializeFromPledgeAgent(address[] memory candidates, uint256[] memory amounts) external onlyPledgeAgent {
    uint256 s = candidates.length;
    for (uint256 i = 0; i < s; ++i) {
      candidateMap[candidates[i]].stakeAmount = amounts[i];
    }
  }

  /*********************** IAgent implementations ***************************/
  /// Prepare for the new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    IBitcoinStake(BTC_STAKE_ADDR).prepare(round);
    IBitcoinStake(BTCLST_STAKE_ADDR).prepare(round);
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round.
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 /*round*/) external override onlyStakeHub {
    uint256 validatorSize = validators.length;
    require(validatorSize == rewardList.length, "the length of validators and rewardList should be equal");

    uint256[] memory rewards = new uint256[](validatorSize);
    StakeAmount memory sa;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      sa = candidateMap[validators[i]];
      rewards[i] = rewardList[i] * sa.lstStakeAmount / (sa.lstStakeAmount + sa.stakeAmount);
    }
    IBitcoinStake(BTCLST_STAKE_ADDR).distributeReward(validators, rewards);

    for (uint256 i = 0; i < validatorSize; ++i) {
      rewards[i] = rewardList[i] - rewards[i];
    }
    IBitcoinStake(BTC_STAKE_ADDR).distributeReward(validators, rewards);
  }

  /// Get staked BTC amount
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of staked BTC amounts of all candidates in this round
  /// @return totalAmount Total BTC staked on all candidates in this round
  function getStakeAmounts(address[] calldata candidates, uint256 /*round*/) external override returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    uint256[] memory lstAmounts = IBitcoinStake(BTCLST_STAKE_ADDR).getStakeAmounts(candidates);
    amounts = IBitcoinStake(BTC_STAKE_ADDR).getStakeAmounts(candidates);

    for (uint256 i = 0; i < candidateSize; ++i) {
      candidateMap[candidates[i]].lstStakeAmount = lstAmounts[i];
      candidateMap[candidates[i]].stakeAmount = amounts[i];
      amounts[i] += lstAmounts[i];
      totalAmount += amounts[i];
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
  /// @return rewardUnclaimed Amount unclaimed after applying grading
  function claimReward(address delegator) external override onlyStakeHub returns (uint256 reward, uint256 rewardUnclaimed) {
    (uint256 btcReward, uint256 btcRewardUnclaimed) = IBitcoinStake(BTC_STAKE_ADDR).claimReward(delegator);
    (uint256 btclstReward, uint256 btclstRewardUnclaimed) = IBitcoinStake(BTCLST_STAKE_ADDR).claimReward(delegator);
    return (btcReward + btclstReward, btcRewardUnclaimed + btclstRewardUnclaimed);
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