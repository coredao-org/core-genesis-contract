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

/// This contract handles CORE staking.
contract CoreAgent is IAgent, System, IParamSubscriber {

  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;

  // minimal CORE require to stake
  uint256 public requiredCoinDeposit;

  // Accured reward of every 1 million CORE per validator on each round
  // validator => (round => 1 million CORE Reward)
  mapping(address => mapping(uint256 => uint256)) public accuredRewardMap;

  // key: delegator address
  // value: delegator info
  mapping(address => Delegator) public delegatorMap;

  // key: candidate op address
  // value: candidate info
  mapping(address => Candidate) public candidateMap;

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
    uint256 realtimeAmount;
    uint256 changeRound;
    uint256 transferredAmount;
  }

  struct Candidate {
    mapping(address => CoinDelegator) cDelegatorMap;
    // Staked amount on last turnround snapshot
    uint256 amount;
    // Realtime staked amount
    uint256 realtimeAmount;
    uint256[] continuousRewardEndRounds;
  }

  struct Delegator {
    address[] candidates;
    uint256 amount;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedCoin(address indexed candidate, address indexed delegator, uint256 amount, uint256 realtimeAmount);
  event undelegatedCoin(address indexed candidate, address indexed delegator, uint256 amount);
  event transferredCoin(
    address indexed sourceCandidate,
    address indexed targetCandidate,
    address indexed delegator,
    uint256 amount,
    uint256 realtimeAmount
  );
  event claimedReward(address indexed delegator, uint256 amount);

  modifier onlyPledgeAgent() {
    require(msg.sender == PLEDGE_AGENT_ADDR, "the sender must be PledgeAgent contract");
    _;
  }

  /*********************** Init ********************************/
  function init() external onlyNotInit {
    requiredCoinDeposit = INIT_REQUIRED_COIN_DEPOSIT;
    roundTag = block.timestamp / SatoshiPlusHelper.ROUND_INTERVAL;
    alreadyInit = true;
  }

  function _initializeFromPledgeAgent(address[] memory candidates, uint256[] memory amounts, uint256[] memory realtimeAmounts) external onlyPledgeAgent {
    uint256 s = candidates.length;
    for (uint256 i = 0; i < s; ++i) {
      Candidate storage c = candidateMap[candidates[i]];
      c.amount = amounts[i];
      c.realtimeAmount = realtimeAmounts[i];
    }
  }

  /*********************** IAgent implementations ***************************/
  /// Prepare for the new round
  /// @param round The new round tag
  function prepare(uint256 round) external override {
    // Nothing to prepare
  }

  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round.
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
      Candidate storage c = candidateMap[validator];
      l = c.continuousRewardEndRounds.length;
      if (l != 0) {
        lastRewardRound = c.continuousRewardEndRounds[l - 1];
        historyReward = m[lastRewardRound];
      } else {
        historyReward = 0;
        lastRewardRound = 0;
      }
      // Calculate accured reward of 1M Core on a validator for the round
      m[round] = historyReward + rewardList[i] * SatoshiPlusHelper.CORE_STAKE_DECIMAL / c.amount;
      if (lastRewardRound + 1 == round) {
        c.continuousRewardEndRounds[l - 1] = round;
      } else {
        c.continuousRewardEndRounds.push(round);
      }
    }
  }

  /// Get staked CORE amount
  /// @param candidates List of candidate operator addresses
  ///
  /// @return amounts List of staked CORE amounts on all candidates in the round
  /// @return totalAmount Total staked CORE on all candidates in the round
  function getStakeAmounts(address[] calldata candidates, uint256) external override view returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    amounts = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; ++i) {
      amounts[i] = candidateMap[candidates[i]].realtimeAmount;
      totalAmount += amounts[i];
    }
  }

  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    uint256 validatorSize = validators.length;
    for (uint256 i = 0; i < validatorSize; ++i) {
      Candidate storage a = candidateMap[validators[i]];
      a.amount = a.realtimeAmount;
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
    require(msg.value >= requiredCoinDeposit, "delegate amount is too small");
    uint256 realtimeAmount = delegateCoin(candidate, msg.sender, msg.value, false);
    emit delegatedCoin(candidate, msg.sender, msg.value, realtimeAmount);
  }

  /// Undelegate coin from a validator
  /// @param candidate The operator address of validator
  /// @param amount The amount of CORE to undelegate
  function undelegateCoin(address candidate, uint256 amount) public {
    require(amount >= requiredCoinDeposit, "undelegate amount is too small");
    undelegateCoin(candidate, msg.sender, amount, false);
    Address.sendValue(payable(msg.sender), amount);
    emit undelegatedCoin(candidate, msg.sender, amount);
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
    require(amount >= requiredCoinDeposit, "transfer amount is too small");
    undelegateCoin(sourceCandidate, msg.sender, amount, true);
    uint256 newDeposit = delegateCoin(targetCandidate, msg.sender, amount, true);

    emit transferredCoin(sourceCandidate, targetCandidate, msg.sender, amount, newDeposit);
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  function claimReward(address delegator) external override onlyStakeHub returns (uint256 reward, uint256 rewardUnclaimed) {
    reward = calculateReward(delegator, true);
    return (reward, 0);
  }

  /// Calculate reward without clearing the cache.
  /// @param delegator the delegator address
  function calculateReward(address delegator) external returns (uint256) {
    return calculateReward(delegator, false);
  }

  /*********************** Receive data from PledgeAgent ***************************/
  /// move staking data for a candidate/delegator pair from PledgeAgent
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  /// @param stakedAmount the staked amount of last round snapshot
  /// @param transferredAmount the transferred out amount counted in reward calculation
  /// @param round data of the round
  function moveData(address candidate, address delegator, uint256 stakedAmount, uint256 transferredAmount, uint256 round) external payable onlyPledgeAgent {
    uint256 realtimeAmount = msg.value;
    require(stakedAmount <= realtimeAmount, "require stakedAmount <= realtimeAmount");
    Candidate storage a = candidateMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    if (changeRound == 0) {
      cd.changeRound = roundTag - 1;
      delegatorMap[delegator].candidates.push(candidate);
    } else if (changeRound != roundTag) {
      uint256 reward = collectCoinReward(candidate, cd);
      rewardMap[delegator] += reward;
    }
    if (round < roundTag) {
      (uint256 reward,) = collectReward(candidate, stakedAmount, realtimeAmount,  transferredAmount, round);
      stakedAmount = realtimeAmount;
      rewardMap[delegator] += reward;
      cd.changeRound = roundTag;
    } else {
      cd.transferredAmount += transferredAmount;
    }
    cd.stakedAmount += stakedAmount;
    cd.realtimeAmount += realtimeAmount;
    delegatorMap[delegator].amount += realtimeAmount;
  }

  /// for backward compatibility - allow users to stake through PledgeAgent
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  function proxyDelegate(address candidate, address delegator) external payable onlyPledgeAgent {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(candidate)) {
      revert InactiveCandidate(candidate);
    }
    require(msg.value >= requiredCoinDeposit, "delegate amount is too small");
    uint256 realtimeAmount = delegateCoin(candidate, delegator, msg.value, false);
    emit delegatedCoin(candidate, delegator, msg.value, realtimeAmount);
  }

  /// for backward compatibility - allow users to unstake through PledgeAgent
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  /// @param amount the amount of CORE to unstake
  function proxyUnDelegate(address candidate, address delegator, uint256 amount) external onlyPledgeAgent {
    require(amount >= requiredCoinDeposit, "undelegate amount is too small");
    undelegateCoin(candidate, delegator, amount, false);
    Address.sendValue(payable(delegator), amount);
    emit undelegatedCoin(candidate, delegator, amount);
  }

  /// for backward compatibility - allow users to transfer stake through PledgeAgent
  /// @param sourceCandidate the validator candidate address to transfer from
  /// @param targetCandidate the validator candidate address to transfer to
  /// @param delegator the delegator address
  /// @param amount the amount of CORE to unstake
  function proxyTransfer(address sourceCandidate, address targetCandidate, address delegator, uint256 amount) external onlyPledgeAgent {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetCandidate)) {
      revert InactiveCandidate(targetCandidate);
    }
    if (sourceCandidate == targetCandidate) {
      revert SameCandidate(sourceCandidate);
    }
    require(amount >= requiredCoinDeposit, "transfer amount is too small");
    undelegateCoin(sourceCandidate, delegator, amount, true);
    uint256 newDeposit = delegateCoin(targetCandidate, delegator, amount, true);

    emit transferredCoin(sourceCandidate, targetCandidate, delegator, amount, newDeposit);
  }

  /*********************** Internal methods ***************************/
  function delegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256) {
    Candidate storage a = candidateMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    if (changeRound == 0) {
      cd.changeRound = roundTag;
      delegatorMap[delegator].candidates.push(candidate);
    } else if (changeRound != roundTag) {
      uint256 reward = collectCoinReward(candidate, cd);
      rewardMap[delegator] += reward;
    }
    a.realtimeAmount += amount;
    cd.realtimeAmount += amount;
    if (!isTransfer) {
      delegatorMap[delegator].amount += amount;
    }

    return cd.realtimeAmount;
  }

  function undelegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256) {
    Candidate storage a = candidateMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    require(changeRound != 0, 'no delegator information found');
    if (changeRound != roundTag) {
      uint256 reward = collectCoinReward(candidate, cd);
      rewardMap[delegator] += reward;
    }

    // design updates vs 1.0.3 hardfork
    // to simplify the reward calculation for user transfers
    // a restriction is made that no more CORE tokens than the turnround snapshot value can be transferred to other validators 
    uint256 stakedAmount = cd.stakedAmount;
    require(stakedAmount >= amount, "Not enough staked tokens");
    if (amount != stakedAmount) {
      require(cd.realtimeAmount - amount >= requiredCoinDeposit, "remain amount is too small");
    }

    a.realtimeAmount -= amount;
    if (isTransfer) {
      cd.transferredAmount += amount;
    } else {
      delegatorMap[delegator].amount -= amount;
    }
    if (!isTransfer && cd.realtimeAmount == amount && cd.transferredAmount == 0) {
      removeDelegation(delegator, candidate);
    } else {
      cd.realtimeAmount -= amount;
      cd.stakedAmount -= amount;
    }
    return amount;
  }

  function collectCoinReward(address candidate, CoinDelegator storage cd) internal returns (uint256 reward) {
    uint256 stakedAmount = cd.stakedAmount;
    uint256 realtimeAmount = cd.realtimeAmount;
    uint256 transferredAmount = cd.transferredAmount;
    bool changed;
    (reward, changed) = collectReward(candidate, stakedAmount, realtimeAmount, transferredAmount, cd.changeRound);
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

  function collectReward(address candidate, uint256 stakedAmount, uint256 realtimeAmount, uint256 transferredAmount, uint256 changeRound) internal returns (uint256 reward, bool changed) {
    require(changeRound != 0, "invalid delegator");
    uint256 lastRoundTag = roundTag - 1;
    if (changeRound <= lastRoundTag) {
      uint256 lastRoundReward = getRoundAccuredReward(candidate, lastRoundTag);
      uint256 lastChangeRoundReward = getRoundAccuredReward(candidate, changeRound - 1);
      uint256 changeRoundReward;
      reward = stakedAmount * (lastRoundReward - lastChangeRoundReward);
      if (transferredAmount != 0) {
        changeRoundReward = getRoundAccuredReward(candidate, changeRound);
        reward += transferredAmount * (changeRoundReward - lastChangeRoundReward);
        transferredAmount = 0;
      }

      if (realtimeAmount != stakedAmount) {
        if (changeRound < lastRoundTag) {
          if (changeRoundReward == 0) {
            changeRoundReward = getRoundAccuredReward(candidate, changeRound);
          }
          reward += (realtimeAmount - stakedAmount) * (lastRoundReward - changeRoundReward);
        }
      }
      reward /= SatoshiPlusHelper.CORE_STAKE_DECIMAL;
      return (reward, true);
    }
    return (0, false);
  }

  function removeDelegation(address delegator, address candidate) internal {
    Delegator storage d = delegatorMap[delegator];
    uint256 l = d.candidates.length;
    for (uint256 i = 0; i < l; ++i) {
      if (d.candidates[i] == candidate) {
        if (i + 1 < l) {
          d.candidates[i] = d.candidates[l-1];
        }
        d.candidates.pop();
        break;
      }
    }
    delete candidateMap[candidate].cDelegatorMap[delegator];
  }

  function getRoundAccuredReward(address candidate, uint256 round) internal returns (uint256 reward) {
    reward = accuredRewardMap[candidate][round];
    if (reward != 0) {
      return reward;
    }
    
    // there might be no rewards for a candidate on a given round if it is unelected or jailed, etc
    // the accrued reward map will only be updated when reward is distributed to the candidate on that round
    // in that case, the accured reward for round N == a round smaller but also closest to N
    // here we use binary search to get that round efficiently
    Candidate storage c = candidateMap[candidate];
    uint256 b = c.continuousRewardEndRounds.length;
    if (b == 0) {
      return 0;
    }
    b -= 1;
    uint256 a;
    uint256 m;
    uint256 targetRound;
    uint256 t;
    while (a <= b) {
      m = (a + b) / 2;
      t = c.continuousRewardEndRounds[m];
      if (t < round) {
        targetRound = t;
        a = m + 1;
      } else if (m == 0) {
        return 0;
      } else {
        b = m - 1;
      }
    }
    if (targetRound != 0) {
      reward = accuredRewardMap[candidate][targetRound];
      accuredRewardMap[candidate][round] = reward;
    }
    return reward;
  }

  function calculateReward(address delegator, bool clearRewardMap) internal returns (uint256 reward) {
    address[] storage candidates = delegatorMap[delegator].candidates;
    uint256 candidateSize = candidates.length;
    address candidate;
    uint256 rewardSum;
    for (uint256 i = candidateSize; i != 0; --i) {
      candidate = candidates[i - 1];
      CoinDelegator storage cd = candidateMap[candidate].cDelegatorMap[delegator];
      reward = collectCoinReward(candidate, cd);
      rewardSum += reward;
      if (cd.realtimeAmount == 0 && cd.transferredAmount == 0) {
        removeDelegation(delegator, candidate);
      }
    }

    reward = rewardMap[delegator];
    if (clearRewardMap) {
      if (reward != 0) {
        rewardMap[delegator] = 0;
      }
    } else if (rewardSum != 0) {
      rewardMap[delegator] = reward + rewardSum;
    }
    return reward + rewardSum;
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

  /*********************** Public view methods ********************************/
  /// Get delegator information
  /// @param candidate The operator address of candidate
  /// @param delegator The delegator address
  /// @return CoinDelegator Information of the delegator
  function getDelegator(address candidate, address delegator) external view returns (CoinDelegator memory) {
    return candidateMap[candidate].cDelegatorMap[delegator];
  }

  /// Get delegator information
  /// @param delegator The delegator address
  /// return the delegated candidates list of the delegator
  function getCandidateListByDelegator(address delegator) external view returns (address[] memory) {
    return delegatorMap[delegator].candidates;
  }
}