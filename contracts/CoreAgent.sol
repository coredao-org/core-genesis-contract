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
  mapping(address => Reward) public rewardMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  struct CoinDelegator {
    uint256 stakedAmount;
    uint256 realtimeAmount;
    uint256 transferredAmount;
    uint256 changeRound;
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

  struct Reward {
    uint256 reward;
    uint256 accStakedAmount;
  }

  /*********************** events **************************/
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
    uint256 realtimeAmount = _delegateCoin(candidate, msg.sender, msg.value, false);
    emit delegatedCoin(candidate, msg.sender, msg.value, realtimeAmount);
  }

  /// Undelegate coin from a validator
  /// @param candidate The operator address of validator
  /// @param amount The amount of CORE to undelegate
  function undelegateCoin(address candidate, uint256 amount) public {
    uint256 dAmount = _undelegateCoin(candidate, msg.sender, amount, false);
    _deductTransferredAmount(msg.sender, dAmount);
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
    _undelegateCoin(sourceCandidate, msg.sender, amount, true);
    uint256 newDeposit = _delegateCoin(targetCandidate, msg.sender, amount, true);

    emit transferredCoin(sourceCandidate, targetCandidate, msg.sender, amount, newDeposit);
  }


  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return floatReward floating reward amount
  /// @return accStakedAmount accumulated stake amount (multipled by rounds), used for grading calculation
  function claimReward(address delegator, uint256 /*coreAmount*/) external override onlyStakeHub returns (uint256 reward, int256 floatReward, uint256 accStakedAmount) {
    address[] storage candidates = delegatorMap[delegator].candidates;
    uint256 candidateSize = candidates.length;
    address candidate;
    uint256 rewardSum;
    uint256 accStakedAmountSum;
    for (uint256 i = candidateSize; i != 0; --i) {
      candidate = candidates[i - 1];
      CoinDelegator storage cd = candidateMap[candidate].cDelegatorMap[delegator];
      (reward, accStakedAmount) = _collectRewardFromCandidate(candidate, cd);
      rewardSum += reward;
      accStakedAmountSum += accStakedAmount;
      if (cd.realtimeAmount == 0 && cd.transferredAmount == 0) {
        _removeDelegation(delegator, candidate);
      }
    }

    reward = rewardMap[delegator].reward;
    accStakedAmount = rewardMap[delegator].accStakedAmount;
    if (accStakedAmount != 0 || reward != 0) {
      delete rewardMap[delegator];
    }
    return (reward + rewardSum, 0, accStakedAmount + accStakedAmountSum);
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
      cd.changeRound = roundTag;
      delegatorMap[delegator].candidates.push(candidate);
    } else if (changeRound != roundTag) {
      (uint256 reward, uint256 accStakedAmount) = _collectRewardFromCandidate(candidate, cd);
      rewardMap[delegator].reward += reward;
      rewardMap[delegator].accStakedAmount += accStakedAmount;
    }
    if (round < roundTag) {
      (uint256 reward,,uint256 accStakedAmount) = _collectReward(candidate, stakedAmount, realtimeAmount, transferredAmount, round);
      stakedAmount = realtimeAmount;
      rewardMap[delegator].reward += reward;
      rewardMap[delegator].accStakedAmount += accStakedAmount;
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
    uint256 realtimeAmount = _delegateCoin(candidate, delegator, msg.value, false);
    emit delegatedCoin(candidate, delegator, msg.value, realtimeAmount);
  }

  /// for backward compatibility - allow users to unstake through PledgeAgent
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  /// @param amount the amount of CORE to unstake
  function proxyUnDelegate(address candidate, address delegator, uint256 amount) external onlyPledgeAgent returns(uint256) {
    if (amount == 0) {
      amount = candidateMap[candidate].cDelegatorMap[delegator].realtimeAmount;
    }
    uint256 dAmount = _undelegateCoin(candidate, delegator, amount, false);
    _deductTransferredAmount(delegator, dAmount);
    Address.sendValue(payable(PLEDGE_AGENT_ADDR), amount);
    emit undelegatedCoin(candidate, delegator, amount);
    return amount;
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
    if (amount == 0) {
      amount = candidateMap[sourceCandidate].cDelegatorMap[delegator].realtimeAmount;
    }
    _undelegateCoin(sourceCandidate, delegator, amount, true);
    uint256 newDeposit = _delegateCoin(targetCandidate, delegator, amount, true);

    emit transferredCoin(sourceCandidate, targetCandidate, delegator, amount, newDeposit);
  }

  /*********************** Internal methods ***************************/
  /// delegate CORE tokens
  /// @param candidate the validator candidate to delegate to
  /// @param delegator the delegator address
  /// @param amount the amount of CORE 
  /// @param isTransfer is called from transfer workflow
  function _delegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256) {
    Candidate storage a = candidateMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    if (changeRound == 0) {
      cd.changeRound = roundTag;
      delegatorMap[delegator].candidates.push(candidate);
    } else if (changeRound != roundTag) {
      (uint256 reward, uint256 accStakedAmount) = _collectRewardFromCandidate(candidate, cd);
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

  /// undelegate CORE tokens
  /// @param candidate the validator candidate to delegate to
  /// @param delegator the delegator address
  /// @param amount the amount of CORE 
  /// @param isTransfer is called from transfer workflow
  /// @return undelegatedNewAmount the amount minuses the reduced staked amount.
  function _undelegateCoin(address candidate, address delegator, uint256 amount, bool isTransfer) internal returns (uint256 undelegatedNewAmount) {
    require(amount != 0, 'Undelegate zero coin');
    Candidate storage a = candidateMap[candidate];
    CoinDelegator storage cd = a.cDelegatorMap[delegator];
    uint256 changeRound = cd.changeRound;
    require(changeRound != 0, 'no delegator information found');
    if (changeRound != roundTag) {
      (uint256 reward, uint256 accStakedAmount) = _collectRewardFromCandidate(candidate, cd);
      rewardMap[delegator].reward += reward;
      rewardMap[delegator].accStakedAmount += accStakedAmount;
    }

    // design updates in 1.0.12 vs 1.0.3
    // to simplify the reward calculation for user transfers
    // a restriction is made that no more CORE tokens than the turnround
    // snapshot value can be transferred to other validators
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

  function _deductTransferredAmount(address delegator, uint256 amount) internal {
    Delegator storage d = delegatorMap[delegator];
    address[] storage candidates = d.candidates;
    address candidate;
    uint256 transferredAmount;
    for (uint256 i = candidates.length; i != 0; --i) {
      candidate = candidates[i - 1];
      CoinDelegator storage cd = candidateMap[candidate].cDelegatorMap[delegator];
      transferredAmount = cd.transferredAmount;
      if (transferredAmount != 0) {
        if (transferredAmount < amount) {
          amount -= transferredAmount;
          cd.transferredAmount = 0;
          if (cd.realtimeAmount == 0) {
            delete candidateMap[candidate].cDelegatorMap[delegator];
            if (i < candidates.length) {
              d.candidates[i-1] = d.candidates[candidates.length-1];
            }
            d.candidates.pop();
          }
        } else {
          cd.transferredAmount -= amount;
          break;
        }
      }
    }
  }

  /// collect reward from a validator candidate
  /// @param candidate the validator candidate to collect rewards
  /// @param cd the structure stores user CORE stake information
  /// @return reward The amount of CORE collected
  /// @return accStakedAmount accumulated stake amount (multipled by days), used for grading calculation
  function _collectRewardFromCandidate(address candidate, CoinDelegator storage cd) internal returns (uint256 reward, uint256 accStakedAmount) {
    uint256 stakedAmount = cd.stakedAmount;
    uint256 realtimeAmount = cd.realtimeAmount;
    uint256 transferredAmount = cd.transferredAmount;
    bool changed;
    (reward, changed, accStakedAmount) = _collectReward(candidate, stakedAmount, realtimeAmount, transferredAmount, cd.changeRound);
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

  /// collect rewards on a candidate with full parameters
  /// @param candidate the candidate to collect reward from
  /// @param stakedAmount CORE amount of last turn round snapshot
  /// @param realtimeAmount realtime staked CORE amount
  /// @param transferredAmount transferred in CORE amount, also eligible for rewards
  /// @param changeRound the last round when the delegator acted
  /// @return reward the amount of rewards collected
  /// @return changed whether the changedRound value should be updated
  /// @return accStakedAmount accumulated stake amount (multipled by days), used for grading calculation
  function _collectReward(address candidate, uint256 stakedAmount, uint256 realtimeAmount, uint256 transferredAmount, uint256 changeRound) internal returns (uint256 reward, bool changed, uint256 accStakedAmount) {
    require(changeRound != 0, "invalid delegator");
    uint256 lastRoundTag = roundTag - 1;
    if (changeRound <= lastRoundTag) {
      uint256 lastRoundReward = _getRoundAccuredReward(candidate, lastRoundTag);
      uint256 lastChangeRoundReward = _getRoundAccuredReward(candidate, changeRound - 1);
      uint256 changeRoundReward;
      reward = stakedAmount * (lastRoundReward - lastChangeRoundReward);
      accStakedAmount = stakedAmount * (lastRoundTag - changeRound + 1);
      
      if (transferredAmount != 0) {
        changeRoundReward = _getRoundAccuredReward(candidate, changeRound);
        reward += transferredAmount * (changeRoundReward - lastChangeRoundReward);
        accStakedAmount += transferredAmount;
      }

      if (realtimeAmount != stakedAmount) {
        if (changeRound < lastRoundTag) {
          if (changeRoundReward == 0) {
            changeRoundReward = _getRoundAccuredReward(candidate, changeRound);
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

  /// remove delegate record of a candidate/delegator pair
  /// @param delegator the delegator address
  /// @param candidate the validator candidate address
  function _removeDelegation(address delegator, address candidate) internal {
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

  /// get accured rewards of a validator candidate on a given round
  /// @param candidate validator candidate address
  /// @param round the round to calculate rewards
  /// @return reward the amount of rewards
  function _getRoundAccuredReward(address candidate, uint256 round) internal returns (uint256 reward) {
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
      revert UnsupportedGovParam(key);
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