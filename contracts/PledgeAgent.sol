// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./lib/Address.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./System.sol";

/// This contract manages user delegate, also known as stake
/// Including both coin delegate and hash delegate

/// HARDFORK V-1.0.3
/// `effective transfer` is introduced in this hardfork to keep the rewards for users 
/// when transferring CORE tokens from one validator to another
/// `effective transfer` only contains the amount of CORE tokens transferred 
/// which are eligible for claiming rewards in the acting round

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

  // HARDFORK V-1.0.3 
  // debtDepositMap keeps delegator's amount of CORE which should be deducted when claiming rewards in every round
  mapping(uint256 => mapping(address => uint256)) public debtDepositMap;

  struct CoinDelegator {
    uint256 deposit;
    uint256 newDeposit;
    uint256 changeRound;
    uint256 rewardIndex;
    // HARDFORK V-1.0.3
    // transferOutDeposit keeps the `effective transfer` out of changeRound
    // transferInDeposit keeps the `effective transfer` in of changeRound
    uint256 transferOutDeposit;
    uint256 transferInDeposit;
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
  /// Receive round rewards from ValidatorSet, which is triggered at the beginning of turn round
  /// @param agentList List of validator operator addresses
  /// @param rewardList List of reward amount
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

  /// Calculate hybrid score for all candidates
  /// @param candidates List of candidate operator addresses
  /// @param powers List of power value in this round
  /// @return scores List of hybrid scores of all validator candidates in this round
  /// @return totalPower Total power delegate in this round
  /// @return totalCoin Total coin delegate in this round
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

  /// Start new round, this is called by the CandidateHub contract
  /// @param validators List of elected validators in this round
  /// @param totalPower Total power delegate in this round
  /// @param totalCoin Total coin delegate in this round
  /// @param round The new round tag
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

  /// Distribute rewards for delegated hash power on one validator candidate
  /// This method is called at the beginning of `turn round` workflow
  /// @param candidate The operator address of the validator candidate
  /// @param miners List of BTC miners who delegated hash power to the candidate
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

  function onFelony(address agent) external override onlyValidator {
    Agent storage a = agentsMap[agent];
    uint256 len = a.rewardSet.length;
    if (len > 0) {
      Reward storage r = a.rewardSet[len-1];
      if (r.round == roundTag && r.coin == 0) {
        delete a.rewardSet[len-1];
      }
    }
  }

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param agent The operator address of validator
  function delegateCoin(address agent) external payable {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent)) {
      revert InactiveAgent(agent);
    }
    uint256 newDeposit = delegateCoin(agent, msg.sender, msg.value, 0);
    emit delegatedCoin(agent, msg.sender, msg.value, newDeposit);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  function undelegateCoin(address agent) external {
    undelegateCoin(agent, 0);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  /// @param amount The amount of CORE to undelegate
  function undelegateCoin(address agent, uint256 amount) public {
    (uint256 deposit, ) = undelegateCoin(agent, msg.sender, amount, false);
    Address.sendValue(payable(msg.sender), deposit);
    emit undelegatedCoin(agent, msg.sender, deposit);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  function transferCoin(address sourceAgent, address targetAgent) external {
    transferCoin(sourceAgent, targetAgent, 0);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  /// @param amount The amount of CORE to transfer
  function transferCoin(address sourceAgent, address targetAgent, uint256 amount) public {
    if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent)) {
      revert InactiveAgent(targetAgent);
    }
    if (sourceAgent == targetAgent) {
      revert SameCandidate(sourceAgent, targetAgent);
    }
    (uint256 deposit, uint256 deductedDeposit) = undelegateCoin(sourceAgent, msg.sender, amount, true);
    uint256 newDeposit = delegateCoin(targetAgent, msg.sender, deposit, deductedDeposit);

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
      if (a.rewardSet.length == 0) {
        continue;
      }
      CoinDelegator storage d = a.cDelegatorMap[msg.sender];
      if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
        continue;
      }
      int256 roundCount = int256(a.rewardSet.length - d.rewardIndex);
      reward = collectCoinReward(a, d, roundLimit);
      roundLimit -= roundCount;
      rewardSum += reward;
      if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
        delete a.cDelegatorMap[msg.sender];
      }
      // if there are rewards to be collected, leave them there
      if (roundLimit < 0) {
        break;
      }
    }

    if (rewardSum != 0) {
      distributeReward(payable(msg.sender), rewardSum);
    }
    return (rewardSum, roundLimit >= 0);
  }

  /*********************** Internal methods ***************************/
  function distributeReward(address payable delegator, uint256 reward) internal {
    Address.sendValue(delegator, reward);
    emit claimedReward(delegator, msg.sender, reward, true);
  }

  function delegateCoin(address agent, address delegator, uint256 deposit, uint256 transferInDeposit) internal returns (uint256) {
    require(deposit >= requiredCoinDeposit, "deposit is too small");
    Agent storage a = agentsMap[agent];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    uint256 rewardAmount;
    if (d.changeRound != 0) {
      rewardAmount = collectCoinReward(a, d, 0x7FFFFFFF);
    }
    a.totalDeposit += deposit;

    if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
      d.newDeposit = deposit;
      d.changeRound = roundTag;
      d.rewardIndex = a.rewardSet.length;
    } else {
      if (d.changeRound < roundTag) {
        d.deposit = d.newDeposit;
        d.changeRound = roundTag;
      }
      d.newDeposit += deposit;
    }

    // HARDFORK V-1.0.3 receive `effective transfer`
    if (transferInDeposit != 0) {
      d.transferInDeposit += transferInDeposit;
    }

    if (rewardAmount != 0) {
      distributeReward(payable(delegator), rewardAmount);
    }
    return d.newDeposit;
  }
  
  function undelegateCoin(address agent, address delegator, uint256 amount, bool isTransfer) internal returns (uint256, uint256) {
    Agent storage a = agentsMap[agent];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    uint256 newDeposit = d.newDeposit;
    if (amount == 0) {
      amount = newDeposit;
    }
    require(newDeposit != 0, "delegator does not exist");
    if (newDeposit != amount) {
      require(amount >= requiredCoinDeposit, "undelegate amount is too small"); 
      require(newDeposit >= requiredCoinDeposit + amount, "remaining amount is too small");
    }
    uint256 rewardAmount = collectCoinReward(a, d, 0x7FFFFFFF);
    a.totalDeposit -= amount;

    // HARDFORK V-1.0.3
    // when handling undelegate, which can be triggered by either REAL undelegate or a transfer
    // the delegated CORE tokens are consumed in the following order
    //  1. the amount of CORE which are not eligible for claiming rewards
    //  2. the amount of self-delegated CORE eligible for claiming rewards (d.deposit)
    //  3. the amount of transferred in CORE eligible for claiming rewards (d.transferInDeposit)
    // deductedInDeposit is the amount of transferred in CORE needs to be deducted from rewards calculation/distribution
    // if it is a REAL undelegate, the value will be added to the DEBT map
    // which takes effect when users claim rewards (or other actions that trigger claiming)
    uint256 deposit = d.changeRound < roundTag ? newDeposit : d.deposit;
    newDeposit -= amount;
    uint256 deductedInDeposit;
    uint256 deductedOutDeposit;
    if (newDeposit < d.transferInDeposit) {
      deductedInDeposit = d.transferInDeposit - newDeposit;
      d.transferInDeposit = newDeposit;
      if (!isTransfer) {
        debtDepositMap[roundTag][msg.sender] += deductedInDeposit;
      }
      deductedOutDeposit = deposit;
    } else if (newDeposit < d.transferInDeposit + deposit) {
      deductedOutDeposit = d.transferInDeposit + deposit - newDeposit;
    }

    // HARDFORK V-1.0.3   
    // deductedOutDeposit is the amount of self-delegated CORE needs to be deducted from rewards calculation/distribution
    // if it is a REAL undelegate, the amount is deducted from the reward set directly
    // otherwise, the amount will be added to d.transferOutDeposit which can be used to claim rewards as d.deposit
    if (deductedOutDeposit != 0) {
      deposit -= deductedOutDeposit;
      if (a.rewardSet.length != 0) {
        Reward storage r = a.rewardSet[a.rewardSet.length - 1];
        if (r.round == roundTag) {
          if (isTransfer) {
            d.transferOutDeposit += deductedOutDeposit;
          } else {
            r.coin -= deductedOutDeposit;
          }
        } else {
          deductedOutDeposit = 0;
        }
      } else {
        deductedOutDeposit = 0;
      }
    }

    if (newDeposit == 0 && d.transferOutDeposit == 0) {
      delete a.cDelegatorMap[delegator];
    } else {
      d.deposit = deposit;
      d.newDeposit = newDeposit;
      d.changeRound = roundTag;
    }

    if (rewardAmount != 0) {
      distributeReward(payable(delegator), rewardAmount);
    }

    return (amount, deductedInDeposit + deductedOutDeposit);
  }

  function collectCoinReward(Reward storage r, uint256 deposit) internal returns (uint256 rewardAmount) {
    require(r.coin >= deposit, "reward is not enough");
    uint256 curReward;
    if (r.coin == deposit) {
      curReward = r.remainReward;
      r.coin = 0;
    } else {
      uint256 rsPower = stateMap[r.round].power;
      curReward = (r.totalReward * deposit * rsPower) / r.score;
      require(r.remainReward >= curReward, "there is not enough reward");
      r.coin -= deposit;
      r.remainReward -= curReward;
    }
    return curReward;
  }

  function collectCoinReward(Agent storage a, CoinDelegator storage d, int256 roundLimit) internal returns (uint256 rewardAmount) {
    uint256 changeRound = d.changeRound;
    uint256 curRound = roundTag;
    if (changeRound < curRound) {
      d.transferInDeposit = 0;
    }

    uint256 rewardLength = a.rewardSet.length;
    uint256 rewardIndex = d.rewardIndex;
    if (rewardIndex >= rewardLength) {
      return 0;
    }
    if (rewardIndex + uint256(roundLimit) < rewardLength) {
      rewardLength = rewardIndex + uint256(roundLimit);
    }

    while (rewardIndex < rewardLength) {
      Reward storage r = a.rewardSet[rewardIndex];
      uint256 rRound = r.round;
      if (rRound == curRound) {
        break;
      }
      uint256 deposit = d.newDeposit;
      // HARDFORK V-1.0.3  
      // d.deposit and d.transferOutDeposit are both eligible for claiming rewards
      // however, d.transferOutDeposit will be used to pay the DEBT for the delegator before that
      // the rewards from the DEBT will be collected and sent to the system reward contract
      if (rRound == changeRound) {
        uint256 transferOutDeposit = d.transferOutDeposit;
        uint256 debt = debtDepositMap[rRound][msg.sender];
        if (transferOutDeposit > debt) {
          transferOutDeposit -= debt;
          debtDepositMap[rRound][msg.sender] = 0;
        } else {
          debtDepositMap[rRound][msg.sender] -= transferOutDeposit;
          transferOutDeposit = 0;
        }
        if (transferOutDeposit != d.transferOutDeposit) {
          uint256 undelegateReward = collectCoinReward(r, d.transferOutDeposit - transferOutDeposit);
          if (r.coin == 0) {
            delete a.rewardSet[rewardIndex];
          }
          ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: undelegateReward }();
        }
        deposit = d.deposit + transferOutDeposit;
        d.deposit = d.newDeposit;
        d.transferOutDeposit = 0;
      }
      if (deposit != 0) {
        rewardAmount += collectCoinReward(r, deposit);
        if (r.coin == 0) {
          delete a.rewardSet[rewardIndex];
        }
      }
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
    CoinDelegator memory d = agentsMap[agent].cDelegatorMap[delegator];
    return d;
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