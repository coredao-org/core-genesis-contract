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
import "./lib/SatoshiPlusHelper.sol";

/// This contract deals with overall hybrid score and reward distribution logics. 
/// It replaces the existing role of PledgeAgent.sol to interact with CandidateHub.sol and other protocol contracts during the turnround process. 
/// Under the neath it interacts with the new agent contracts to deal with CORE, BTC and hash staking separately. 
contract StakeHub is IStakeHub, System, IParamSubscriber {
  using BytesLib for *;

  uint256 public constant HASH_UNIT_CONVERSION = 1e18;
  uint256 public constant INIT_HASH_FACTOR = 1e6;
  uint256 public constant BTC_UNIT_CONVERSION = 1e10;
  uint256 public constant INIT_BTC_FACTOR = 1e4;

  uint256 public constant MASK_STAKE_CORE_MASK = 1;
  uint256 public constant MASK_STAKE_HASH_MASK = 2;
  uint256 public constant MASK_STAKE_BTC_MASK = 4;

  // Supported asset types
  //  - CORE
  //  - Hash power (measured in BTC blocks)
  //  - BTC 
  Asset[] public assets;

  // key: candidate op address
  // value: amount of each staked asset type
  mapping(address => uint256[]) public candidateAmountMap;

  // key: candidate op address
  // value: hybrid score of each candidate
  mapping(address => uint256) public candidateScoreMap;

  // key: delegator address
  // value: MASK value of staked asset types
  // TODO unused
  mapping(address => uint256) public delegatesMaskMap;

  // key: agent contract address 
  // value: asset information of the round
  mapping(address => AssetState) public stateMap;

  // key: delegator address
  // value: system debts, e.g. transmitting fee of a BTC staking transaction
  mapping(address => Debt) debts;

  // other smart contracts granted to interact with StakeHub
  mapping(address => bool) public operators;

  // key: contributor address, e.g. relayer's
  // value: rewards collected for contributing to the system
  // TODO unused
  mapping(address => uint256) public payableNotes;

  // CORE grading applied to BTC stakers
  // TODO these values should be saved for each round; otherwise make sure to clear up unclaimed rewards in each round
  LP[] public lpRates;

  // whether the CORE grading is enabled
  bool public isActive;

  // the percentage of unclaimed rewards distributed to the BTC pool
  uint256 public btcPoolRate;

  // accumulated unclaimed rewards each round, will be redistributed at the beginning of the next round
  uint256 public unclaimedReward;

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

  struct Debt {
    NotePayable[] notes;
  }
  struct NotePayable {
    address contributor;
    uint256 amount;
  }

  struct LP {
      uint256 l;
      uint256 p;
  }

  /*********************** events **************************/
  event roundReward(string indexed name, address indexed validator, uint256 amount, uint256 bonus);
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, uint256 amount);
  event claimedRelayerReward(address indexed relayer, uint256 amount);

  function init() external onlyNotInit {
    // initialize list of supported assets
    assets.push(Asset("CORE", CORE_AGENT_ADDR, 1, 6000));
    assets.push(Asset("HASHPOWER", HASH_AGENT_ADDR, HASH_UNIT_CONVERSION * INIT_HASH_FACTOR, 2000));
    assets.push(Asset("BTC", BTC_AGENT_ADDR, BTC_UNIT_CONVERSION * INIT_BTC_FACTOR, 4000));

    _initHybridScore();

    operators[PLEDGE_AGENT_ADDR] = true;
    operators[CORE_AGENT_ADDR] = true;
    operators[HASH_AGENT_ADDR] = true;
    operators[BTC_AGENT_ADDR] = true;
    operators[BTC_STAKE_ADDR] = true;
    operators[BTCLST_STAKE_ADDR] = true;

    btcPoolRate = SatoshiPlusHelper.DENOMINATOR;
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

    address validator;
    uint256[] memory bonuses = new uint256[](assetSize);
    bonuses[2] = unclaimedReward * btcPoolRate / SatoshiPlusHelper.DENOMINATOR / validatorSize;
    bonuses[0] = unclaimedReward * (SatoshiPlusHelper.DENOMINATOR - btcPoolRate) / SatoshiPlusHelper.DENOMINATOR / validatorSize;
    uint256 burnReward = unclaimedReward - (bonuses[0]+bonuses[2]) * validatorSize;
    unclaimedReward = 0;
    for (uint256 i = 0; i < assetSize; ++i) {
      AssetState memory cs = stateMap[assets[i].agent];
      for (uint256 j = 0; j < validatorSize; ++j) {
        validator = validators[j];
        // only reach here if running a new chain from genesis
        if (candidateScoreMap[validator] == 0) {
          if (i == 0) {
            burnReward += rewardList[j];
          }
          burnReward += bonuses[i];
          rewards[j] = 0;
          continue;
        }
        uint256 r = rewardList[j] * candidateAmountMap[validator][i] * cs.factor / candidateScoreMap[validator];
        // hardcap is applied to each pool, using the discount calculated in `getHybridScore()` step
        rewards[j] = r * cs.discount / SatoshiPlusHelper.DENOMINATOR;
        burnReward += (r - rewards[j]);
        emit roundReward(assets[i].name, validator, rewards[j], bonuses[i]);
        // redistribute unclaimed rewards
        // added after hardcap to leave more rewards to users
        rewards[j] += bonuses[i];
      }
      IAgent(assets[i].agent).distributeReward(validators, rewards, roundTag);
    }

    // burn overflow reward after hardcap
    ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: burnReward }();
  }

  /// Calculate hybrid score for all candidates
  /// This function will also calculate the discount of rewards for each asset to apply hardcap
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
    // asset score & hardcaps are used to calculate discount for each asset
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
      stateMap[assets[i].agent] = AssetState(totalAmount, t, SatoshiPlusHelper.DENOMINATOR);
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
      if (assetScores[i] * hardcapSum > assets[i].hardcap * t) {
        stateMap[assets[i].agent].discount = assets[i].hardcap * t * SatoshiPlusHelper.DENOMINATOR / (hardcapSum * assetScores[i]);
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

  /// add a system debt on a delegator
  /// @param delegator the delegator to pay the debt
  /// @param contributor the contributor to receive the fee
  /// @param amount amount of CORE
  function addNotePayable(address delegator, address contributor, uint256 amount) external override {
    require(operators[msg.sender], 'only debt operators');
    debts[delegator].notes.push(NotePayable(contributor, amount));
  }

  /// Claim reward for delegator
  /// @return rewards Amounts claimed
  /// @return debtAmount system debt paid
  function claimReward() external returns (uint256[] memory rewards, uint256 debtAmount) {
    address delegator = msg.sender;
    (rewards, debtAmount) = calculateReward(delegator);

    uint256 reward = 0;
    for (uint256 i = 0; i < rewards.length; i++) {
      reward += rewards[i];
    }
    if (reward != 0) {
      Address.sendValue(payable(delegator), reward);
      emit claimedReward(delegator, reward);
    }
  }

  /// Calculate reward for delegator
  /// @param delegator delegator address
  /// @param rewards rewards on each type of staked assets
  /// @param debtAmount system debt paid
  function calculateReward(address delegator) public returns (uint256[] memory rewards, uint256 debtAmount) {
    (uint256 coreReward, uint256 coreRewardUnclaimed) = IAgent(assets[0].agent).claimReward(delegator);
    (uint256 hashPowerReward, uint256 hashPowerRewardUnclaimed) = IAgent(assets[1].agent).claimReward(delegator);
    (uint256 btcReward, uint256 btcRewardUnclaimed) = IAgent(assets[2].agent).claimReward(delegator);

    // apply CORE grading to BTC rewards
    uint256 lpRatesLength = lpRates.length;
    if (isActive && lpRatesLength != 0) {
      uint256 bb = coreReward * SatoshiPlusHelper.DENOMINATOR / btcReward;
      uint256 p =  SatoshiPlusHelper.DENOMINATOR;
      for (uint256 i = lpRatesLength; i != 0; i--) {
        if (bb >= lpRates[i].l) {
          p = lpRates[i].p;
          break;
        }
      }

      uint256 btcRewardClaimed = btcReward * p / SatoshiPlusHelper.DENOMINATOR;
      btcRewardUnclaimed += (btcReward - btcRewardClaimed);
      btcReward = btcRewardClaimed;
    }

    rewards = new uint256[](assets.length);
    rewards[0] = coreReward;
    rewards[1] = hashPowerReward;
    rewards[2] = btcReward;

    uint256 reward = coreReward + hashPowerReward + btcReward;

    // pay system debts from staking rewards
    if (reward != 0) {
      Debt storage lb = debts[delegator];
      uint256 lbamount;
      for (uint256 i = lb.notes.length; i != 0; --i) {
        lbamount = lb.notes[i-1].amount;
        if (lbamount <= reward) {
          reward -= lbamount;
          payableNotes[lb.notes[i-1].contributor] += lbamount;
          debtAmount += lbamount;
          lb.notes.pop();
        } else {
          debtAmount += reward;
          lb.notes[i-1].amount -= reward;
          payableNotes[lb.notes[i-1].contributor] += reward;
          reward = 0;
          break;
        }
      }
    }

    unclaimedReward += (btcRewardUnclaimed + coreRewardUnclaimed + hashPowerRewardUnclaimed);
  }

  /// Claim reward for relayer
  /// @return reward Amount claimed
  function claimRelayerReward() external returns (uint256 reward) {
    address relayer = msg.sender;
    reward = payableNotes[relayer];
    if (reward != 0) {
      payableNotes[relayer] = 0;
      Address.sendValue(payable(relayer), reward);
      emit claimedRelayerReward(relayer, reward);
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
    } else if(Memory.compareStrings(key, "lpRates")) {
      // TODO more details on how the grading binary array is designed and parsed
      uint256 i;
      uint256 lastLength = lpRates.length;
      uint256 currentLength = value.indexUint(0, 1);

      require(((currentLength << 2) + 1) == value.length, "invalid param length");

      for (i = currentLength; i < lastLength; i++) {
        lpRates.pop();
      }

      for (i = 0; i < currentLength; i++) {
        uint256 startIndex = (i << 2) + 1;
        uint256 l = value.indexUint(startIndex, 2);
        require(l <= SatoshiPlusHelper.DENOMINATOR, "invalid param l");
        uint256 p =  value.indexUint(startIndex + 2, 2);
        require(p <= SatoshiPlusHelper.DENOMINATOR, "invalid param p");
        LP memory lp = LP({
          l: l,
          p: p
        });

        if (i >= lastLength) {
          lpRates.push(lp);
        } else {
          lpRates[i] = lp;
        }
      }
    } else if (Memory.compareStrings(key, "isActive")) {
       uint256 newIsActive = value.toUint256(0);
      if (newIsActive > 1) {
        revert OutOfBounds(key, newIsActive, 0, 1);
      }
      isActive = newIsActive == 1;
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
    (bool success, bytes memory data) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("getStakeInfo(address[])", validators));
    require (success, "call PLEDGE_AGENT_ADDR.getStakeInfo() failed");
    (uint256[] memory cores, uint256[] memory hashs, uint256[] memory btcs) = abi.decode(data, (uint256[], uint256[], uint256[]));

    (success,) = assets[2].agent.call(abi.encodeWithSignature("initHardforkRound(address[],uint256[])", validators, btcs));
    require (success, "call BTC_AGENT_ADDR.initHardforkRound() failed");

    uint256 validatorSize = validators.length;
    uint256[] memory totalAmounts = new uint256[](3);
    for (uint256 i = 0; i < validatorSize; ++i) {
      address validator = validators[i];

      totalAmounts[0] += cores[i];
      totalAmounts[1] += hashs[i];
      totalAmounts[2] += btcs[i];

      candidateAmountMap[validator].push(cores[i]);
      candidateAmountMap[validator].push(hashs[i]);
      candidateAmountMap[validator].push(btcs[i]);

      candidateScoreMap[validator] = cores[i] * assets[0].factor + hashs[i] * assets[1].factor + btcs[i] * assets[2].factor;
    }

    uint256 len = assets.length;
    for (uint256 j = 0; j < len; j++) {
      stateMap[assets[j].agent] = AssetState(totalAmounts[j], assets[j].factor, SatoshiPlusHelper.DENOMINATOR);
    }

    // get active candidates.
    (success, data) = CANDIDATE_HUB_ADDR.call(abi.encodeWithSignature("getCandidates()"));
    require (success, "call CANDIDATE_HUB.getCandidates() failed");
    address[] memory candidates = abi.decode(data, (address[]));
    // move candidate amount.
    (success,) = PLEDGE_AGENT_ADDR.call(abi.encodeWithSignature("moveAgent(address[])", candidates));
    require (success, "call PLEDGE_AGENT_ADDR.moveAgent() failed");
  }
}