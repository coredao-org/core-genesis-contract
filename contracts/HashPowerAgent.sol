// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./System.sol";

/// This contract manages Bitcoin miners delegate hash power.
contract HashPowerAgent is IAgent, System, IParamSubscriber {

  // This field is used to store hash power reward of delegators
  // when turn round
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);

  function init() external onlyNotInit {
    alreadyInit = true;
  }

  /*********************** IAgent implementations ***************************/
  /// Do some preparement before new round.
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    // Nothing
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round
  /// @param validatorList List of validator operator addresses
  /// @param rewardList List of reward amount
  /// @param round The round tag
  function distributeReward(address[] calldata validatorList, uint256[] calldata rewardList, uint256 round) external override onlyStakeHub {
    uint256 validatorSize = validatorList.length;
    require(validatorSize == rewardList.length, "the length of validatorList and rewardList should be equal");

    // fetch BTC miners who delegated hash power in the about to end round; 
    // and distribute rewards to them
    uint256 minerSize;
    uint256 avgReward;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      address[] memory miners = ILightClient(LIGHT_CLIENT_ADDR).getRoundMiners(round-7, validatorList[i]);
      // distribute rewards to every miner
      minerSize = miners.length;
      if (minerSize != 0) {
        avgReward = rewardList[i] / minerSize;
        for (uint256 j = 0; j < minerSize; ++j) {
          rewardMap[miners[j]] += avgReward;
        }
      }
    }
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  /// @param roundTag The new round tag
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmounts(address[] calldata candidates, uint256 roundTag) external override view returns (uint256[] memory amounts, uint256 totalAmount) {
    // fetch hash power delegated on list of candidates
    // which is used to calculate hybrid score for validators in the new round
    (amounts, totalAmount) = ILightClient(LIGHT_CLIENT_ADDR).getRoundPowers(roundTag-7, candidates);
  }

  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    // nothing.
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  function claimReward(address delegator) external override onlyStakeHub returns (uint256, uint256) {
    uint256 rewardSum = rewardMap[delegator];
    if (rewardSum != 0) {
      rewardMap[delegator] = 0;
    }
    return (rewardSum, 0);
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