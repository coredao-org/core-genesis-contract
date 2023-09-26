// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./System.sol";

/// This contract manages user delegate, also known as stake
/// Including both coin delegate and hash delegate
contract PledgeAgent is IPledgeAgent, System, IParamSubscriber {
  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;
  uint256 public constant INIT_HASH_POWER_FACTOR = 20000;
  uint256 public constant POWER_BLOCK_FACTOR = 1e18;

  uint256 public requiredCoinDeposit;

  // powerFactor/10000 determines the weight of BTC hash power vs CORE stakes
  // the default value of powerFactor is set to 20000 
  // which means the overall BTC hash power takes 2/3 total weight 
  // when calculating hybrid score and distributing block rewards
  uint256 public powerFactor;

  // key: candidate's operateAddr
  mapping(address => Agent) public agentsMap;

  // This field is used to store `special` reward records of delegators. 
  // There are two cases
  //  1, distribute hash power rewards dust to one miner when turn round
  //  2, save the amount of tokens failed to claim by coin delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  // This field is not used in the latest implementation
  // It stays here in order to keep data compatibility for TestNet upgrade
  mapping(bytes20 => address) public btc2ethMap;

  // key: round index
  // value: useful state information of round
  mapping(uint256 => RoundState) public stateMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  struct CoinDelegator {
    uint256 deposit;
    uint256 newDeposit;
    uint256 changeRound;
    uint256 rewardIndex;
  }

  struct Reward {
    uint256 totalReward;
    uint256 remainReward;
    uint256 score;
    uint256 coin;
    uint256 round;
  }

  // The Agent struct for Candidate.
  struct Agent {
    uint256 totalDeposit;
    mapping(address => CoinDelegator) cDelegatorMap;
    Reward[] rewardSet;
    uint256 power;
    uint256 coin;
  }

  struct RoundState {
    uint256 power;
    uint256 coin;
    uint256 powerFactor;
  }

  /*********************** events **************************/
  event paramChange(string key, bytes value);
  event delegatedCoin(address indexed agent, address indexed delegator, uint256 amount, uint256 totalAmount);
  event undelegatedCoin(address indexed agent, address indexed delegator, uint256 amount);
  event transferredCoin(
    address indexed sourceAgent,
    address indexed targetAgent,
    address indexed delegator,
    uint256 amount,
    uint256 totalAmount
  );
  event roundReward(address indexed agent, uint256 coinReward, uint256 powerReward);
  event claimedReward(address indexed delegator, address indexed operator, uint256 amount, bool success);

  /// The validator candidate is inactive, it is expected to be active
  /// @param candidate Address of the validator candidate
  error InactiveAgent(address candidate);

  /// Same source/target addressed provided, it is expected to be different
  /// @param source Address of the source candidate
  /// @param target Address of the target candidate
  error SameCandidate(address source, address target);

  function init() external onlyNotInit {
    requiredCoinDeposit = INIT_REQUIRED_COIN_DEPOSIT;
    powerFactor = INIT_HASH_POWER_FACTOR;
    roundTag = 1;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  
  /* @product Called by the ValidatorSet contract (only) at the beginning of turn round to 
              receive round rewards
     @param agentList: List of validator operator addresses
     @param rewardList: List of reward amounts
     @logic
          For each validator - if the roundScore of the agent's last reward is positive and its (new) 
          reward value is positive then set the agent's last reward's total and remain.reward 
          values to the agent's new reward value
*/
    function addRoundReward(address[] calldata agentList, uint256[] calldata rewardList)
    external
    payable
    override
    onlyValidator
  {
    uint256 agentSize = agentList.length;
    require(agentSize == rewardList.length, "the length of agentList and rewardList should be equal");
    RoundState memory rs = stateMap[roundTag];
    for (uint256 i = 0; i < agentSize; ++i) {
      Agent storage a = agentsMap[agentList[i]];
      if (a.rewardSet.length == 0) {
        continue;
      }
      Reward storage r = a.rewardSet[a.rewardSet.length - 1];
      uint256 roundScore = r.score;
      if (roundScore == 0) {
        delete a.rewardSet[a.rewardSet.length - 1];
        continue;
      }
      if (rewardList[i] == 0) {
        continue;
      }
      r.totalReward = rewardList[i];
      r.remainReward = rewardList[i];
      uint256 coinReward = rewardList[i] * a.coin * rs.power / roundScore;
      uint256 powerReward = rewardList[i] * a.power * rs.coin / 10000 * rs.powerFactor / roundScore;
      emit roundReward(agentList[i], coinReward, powerReward);
    }
  }

/* @product Called by the CandidateHub contract from the turn round flow to calculate hybrid scores for all candidates
   @param candidates: List of candidate operator addresses
   @param powers: List of power values in this round
   @return scores List of hybrid scores of all validator candidates in this round
   @return totalPower Total power delegated in this round
   @return totalCoin Total coin delegated in this round

   @logic
        1. assigns, for each candidate, its power to be the new power value times 
           POWER_BLOCK_FACTOR (=1e18) and its coin value to be its totalDeposit
        2. Calculates the totalPower of all candidates as the sum of all of their (new) power 
           values PLUS ONE @openissue
        3. Calculates the totalCoin of all candidates as the sum of all of their (new) coin 
           values PLUS ONE @openissue
        4. Use these values to calculates the hybrid score for each candidate as follows:
              agent.score = (agent.power * totalCoin * powerFactor / 10000) +  (agent.coin * totalPower)
*/
  function getHybridScore(address[] calldata candidates, uint256[] calldata powers
  ) external override onlyCandidate
      returns (uint256[] memory scores, uint256 totalPower, uint256 totalCoin) {
    uint256 candidateSize = candidates.length;
    require(candidateSize == powers.length, "the length of candidates and powers should be equal");

    totalPower = 1;
    totalCoin = 1;
    // setup `power` and `coin` values for every candidate
    for (uint256 i = 0; i < candidateSize; ++i) {
      Agent storage a = agentsMap[candidates[i]];
      // in order to improve accuracy, the calculation of power is based on 10^18
      a.power = powers[i] * POWER_BLOCK_FACTOR;
      a.coin = a.totalDeposit;
      totalPower += a.power;
      totalCoin += a.coin;
    }

    // calc hybrid score
    scores = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; ++i) {
      Agent storage a = agentsMap[candidates[i]];
      scores[i] = a.power * totalCoin * powerFactor / 10000 + a.coin * totalPower;
    }
    return (scores, totalPower, totalCoin);
  }

/* @product Called by the CandidateHub contract as part of the turn round flow to to start new round
   @param validators: List of elected validators in this round
   @param totalPower: Total power delegated in this round as calculated in getHybridScore()
   @param totalCoin: Total coin delegated in this round as calculated in getHybridScore()
   @param round: The new round tag

   @logic
        1. adds a new round record for the new round with power set to the totalPower value, 
           coin to the totalCoin value, and powerFactor set to the global powerFactor
        2. Sets the global roundTag value to be that of the new round
        3. For each validator calculates a score as follows:
               new.agent.score = (agent.power * totalCoin * powerFactor / 10000)  +  (agent.coin * totalPower)
           
           and adds a new reward to the agent's list for the new round with the new.agent.score 
           and the agent's coin value
*/
  function setNewRound(address[] calldata validators, uint256 totalPower,
      uint256 totalCoin, uint256 round) external override onlyCandidate {
    RoundState memory rs;
    rs.power = totalPower;
    rs.coin = totalCoin;
    rs.powerFactor = powerFactor;
    stateMap[round] = rs;

    roundTag = round;
    uint256 validatorSize = validators.length;
    for (uint256 i = 0; i < validatorSize; ++i) {
      Agent storage a = agentsMap[validators[i]];
      uint256 score = a.power * rs.coin * powerFactor / 10000 + a.coin * rs.power;
      a.rewardSet.push(Reward(0, 0, score, a.coin, round));
    }
  }

/* @product Called by the CandidateHub contract from the turn round flow to distribute rewards for delegated hash 
    power for a single validator candidate
   @param candidate: The operator address of the validator candidate
   @param miners: List of BTC miners who delegated hash power to the candidate
   
   @logic
        1. Find the candidate.round.reward record i.e. the reward for the current round 
           and verify its totalReward value is positive
        2. Calculate a reward.value = 
              current.round.coin * 1e18 * current.round.powerFactor / 10000 * agent.reward.totalReward / agent.reward.score
        3. Increase the reward of all the miners in the miners list by reward.value
        4. Calculate a powerReward value  = reward.value * number.of.candidate.miners
        5. Calculate a undelegated.coin.reward initial value as follows:
            if (candidate.coin > candidate.round.reward.coin)
                undelegated.coin.reward = candidate.round.reward.totalReward * (candidate.coin - candidate.round.reward.coin) * this.round.power / candidate.round.reward.score;
            else
                undelegated.coin.reward = 0

        6. If candidate.round.reward.coin = 0 then delete the candidate.round.reward record and
            set undelegated.coin.reward = candidate.round.remainReward - powerReward
        7. Else, if either powerReward or undelegated.coin.reward are positive, subtract their 
           sum from candidate.round.reward.remainReward:
        8. Finally, if undelegated.coin.reward is positive, call the SystemReward's receiveRewards() 
           service with eth value of undelegated.coin.reward to store the rewards
*/
  function distributePowerReward(address candidate, address[] calldata miners) external override onlyCandidate {
    // distribute rewards to every miner
    // note that the miners are represented in the form of reward addresses
    // and they can be duplicated because everytime a miner delegates a BTC block
    // to a validator on Core blockchain, a new record is added in BTCLightClient
    Agent storage a = agentsMap[candidate];
    uint256 l = a.rewardSet.length;
    if (l == 0) {
      return;
    }
    Reward storage r = a.rewardSet[l-1];
    if (r.totalReward == 0 || r.round != roundTag) {
      return;
    }
    RoundState storage rs = stateMap[roundTag];
    uint256 reward = rs.coin * POWER_BLOCK_FACTOR * rs.powerFactor / 10000 * r.totalReward / r.score;
    uint256 minerSize = miners.length;

    uint256 powerReward = reward * minerSize;
    uint256 undelegateCoinReward;
    if (a.coin > r.coin) {
      // undelegatedCoin = a.coin - r.coin
      undelegateCoinReward = r.totalReward * (a.coin - r.coin) * rs.power / r.score;
    }
    uint256 remainReward = r.remainReward;
    require(remainReward >= powerReward + undelegateCoinReward, "there is not enough reward");

    for (uint256 i = 0; i < minerSize; i++) {
      rewardMap[miners[i]] += reward;
    }

    if (r.coin == 0) {
      delete a.rewardSet[l-1];
      undelegateCoinReward = remainReward - powerReward;
    } else if (powerReward != 0 || undelegateCoinReward != 0) {
      r.remainReward -= (powerReward + undelegateCoinReward);
    }

    if (undelegateCoinReward != 0) {
      ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: undelegateCoinReward }();
    }
  }

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param agent The operator address of validator
  function delegateCoin(address agent) external payable {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent)) {
      revert InactiveAgent(agent);
    }
    uint256 newDeposit = delegateCoin(agent, msg.sender, msg.value);
    emit delegatedCoin(agent, msg.sender, msg.value, newDeposit);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  function undelegateCoin(address agent) external {
    uint256 deposit = undelegateCoin(agent, msg.sender);
    payable(msg.sender).transfer(deposit);
    emit undelegatedCoin(agent, msg.sender, deposit);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  function transferCoin(address sourceAgent, address targetAgent) external {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent)) {
      revert InactiveAgent(targetAgent);
    }
    if (sourceAgent == targetAgent) {
      revert SameCandidate(sourceAgent, targetAgent);
    }
    uint256 deposit = undelegateCoin(sourceAgent, msg.sender);
    uint256 newDeposit = delegateCoin(targetAgent, msg.sender, deposit);
    emit transferredCoin(sourceAgent, targetAgent, msg.sender, deposit, newDeposit);
  }

  /// Claim reward for delegator
  /// @param agentList The list of validators to claim rewards on, it can be empty
  /// @return (Amount claimed, Are all rewards claimed)
  function claimReward(address[] calldata agentList) external returns (uint256, bool) {
    // limit round count to control gas usage
    int256 roundLimit = 500;
    uint256 reward;
    uint256 rewardSum = rewardMap[msg.sender];
    if (rewardSum != 0) {
      rewardMap[msg.sender] = 0;
    }

    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      Agent storage a = agentsMap[agentList[i]];
      if (a.rewardSet.length == 0) continue;
      CoinDelegator storage d = a.cDelegatorMap[msg.sender];
      if (d.newDeposit == 0) continue;
      int256 roundCount = int256(a.rewardSet.length - d.rewardIndex);
      reward = collectCoinReward(a, d, roundLimit);
      roundLimit -= roundCount;
      rewardSum += reward;
      // if there are rewards to be collected, leave them there
      if (roundLimit < 0) break;
    }
    if (rewardSum != 0) {
      distributeReward(payable(msg.sender), rewardSum);
    }
    return (rewardSum, roundLimit >= 0);
  }

  /*********************** Internal methods ***************************/
  function distributeReward(address payable delegator, uint256 reward) internal {
    (bool success, bytes memory data) = delegator.call{value: reward, gas: 50000}("");
    emit claimedReward(delegator, msg.sender, reward, success);
    if (!success) {
      rewardMap[msg.sender] = reward;
    }
  }

  function delegateCoin(
    address agent,
    address delegator,
    uint256 deposit
  ) internal returns (uint256) {
    Agent storage a = agentsMap[agent];
    uint256 newDeposit = a.cDelegatorMap[delegator].newDeposit + deposit;

    a.totalDeposit += deposit;
    if (newDeposit == deposit) {
      require(deposit >= requiredCoinDeposit, "deposit is too small");
      uint256 rewardIndex = a.rewardSet.length;
      a.cDelegatorMap[delegator] = CoinDelegator(0, deposit, roundTag, rewardIndex);
    } else {
      require(deposit != 0, "deposit value is zero");
      CoinDelegator storage d = a.cDelegatorMap[delegator];
      uint256 rewardAmount = collectCoinReward(a, d, 0x7FFFFFFF);
      if (d.changeRound < roundTag) {
        d.deposit = d.newDeposit;
        d.changeRound = roundTag;
      }
      d.newDeposit = newDeposit;
      if (rewardAmount > 0) {
        distributeReward(payable(delegator), rewardAmount);
      }
    }
    return newDeposit;
  }

  function undelegateCoin(address agent, address delegator) internal returns (uint256) {
    Agent storage a = agentsMap[agent];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    uint256 newDeposit = d.newDeposit;
    require(newDeposit != 0, "delegator does not exist");

    uint256 rewardAmount = collectCoinReward(a, d, 0x7FFFFFFF);

    a.totalDeposit -= newDeposit;
    if (a.rewardSet.length != 0) {
      Reward storage r = a.rewardSet[a.rewardSet.length - 1];
      if (r.round == roundTag) {
        if (d.changeRound < roundTag) {
          r.coin -= newDeposit;
        } else {
          r.coin -= d.deposit;
        }
      }
    }
    delete a.cDelegatorMap[delegator];
    if (rewardAmount > 0) {
      distributeReward(payable(delegator), rewardAmount);
    }
    return newDeposit;
  }

  function collectCoinReward(
    Agent storage a,
    CoinDelegator storage d,
    int256 roundLimit
  ) internal returns (uint256 rewardAmount) {
    uint256 rewardLength = a.rewardSet.length;
    uint256 rewardIndex = d.rewardIndex;
    rewardAmount = 0;
    if (rewardIndex >= rewardLength) {
      return rewardAmount;
    }
    if (rewardIndex + uint256(roundLimit) < rewardLength) {
      rewardLength = rewardIndex + uint256(roundLimit);
    }
    uint256 curReward;
    uint256 changeRound = d.changeRound;

    while (rewardIndex < rewardLength) {
      Reward storage r = a.rewardSet[rewardIndex];
      if (r.round == roundTag) break;
      uint256 deposit = d.newDeposit;
      if (r.round == changeRound) {
        deposit = d.deposit;
        d.deposit = d.newDeposit;
      }
      require(r.coin >= deposit, "reward is not enough");
      if (r.coin == deposit) {
        curReward = r.remainReward;
        delete a.rewardSet[rewardIndex];
      } else {
        uint256 rsPower = stateMap[r.round].power;
        curReward = (r.totalReward * deposit * rsPower) / r.score;
        require(r.remainReward >= curReward, "there is not enough reward");
        r.coin -= deposit;
        r.remainReward -= curReward;
      }
      rewardAmount += curReward;
      rewardIndex++;
    }

    // update index whenever claim happens
    d.rewardIndex = rewardIndex;
    return rewardAmount;
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
    } else if (Memory.compareStrings(key, "powerFactor")) {
      uint256 newHashPowerFactor = BytesToTypes.bytesToUint256(32, value);
      if (newHashPowerFactor == 0) {
        revert OutOfBounds(key, newHashPowerFactor, 1, type(uint256).max);
      }
      powerFactor = newHashPowerFactor;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /*********************** Public view ********************************/
  /// Get delegator information
  /// @param agent The operator address of validator
  /// @param delegator The delegator address
  /// @return CoinDelegator Information of the delegator
  function getDelegator(address agent, address delegator) external view returns (CoinDelegator memory) {
    return agentsMap[agent].cDelegatorMap[delegator];
  }

  /// Get reward information of a validator by index
  /// @param agent The operator address of validator
  /// @param index The reward index
  /// @return Reward The reward information
  function getReward(address agent, uint256 index) external view returns (Reward memory) {
    Agent storage a = agentsMap[agent];
    require(index < a.rewardSet.length, "out of up bound");
    return a.rewardSet[index];
  }
}
