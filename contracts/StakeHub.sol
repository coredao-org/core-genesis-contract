// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IParamSubscriber.sol";
import "./interface/IStakeHub.sol";
import "./interface/IAgent.sol";
import "./interface/ISystemReward.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IValidatorSet.sol";
import "./System.sol";
import "./lib/Address.sol";
import "./lib/Memory.sol";
import "./lib/BytesLib.sol";
import "./lib/RLPDecode.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./lib/SafeCast.sol";

/// This contract deals with overall hybrid score and reward distribution logics. 
/// It replaces the existing role of PledgeAgent.sol to interact with CandidateHub.sol and other protocol contracts during the turnround process. 
/// Underneath it interacts with the new agent contracts to deal with CORE, BTC and hash staking separately. 
contract StakeHub is IStakeHub, System, IParamSubscriber {
  using BytesLib for *;
  using SafeCast for *;

  // Supported asset types
  //  - CORE
  //  - Hash power (measured in BTC blocks)
  //  - BTC 
  Asset[] public assets;

  // key: candidate op address
  // value: score of each staked asset type
  //        0 - total score
  //        1 - CORE score
  //        2 - hash score
  //        3 - BTC score
  mapping(address => uint256[]) public candidateScoresMap;

  // key: agent contract address 
  // value: asset information of the round
  mapping(address => AssetState) public stateMap;

  // other smart contracts granted to interact with StakeHub
  mapping(address => bool) public operators;

  // surplus of dual staking, unclaimble rewards increase surplus and extra rewards decrease it
  // if the current surplus is not enough to pay the next extra rewards, system reward contract will be called to refill
  uint256 public surplus;

  struct Asset {
    string  name;
    address agent;
    uint32 hardcap;
  }

  struct AssetState {
    uint256 amount;
    uint256 factor;
  }

  /*********************** events **************************/
  event roundReward(string indexed name, uint256 round, address[] validator, uint256[] amount);
  event claimedReward(address indexed delegator, uint256 amount);
  event claimedRelayerReward(address indexed relayer, uint256 amount);
  event received(address indexed from, uint256 amount);

  modifier onlyPledgeAgent() {
    require(msg.sender == PLEDGE_AGENT_ADDR, "the sender must be pledge agent contract");
    _;
  }

  function init() external onlyNotInit {
    // initialize list of supported assets
    assets.push(Asset("CORE", CORE_AGENT_ADDR, 6000));
    assets.push(Asset("HASHPOWER", HASH_AGENT_ADDR, 2000));
    assets.push(Asset("BTC", BTC_AGENT_ADDR, 4000));

    operators[PLEDGE_AGENT_ADDR] = true;
    operators[CORE_AGENT_ADDR] = true;
    operators[HASH_AGENT_ADDR] = true;
    operators[BTC_AGENT_ADDR] = true;
    operators[BTC_STAKE_ADDR] = true;
    operators[BTCLST_STAKE_ADDR] = true;

    alreadyInit = true;

    address[] memory validators = IValidatorSet(VALIDATOR_CONTRACT_ADDR).getValidatorOps();
    uint256[] memory factors = new uint256[](3);
    factors[0] = 1;
    // HASH_UNIT_CONVERSION * 1e6
    factors[1] = 1e18 * 1e6;
    // BTC_UNIT_CONVERSION * 2e4
    factors[2] = 1e10 * 2e4;
    uint256 validatorSize = validators.length;
    for (uint256 i = 0; i < validatorSize; ++i) {
      address validator = validators[i];
      candidateScoresMap[validator].push(0);
      candidateScoresMap[validator].push(0);
      candidateScoresMap[validator].push(0);
      candidateScoresMap[validator].push(0);
    }

    uint256 len = assets.length;
    for (uint256 j = 0; j < len; j++) {
      stateMap[assets[j].agent] = AssetState(0, factors[j]);
    }
  }

  receive() external payable {
    if (msg.value != 0) {
      emit received(msg.sender, msg.value);
    }
  }

  /*********************** Interface implementations ***************************/
  /// Receive staking rewards from ValidatorSet, which is triggered at the
  /// beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function addRoundReward(
    address[] calldata validators,
    uint256[] calldata rewardList,
    uint256 roundTag
  ) external payable override onlyValidator
  {
    uint256 validatorSize = validators.length;
    require(validatorSize == rewardList.length, "the length of validators and rewardList should be equal");
    uint256[] memory rewards = new uint256[](validatorSize);

    uint256 burnReward;
    uint256 assetSize = assets.length;
    for (uint256 i = 0; i < assetSize; ++i) {
      for (uint256 j = 0; j < validatorSize; ++ j) {
        address validator = validators[j];
        uint256 totalScore = candidateScoresMap[validator][0];
        // only reach here if running a new chain from genesis
        if (totalScore == 0) {
          if (i == 0) {
            burnReward += rewardList[j];
          }
          rewards[j] = 0;
          continue;
        }
        rewards[j] = rewardList[j] * candidateScoresMap[validator][i+1] / totalScore;
      }
      emit roundReward(assets[i].name, roundTag, validators, rewards);
      IAgent(assets[i].agent).distributeReward(validators, rewards, roundTag);
    }
    // burn rewards after initial setup, should reach only if running a new chain from genesis
    if (burnReward != 0) {
      ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: burnReward }();
    }
  }

  /// Calculate hybrid score for all candidates
  /// This function will also calculate the discount of rewards for each asset
  /// to apply hardcap
  ///
  /// @param candidates List of candidate operator addresses
  /// @param round The new round tag
  /// @return scores List of hybrid scores of all validator candidates in this round
  function getHybridScore(
    address[] calldata candidates,
    uint256 round
  ) external override onlyCandidate returns (uint256[] memory scores) {
    IBitcoinStake(BTC_STAKE_ADDR).prepare(round);
    uint256 candidateSize = candidates.length;
    uint256 assetSize = assets.length;

    uint256 factor0;
    uint256[] memory amounts;
    uint256[] memory totalAmounts = new uint256[](assetSize);
    scores = new uint256[](candidateSize);
    for (uint256 i = 0; i < assetSize; ++i) {
      (amounts, totalAmounts[i]) =
        IAgent(assets[i].agent).getStakeAmounts(candidates, round);
      uint256 factor = 1;
      if (i == 0) {
        factor0 = factor;
      } else if (totalAmounts[0] != 0 && totalAmounts[i] != 0) {
        factor = (factor0 * totalAmounts[0]) * assets[i].hardcap / assets[0].hardcap / totalAmounts[i];
      }
      uint score;
      for (uint256 j = 0; j < candidateSize; ++j) {
        score = amounts[j] * factor;
        scores[j] += score;
        uint256[] storage candidateScores = candidateScoresMap[candidates[j]];
        if (candidateScores.length == 0) {
          candidateScores.push(0);
        }
        if (candidateScores.length == i+1) {
          candidateScores.push(score);
        } else {
          candidateScores[i+1] = score;
        }
      }
      stateMap[assets[i].agent] = AssetState(totalAmounts[i], factor);
    }

    for (uint256 j = 0; j < candidateSize; ++j) {
      candidateScoresMap[candidates[j]][0] = scores[j];
    }
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyCandidate {
    uint256 assetSize = assets.length;
    for (uint256 i = 0; i < assetSize; ++i) {
      IAgent(assets[i].agent).setNewRound(validators, round);
    }
  }

  /// Claim reward for delegator
  /// @return rewards Amounts claimed
  function claimReward() external returns (uint256[] memory rewards) {
    address delegator = msg.sender;
    rewards = _calculateReward(delegator);

    uint256 reward;
    for (uint256 i = 0; i < rewards.length; i++) {
      reward += rewards[i];
    }
    if (reward != 0) {
      Address.sendValue(payable(delegator), reward);
      emit claimedReward(delegator, reward);
    }
  }

  /// Claim reward for PledgeAgent
  /// @param delegator delegator address
  /// @return reward Amounts claimed
  function proxyClaimReward(address delegator) external onlyPledgeAgent returns (uint256 reward) {
    uint256[] memory rewards = _calculateReward(delegator);

    for (uint256 i = 0; i < rewards.length; i++) {
      reward += rewards[i];
    }
    if (reward != 0) {
      Address.sendValue(payable(PLEDGE_AGENT_ADDR), reward);
    }
  }

  /// Calculate reward for delegator
  /// @param delegator delegator address
  /// @return rewards Amounts claimed
  function _calculateReward(address delegator) internal returns (uint256[] memory rewards) {
    uint256 assetSize = assets.length;
    rewards = new uint256[](assetSize);
    int256 floatReward;
    uint256 accStakedCoreAmount;
    (rewards[0], floatReward, accStakedCoreAmount) = IAgent(assets[0].agent).claimReward(delegator, 0);

    uint256 totalReward = rewards[0];
    int256 totalFloatReward = floatReward;
    for (uint256 i = 1; i < assetSize; ++i) {
      (rewards[i], floatReward,) = IAgent(assets[i].agent).claimReward(delegator, accStakedCoreAmount);
      totalReward += rewards[i];
      totalFloatReward += floatReward;
    }

    if (totalFloatReward > surplus.toInt256()) {
      // move 10x from system reward as a buffer for the next claim calls
      uint256 claimAmount = totalFloatReward.toUint256() * 10;
      ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(payable(STAKE_HUB_ADDR), claimAmount);
      surplus += claimAmount;
    }
    surplus = (surplus.toInt256() - totalFloatReward).toUint256();
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    uint256 newValue = value.toUint256(0);
    if (!_updateHardcap(key, newValue)) {
      revert UnsupportedGovParam(key);
    }
  
    emit paramChange(key, value);
  }

  function _updateHardcap(string calldata key, uint256 newValue) internal returns(bool) {
    uint256 indexplus;
    if (Memory.compareStrings(key, "coreHardcap")) {
      indexplus = 1;
    } else if(Memory.compareStrings(key, "hashHardcap")) {
      indexplus = 2;
    } else if(Memory.compareStrings(key, "btcHardcap")) {
      indexplus = 3;
    }
    if (indexplus != 0) {
      if (newValue == 0 || newValue > 1e5) {
        revert OutOfBounds(key, newValue, 1, 1e5);
      }
      assets[indexplus - 1].hardcap = uint32(newValue);
      return true;
    }
    return false;
  }

  /*********************** External methods ********************************/
  function getCandidateScores(address candidate) external view returns (uint256[] memory) {
    return candidateScoresMap[candidate];
  }

  function getAssets() external view returns (Asset[] memory) {
    return assets;
  }
}