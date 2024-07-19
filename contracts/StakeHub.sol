// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IParamSubscriber.sol";
import "./interface/IStakeHub.sol";
import "./interface/IAgent.sol";
import "./interface/ISystemReward.sol";
import "./interface/IValidatorSet.sol";
import "./System.sol";
import "./lib/Address.sol";
import "./lib/Memory.sol";
import "./lib/BytesLib.sol";

/// This contract manages all stake implementation agent on Core blockchain
/// Currently, it supports three types of stake: Core, Hash, and BTC/BTCLST.
/// Each one have a hardcap of rewards.
/// As a transitional version, pledgeagent.sol retains the logic of core,
/// hash, and BTC.
contract StakeHub is IStakeHub, System, IParamSubscriber {
  using BytesLib for *;

  uint256 public constant HASH_UNIT_CONVERSION = 1e18;
  uint256 public constant INIT_HASH_FACTOR = 1e6;
  uint256 public constant BTC_UNIT_CONVERSION = 1e10;
  uint256 public constant INIT_BTC_FACTOR = 1e4;
  uint256 public constant DENOMINATOR = 1e4;

  // Asset list.
  Asset[] public assets;

  // key: candidate op address
  // value: assets' stake amount list.
  //        The order is core, hash, btc.
  mapping(address => uint256[]) public candidateAmountMap;

  // key: candidate op address
  // value: hybrid score for each candidate.
  mapping(address => uint256) public candidateScoreMap;

  // key: Asset's agent address
  // value: useful state information of round
  mapping(address => AssetState) public stateMap;

  // key: delegator, value: Liability
  mapping(address => Liability) liabilities;

  mapping(address => bool) public liabilityOperators;

  // key: creditor address
  // value: amount of note payable for claim.
  mapping(address => uint256) public payableNotes;

  struct Asset {
    string  name;
    address agent;
    uint256 factor;
    uint256 hardcap;
  }

  struct AssetState {
    uint256 amount;
    uint256 factor;
    uint256 discount;
  }

  struct Liability {
    NotePayable[] notes;
  }
  struct NotePayable {
    address creditor;
    uint256 amount;
  }

  // key: delegator
  // value: score = sum(delegated core * delegated time)
  // When user claim reward of btc, it will cost score.
  // If the score is not enough, reward should be discount.
  mapping(address => uint256) rewardScoreMap;

  /*********************** events **************************/
  event roundReward(string indexed name, address indexed validator, uint256 amounted);
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);

  function init() external onlyNotInit {
    // add three assets into list
    assets.push(Asset("CORE", PLEDGE_AGENT_ADDR, 1, 6000));
    assets.push(Asset("HASHPOWER", HASH_AGENT_ADDR, HASH_UNIT_CONVERSION * INIT_HASH_FACTOR, 2000));
    assets.push(Asset("BTC", BTC_AGENT_ADDR, BTC_UNIT_CONVERSION * INIT_BTC_FACTOR, 4000));

    _initHybridScore();

    liabilityOperators[BTC_STAKE_ADDR] = true;
    liabilityOperators[BTCLST_STAKE_ADDR] = true;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  /// Receive round rewards from ValidatorSet, which is triggered at the beginning of turn round
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
    uint256 assetSize = assets.length;
    uint256[] memory rewards = new uint256[](validatorSize);
    uint256 burnReward;

    address validator;
    uint256 rewardValue;
    for (uint256 i = 0; i < assetSize; ++i) {
      AssetState memory cs = stateMap[assets[i].agent];
      rewardValue = 0;
      for (uint256 j = 0; j < validatorSize; ++j) {
        validator = validators[j];
        // This code scope is used for deploy as genesis
        if (candidateScoreMap[validator] == 0) {
          burnReward += rewardList[j] / assetSize;
          rewards[j] = 0;
          continue;
        }
        uint256 r = rewardList[j] * candidateAmountMap[validator][i] * cs.factor / candidateScoreMap[validator];
        rewards[j] = r * cs.discount / DENOMINATOR;
        rewardValue += rewards[j];
        burnReward += (r - rewards[j]);
        emit roundReward(assets[i].name, validator, rewards[j]);
      }
      IAgent(assets[i].agent).distributeReward(validators, rewards, roundTag);
    }
    // burn overflow reward of hardcap
    ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: burnReward }();
  }

  /// Calculate hybrid score for all candidates
  /// This function will also calculate the discount of reward for each asset
  /// if stake percent overflow its hardcap.
  ///
  /// @param candidates List of candidate operator addresses
  /// @param roundTag The new round tag
  /// @return scores List of hybrid scores of all validator candidates in this round
  function getHybridScore(
    address[] calldata candidates,
    uint256 roundTag
  ) external override onlyCandidate returns (uint256[] memory scores) {
    uint256 candidateSize = candidates.length;
    uint256 assetSize = assets.length;

    uint256 hardcapSum;
    for (uint256 i = 0; i < assetSize; ++i) {
      hardcapSum += assets[i].hardcap;
      IAgent(assets[i].agent).prepare(roundTag);
    }
    // score := asset's amount * factor.
    // asset score & hardcaps are used to calculate discount
    // for each asset's reward.
    uint256[] memory assetScores = new uint256[](assetSize);
    scores = new uint256[](candidateSize);
    uint256 t;
    address candiate;
    for (uint256 i = 0; i < assetSize; ++i) {
      (uint256[] memory amounts, uint256 totalAmount) =
        IAgent(assets[i].agent).getStakeAmounts(candidates, roundTag);
      t = assets[i].factor;
      assetScores[i] = totalAmount * t;
      for (uint256 j = 0; j < candidateSize; ++j) {
        scores[j] += amounts[j] * t;
        candiate = candidates[j];
        // length should never be less than i
        if (candidateAmountMap[candiate].length == i) {
          candidateAmountMap[candiate].push(amounts[j]);
        } else {
          candidateAmountMap[candiate][i] = amounts[j];
        }
      }
      stateMap[assets[i].agent] = AssetState(totalAmount, t, DENOMINATOR);
    }

    for (uint256 j = 0; j < candidateSize; ++j) {
      candidateScoreMap[candidates[j]] = scores[j];
    }

    t = assetScores[0] + assetScores[1] + assetScores[2];
    for (uint256 i = 0; i < assetSize; ++i) {
      // stake_proportion := assetScores[i] / t
      // hardcap_proportion := hardcap / hardcapSum
      // if stake_proportion > hardcap_proportion;
      //    then discount = hardcap_proportion / stake_proportion
      // above if condition transform ==> assetScores[i] * hardcapSum > hardcap * t
      if (assetScores[i] * hardcapSum > assets[i].hardcap * t) {
        stateMap[assets[i].agent].discount = assets[i].hardcap * t * DENOMINATOR / (hardcapSum * assetScores[i]);
      }
    }
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param roundTag The new round tag
  function setNewRound(address[] calldata validators, uint256 roundTag) external override onlyCandidate {
    uint256 assetSize = assets.length;
    for (uint256 i = 0; i < assetSize; ++i) {
      IAgent(assets[i].agent).setNewRound(validators, roundTag);
    }
  }

  function addNotePayable(address delegator, address creditor, uint256 amount) external override {
    require(liabilityOperators[msg.sender], 'only liability operators');
    liabilities[delegator].notes.push(NotePayable(creditor, amount));
  }

  /// Claim reward for delegator
  /// @return reward Amount claimed
  function claimReward() external returns (uint256 reward, uint256 liabilityAmount) {
    uint256 subReward;
    uint256 assetSize = assets.length;
    address delegator = msg.sender;
    for (uint256 i = 0; i < assetSize; ++i) {
      subReward = IAgent(assets[i].agent).claimReward(delegator);
      reward += subReward;
    }
    if (reward != 0) {
      Liability storage lb = liabilities[delegator];
      uint256 lbamount;
      for (uint256 i = lb.notes.length; i != 0; --i) {
        lbamount = lb.notes[i-1].amount;
        if (lbamount <= reward) {
          reward -= lbamount;
          payableNotes[lb.notes[i-1].creditor] += lbamount;
          liabilityAmount += lbamount;
          lb.notes.pop();
        } else {
          liabilityAmount += reward;
          lb.notes[i-1].amount -= reward;
          payableNotes[lb.notes[i-1].creditor] += reward;
          reward = 0;
          break;
        }
      }
      if (reward != 0) {
        Address.sendValue(payable(delegator), reward);
        emit claimedReward(delegator, reward);
      }
    }
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }

    if (Memory.compareStrings(key, "hashFactor")) {
      uint256 newHashFactor = value.toUint256(0);
      if (newHashFactor == 0 || newHashFactor > 1e8) {
        revert OutOfBounds(key, newHashFactor, 1, 1e8);
      }
      assets[1].factor = newHashFactor;
    } else if (Memory.compareStrings(key, "btcFactor")) {
      uint256 newBtcFactor = value.toUint256(0);
      if (newBtcFactor == 0 || newBtcFactor > 1e8) {
        revert OutOfBounds(key, newBtcFactor, 1, 1e8);
      }
      assets[2].factor = newBtcFactor;
    } else if (Memory.compareStrings(key, "coreHardcap")) {
      uint256 newCoreHardcap = value.toUint256(0);
      if (newCoreHardcap == 0 || newCoreHardcap > 1e8) {
        revert OutOfBounds(key, newCoreHardcap, 1, 1e8);
      }
      assets[0].hardcap = newCoreHardcap;
    } else if(Memory.compareStrings(key, "hashHardcap")) {
      uint256 newHashHardcap = value.toUint256(0);
      if (newHashHardcap == 0 || newHashHardcap > 1e8) {
        revert OutOfBounds(key, newHashHardcap, 1, 1e8);
      }
      assets[1].hardcap = newHashHardcap;
    } else if(Memory.compareStrings(key, "btcHardcap")) {
      uint256 newBtcHardcap = value.toUint256(0);
      if (newBtcHardcap == 0 || newBtcHardcap > 1e8) {
        revert OutOfBounds(key, newBtcHardcap, 1, 1e8);
      }
      assets[2].hardcap = newBtcHardcap;
    } else {
      require(false, "unknown param");
    }
  
    emit paramChange(key, value);
  }

  /*********************** External methods ********************************/
  function getCandidateAmounts(address candidate) external view returns (uint256[] memory) {
    return candidateAmountMap[candidate];
  }

  function getAssets() external view returns (Asset[] memory) {
    return assets;
  }

  /*********************** Internal methods ********************************/
  function _initHybridScore() internal {
    // get validator set
    address[] memory validators = IValidatorSet(VALIDATOR_CONTRACT_ADDR).getValidatorOps();
    uint256 validatorSize = validators.length;
    uint256 core;
    uint256 hashpower;
    uint256 btc;
    uint256 totalCore;
    uint256 totalHashPower;
    uint256 totalBtc;
    for (uint256 i = 0; i < validatorSize; ++i) {
      address validator = validators[i];
      (bool success, bytes memory data) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("getStakeInfo(address)", validator));
      if (success) {
        (core, hashpower, btc) = abi.decode(data, (uint256, uint256, uint256));
      }
      totalCore += core;
      totalHashPower += hashpower;
      totalBtc += btc;

      candidateAmountMap[validator].push(core);
      candidateAmountMap[validator].push(hashpower);
      candidateAmountMap[validator].push(btc);

      candidateScoreMap[validator] = core * assets[0].factor + hashpower * assets[1].factor + btc * assets[2].factor;
    }

    stateMap[assets[0].agent] = AssetState(totalCore, assets[0].factor, DENOMINATOR);
    stateMap[assets[1].agent] = AssetState(totalHashPower, assets[1].factor, DENOMINATOR);
    stateMap[assets[2].agent] = AssetState(totalBtc, assets[2].factor, DENOMINATOR);
  }
}