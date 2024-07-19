// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./lib/Address.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";

/// HARDFORK V-1.0.10
/// This contract manages user delegate CORE.
contract CoreAgent is IAgent, System, IParamSubscriber {

  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;

  uint256 public requiredCoinDeposit;

  // Reward of per 1m CORE per validator per round
  // validator => (round => 1 m cores' Reward)
  mapping(address => mapping(uint256 => uint256)) public accuredRewardMap;

  // key: delegator address
  // value: delegator info.
  mapping(address => Delegator) public delegatorsMap;

  // key: candidate's operateAddr
  // value: candidate info.
  mapping(address => Candidate) public candidatesMap;

  // This field is used to store reward of delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  struct CoinDelegator {
    uint256 stakedAmount;
    uint256 totalAmount;
    uint256 changeRound;
    uint256 transferredAmount;
  }

  struct Candidate {
    mapping(address => CoinDelegator) cDelegatorMap;
    // This value is set in setNewRound
    uint256 amount;
    // It is changed when delegate/undelegate/tranfer
    uint256 realAmount;
    uint256[] continuousRewardEndRounds;
  }

  struct Delegator {
    address[] candidates;
    uint256 amount;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedCoin(address indexed candidate, address indexed delegator, uint256 amount, uint256 totalAmount);
  event undelegatedCoin(address indexed candidate, address indexed delegator, uint256 amount);
  event transferredCoin(
    address indexed sourceCandidate,
    address indexed targetCandidate,
    address indexed delegator,
    uint256 amount,
    uint256 totalAmount
  );
  event claimedReward(address indexed delegator, uint256 amount);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveCandidate(address candidate);

  /// Same address provided when transfer.
  /// @param candidate Address of the candidate
  error SameCandidate(address candidate);

  function init() external onlyNotInit {
    requiredCoinDeposit = INIT_REQUIRED_COIN_DEPOSIT;
    roundTag = block.timestamp / SatoshiPlusHelper.ROUND_INTERVAL;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  /// Do some preparement before new round.
  function prepare(uint256) external override {
    // Nothing
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  /// @param round The round tag
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 round) external override onlyStakeHub
  {
    uint256 validateSize = validators.length;
    require(validateSize == rewardList.length, "the length of validators and rewardList should be equal");

    uint256 historyReward;
    uint256 lastRewardRound;
    uint256 l;
    address validator;
    for (uint256 i = 0; i < validateSize; i++) {
      if (rewardList[i] == 0) {
        continue;
      }
      validator = validators[i];
      mapping(uint256 => uint256) storage m = accuredRewardMap[validator];
      Candidate storage c = candidatesMap[validator];
      l = c.continuousRewardEndRounds.length;
      if (l != 0) {
        lastRewardRound = c.continuousRewardEndRounds[l - 1];
        historyReward = m[lastRewardRound];
      } else {
        historyReward = 0;
        lastRewardRound = 0;
      }
      // Calculate reward of per 1 M Core per validator per round
      m[round] = historyReward + rewardList[i] * SatoshiPlusHelper.CORE_STAKE_DECIMAL / c.amount;
      if (lastRewardRound + 1 == round) {
        c.continuousRewardEndRounds[l - 1] = round;
      } else {
        c.continuousRewardEndRounds.push(round);
      }
    }
  }

  /// Get stake amount
  /// @param candidates List of candidate operator addresses
  ///
  /// @return amounts List of amounts of all special candidates in this round
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmounts(address[] calldata candidates, uint256) external override view returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    amounts = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; ++i) {
      amounts[i] = candidatesMap[candidates[i]].realAmount;
      totalAmount += amounts[i];
    }
  }

  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    uint256 validatorSize = validators.length;
    for (uint256 i = 0; i < validatorSize; ++i) {
      Candidate storage a = candidatesMap[validators[i]];
      a.amount = a.realAmount;
    }
    roundTag = round;
  }

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param candidate The operator address of validator
  function delegateCoin(address candidate) external payable {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(candidate)) {
      revert InactiveCandidate(candidate);
    }
    require(msg.value != 0, 'deposit amount is zero');
    uint256 totalAmount = delegateCoin(candidate, msg.sender, msg.value);
    emit delegatedCoin(candidate, msg.sender, msg.value, totalAmount);
  }

  /// Undelegate coin from a validator
  /// @param candidate The operator address of validator
  function undelegateCoin(address candidate) external {
    undelegateCoin(candidate, 0);
  }

  /// Undelegate coin from a validator
  /// @param candidate The operator address of validator
  /// @param amount The amount of CORE to undelegate
  function undelegateCoin(address candidate, uint256 amount) public {
    amount = undelegateCoin(candidate, msg.sender, amount, false);
    Address.sendValue(payable(msg.sender), amount);
    emit undelegatedCoin(candidate, msg.sender, amount);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceCandidate The validator to transfer coin stake from
  /// @param targetCandidate The validator to transfer coin stake to
  function transferCoin(address sourceCandidate, address targetCandidate) external {
    transferCoin(sourceCandidate, targetCandidate, 0);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceCandidate The validator to transfer coin stake from
  /// @param targetCandidate The validator to transfer coin stake to
  /// @param amount The amount of CORE to transfer
  function transferCoin(address sourceCandidate, address targetCandidate, uint256 amount) public {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
      revert InactiveCandidate(targetCandidate);
    }
    if (sourceCandidate == targetCandidate) {
      revert SameCandidate(sourceCandidate);
    }
    amount = undelegateCoin(sourceCandidate, msg.sender, amount, true);
    uint256 newDeposit = delegateCoin(targetCandidate, msg.sender, amount);

    emit transferredCoin(sourceCandidate, targetCandidate, msg.sender, amount, newDeposit);
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  function claimReward(address delegator) external override onlyStakeHub returns (uint256) {
    uint256 reward;
    uint256 rewardSum = rewardMap[delegator];
    if (rewardSum != 0) {
      rewardMap[delegator] = 0;
    }
    address[] storage candidates = delegatorsMap[delegator].candidates;
    uint256 candidateSize = candidates.length;
    address candidate;
    for (uint256 i = candidateSize; i != 0;) {
      candidate = candidates[i];
      CoinDelegator storage cd = candidatesMap[candidate].cDelegatorMap[delegator];
      reward = collectCoinReward(candidate, cd);
      rewardSum += reward;
      if (cd.totalAmount == 0 && cd.transferredAmount == 0) {
        removeCandidate(delegator, candidate);
        delete candidatesMap[candidate].cDelegatorMap[delegator];
      }
    }
    return rewardSum;
  }

  /*********************** Internal methods ***************************/
  function delegateCoin(address candidate, address delegator, uint256 amount) internal returns (uint256) {
    Candidate storage a = candidatesMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    Delegator storage d = delegatorsMap[delegator];
    uint256 changeRound = cd.changeRound;
    if (changeRound == 0) {
      cd.changeRound = roundTag;
      d.candidates.push(candidate);
    } else if (changeRound != roundTag) {
      uint256 reward = collectCoinReward(candidate, cd);
      rewardMap[delegator] += reward;
    }
    a.realAmount += amount;
    cd.totalAmount += amount;
    d.amount += amount;

    return cd.totalAmount;
  }
  
  function undelegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256) {
    Candidate storage a = candidatesMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    require(changeRound != 0, 'no delegator');
    if (changeRound != roundTag) {
      uint256 reward = collectCoinReward(candidate, cd);
      rewardMap[delegator] += reward;
    }
    uint256 stakedAmount = cd.stakedAmount;
    if (amount == 0) {
      amount = stakedAmount;
    }
    require(stakedAmount != 0 && stakedAmount >= amount, "Not enough staked token");

    if (isTransfer) {
      cd.transferredAmount += amount;
    }

    a.realAmount -= amount;
    Delegator storage d = delegatorsMap[delegator];
    d.amount -= amount;
    if (!isTransfer && cd.totalAmount == amount && cd.transferredAmount == 0) {
      removeCandidate(delegator, candidate);
      delete a.cDelegatorMap[delegator];
    } else {
      cd.totalAmount -= amount;
      cd.stakedAmount -= amount;
    }
    return amount;
  }

  function collectCoinReward(address candidate, CoinDelegator storage cd) internal returns (uint256 reward) {
    uint256 changeRound = cd.changeRound;
    require(changeRound != 0, "invalid coindelegator");
    uint256 lastRoundTag = roundTag - 1;
    if (changeRound <= lastRoundTag) {
      uint256 stakedAmount = cd.stakedAmount;
      uint256 lastRoundReward = getRoundAccuredReward(candidate, lastRoundTag);
      uint256 lastChangeRoundReward = getRoundAccuredReward(candidate, changeRound - 1);
      uint256 changeRoundReward;
      reward = stakedAmount * (lastRoundReward - lastChangeRoundReward);
      if (cd.transferredAmount != 0) {
        changeRoundReward = getRoundAccuredReward(candidate, changeRound);
        reward += cd.transferredAmount * (changeRoundReward - lastChangeRoundReward);
        cd.transferredAmount = 0;
      }

      if (cd.totalAmount != stakedAmount) {
        if (changeRound < lastRoundTag) {
          if (changeRoundReward == 0) {
            changeRoundReward = getRoundAccuredReward(candidate, changeRound);
          }
          reward += (cd.totalAmount - stakedAmount) * (lastRoundReward - changeRoundReward);
        }
        cd.stakedAmount = cd.totalAmount;
      }
      reward /= SatoshiPlusHelper.CORE_STAKE_DECIMAL;
      cd.changeRound = roundTag;
    }
  }

  function removeCandidate(address delegator, address candidate) internal {
    Delegator storage d = delegatorsMap[delegator];
    uint256 l = d.candidates.length;
    for (uint256 i = 0; i < l; ++i) {
      if (d.candidates[i] == candidate) {
        if (i + 1 < l) {
          d.candidates[i] = d.candidates[l-1];
        }
        d.candidates.pop();
        return;
      }
    }
  }

  function getRoundAccuredReward(address candidate, uint256 round) internal view returns (uint256 reward) {
    reward = accuredRewardMap[candidate][round];
    if (reward != 0) {
      return reward;
    }
    // if there's no field with the round,
    // use binary search to get the previous nearest round.
    Candidate storage c = candidatesMap[candidate];
    uint256 b = c.continuousRewardEndRounds.length;
    if (b == 0) {
      return 0;
    }
    b -= 1;
    uint256 a;
    uint256 m;
    uint256 tr;
    while (a <= b) {
      m = (a + b) / 2;
      tr = c.continuousRewardEndRounds[m];
      // tr should never be equal to round because the above reward value is zero.
      if (tr < round) {
        reward = accuredRewardMap[candidate][tr];
        a = m + 1;
      } else if (m == 0) {
        return 0;
      } else {
        b = m - 1;
      }
    }
    return reward;
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "requiredCoinDeposit")) {
      uint256 newRequiredCoinDeposit = BytesToTypes.bytesToUint256(32, value);
      if (newRequiredCoinDeposit == 0) {
        revert OutOfBounds(key, newRequiredCoinDeposit, 1, type(uint256).max);
      }
      requiredCoinDeposit = newRequiredCoinDeposit;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /*********************** Public view ********************************/
  /// Get delegator information
  /// @param candidate The operator address of candidate
  /// @param delegator The delegator address
  /// @return CoinDelegator Information of the delegator
  function getDelegator(address candidate, address delegator) external view returns (CoinDelegator memory) {
    return candidatesMap[candidate].cDelegatorMap[delegator];
  }

  function getCandidateListByDelegator(address delegator) external view returns (address[] memory) {
    return delegatorsMap[delegator].candidates;
  }
}