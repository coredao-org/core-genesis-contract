pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;
import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./System.sol";
import "./lib/SafeMath.sol";

/// This contract manages user delegate, also known as stake
/// Including both coin delegate and hash delegate
contract PledgeAgent is IPledgeAgent, System, IParamSubscriber {
  using SafeMath for uint256;

  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;
  uint256 public constant INIT_HASH_POWER_FACTOR = 20000;
  uint256 public constant DUST_LIMIT = 1e13;
  uint256 public constant POWER_BLOCK_FACTOR = 1e18;

  uint256 public requiredCoinDeposit;

  // powerFactor/10000 determines the weight of BTC hash power vs CORE stakes
  // the default value of powerFactor is set to 20000 
  // which means the overall BTC hash power takes 2/3 total weight 
  // when calculating hybrid score and distributing block rewards
  uint256 public powerFactor;

  // key: candidate's operateAddr
  mapping(address => Agent) public agentsMap;

  // this field is used to store rewards of delegated hash powers
  // key: reward address set by BTC miners
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public powerRewardMap;

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

  // there will be unclaimed rewards when delegators exit.
  // the rewards for the exit day will be delivered by system
  // but can not be claimed - we call them as dust
  uint256 public totalDust;

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
  event claimedPowerReward(address indexed delegator, uint256 amount, bool success);

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
    // if no hash power is delegated in the round, return
    RoundState storage rs = stateMap[roundTag];
    if (rs.power == 1) {
      return;
    }
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
    uint256 reward = rs.coin * POWER_BLOCK_FACTOR * rs.powerFactor / 10000 * r.totalReward / r.score;
    uint256 totalReward = reward * miners.length;
    require(r.remainReward >= totalReward, "there is not enough reward");

    uint256 minerSize = miners.length;
    for (uint256 i = 0; i < minerSize; i++) {
      powerRewardMap[miners[i]] += reward;
    }

    if (r.coin == 0) {
      totalDust += (r.remainReward - totalReward);
      delete a.rewardSet[l-1];
    } else {
      r.remainReward -= totalReward;
    }
  }

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param agent The operator address of validator
  function delegateCoin(address agent) external payable {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent), "agent is inactivated");
    uint256 newDeposit = delegateCoin(agent, msg.sender, msg.value);
    emit delegatedCoin(agent, msg.sender, msg.value, newDeposit);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  function undelegateCoin(address agent) external {
    uint256 deposit = undelegateCoin(agent, msg.sender);
    msg.sender.transfer(deposit);
    emit undelegatedCoin(agent, msg.sender, deposit);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  function transferCoin(address sourceAgent, address targetAgent) external {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent), "agent is inactivated");
    require(sourceAgent!=targetAgent, "source agent and target agent are the same one");
    uint256 deposit = undelegateCoin(sourceAgent, msg.sender);
    uint256 newDeposit = delegateCoin(targetAgent, msg.sender, deposit);
    emit transferredCoin(sourceAgent, targetAgent, msg.sender, deposit, newDeposit);
  }

  /// Claim reward for coin delegate
  /// @param delegator The delegator address
  /// @param agentList The list of validators to claim rewards on
  /// @return (Amount claimed, Are all rewards claimed)
  function claimReward(address payable delegator, address[] calldata agentList) external returns (uint256, bool) {
    // limit round count to control gas usage
    int256 roundLimit = 500;
    uint256 reward;
    uint256 dust;
    uint256 rewardSum = 0;
    uint256 dustSum = 0;

    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      Agent storage a = agentsMap[agentList[i]];
      if (a.rewardSet.length == 0) continue;
      CoinDelegator storage d = a.cDelegatorMap[delegator];
      if (d.newDeposit == 0) continue;
      int256 roundCount = int256(a.rewardSet.length - d.rewardIndex);
      (reward, dust) = collectCoinReward(a, d, roundLimit);
      roundLimit -= roundCount;
      rewardSum += reward;
      dustSum += dust;
      // if there are rewards to be collected, leave them there
      if (roundLimit < 0) break;
    }
    require(rewardSum != 0, "no pledge reward");
    distributeReward(delegator, rewardSum, dustSum);
    return (rewardSum, roundLimit >= 0);
  }

  /// Claim reward for hash power delegate
  function claimPowerReward() external {
    uint256 reward = powerRewardMap[msg.sender];
    if (reward == 0) {
      return;
    }
    powerRewardMap[msg.sender] = 0;
    bool success = msg.sender.send(reward);
    emit claimedPowerReward(msg.sender, reward, success);
    if (!success) {
      totalDust += reward;
    }
  }

  /*********************** Internal methods ***************************/
  function distributeReward(address payable delegator, uint256 reward, uint256 dust) internal {
    if (reward != 0) {
      if (dust <= DUST_LIMIT) {
        reward += dust;
        dust = 0;
      } else {
        reward += DUST_LIMIT;
        dust -= DUST_LIMIT;
      }
      bool success = delegator.send(reward);
      emit claimedReward(delegator, msg.sender, reward, success);
      if (!success) {
        totalDust += reward + dust;
      } else if (dust != 0) {
        totalDust += dust;
      }
    }
  }

  function delegateCoin(
    address agent,
    address payable delegator,
    uint256 deposit
  ) internal returns (uint256) {
    Agent storage a = agentsMap[agent];
    uint256 newDeposit = a.cDelegatorMap[delegator].newDeposit + deposit;
    if (newDeposit == deposit) {
      require(deposit >= requiredCoinDeposit, "deposit is too small");
      uint256 rewardIndex = a.rewardSet.length;
      a.cDelegatorMap[delegator] = CoinDelegator(0, deposit, roundTag, rewardIndex);
    } else {
      require(deposit != 0, "deposit value is zero");
      CoinDelegator storage d = a.cDelegatorMap[delegator];
      (uint256 rewardAmount, uint256 dust) = collectCoinReward(a, d, 0x7FFFFFFF);
      distributeReward(delegator, rewardAmount, dust);
      if (d.changeRound < roundTag) {
        d.deposit = d.newDeposit;
        d.changeRound = roundTag;
      }
      d.newDeposit = newDeposit;
    }
    a.totalDeposit += deposit;
    return newDeposit;
  }

  function undelegateCoin(address agent, address payable delegator) internal returns (uint256) {
    Agent storage a = agentsMap[agent];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    uint256 newDeposit = d.newDeposit;
    require(newDeposit != 0, "delegator does not exist");

    (uint256 rewardAmount, uint256 dust) = collectCoinReward(a, d, 0x7FFFFFFF);
    distributeReward(delegator, rewardAmount, dust);

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
    return newDeposit;
  }

  function collectCoinReward(
    Agent storage a,
    CoinDelegator storage d,
    int256 roundLimit
  ) internal returns (uint256 rewardAmount, uint256 dust) {
    uint256 rewardLength = a.rewardSet.length;
    uint256 rewardIndex = d.rewardIndex;
    rewardAmount = 0;
    dust = 0;
    if (rewardIndex >= rewardLength) {
      return (rewardAmount, dust);
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
      uint256 rsPower = stateMap[r.round].power;
      curReward = (r.totalReward * deposit * rsPower) / r.score;
      rewardAmount += curReward;
      require(r.coin >= deposit, "reward is not enough");
      require(r.remainReward >= curReward, "there is not enough reward");
      if (r.coin == deposit) {
        dust += (r.remainReward - curReward);
        delete a.rewardSet[rewardIndex];
      } else {
        r.coin -= deposit;
        r.remainReward -= curReward;
      }
      rewardIndex++;
    }

    // update index whenever claim happens
    d.rewardIndex = rewardIndex;
    return (rewardAmount, dust);
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "requiredCoinDeposit")) {
      require(value.length == 32, "length of requiredCoinDeposit mismatch");
      uint256 newRequiredCoinDeposit = BytesToTypes.bytesToUint256(32, value);
      require(newRequiredCoinDeposit != 0, "the requiredCoinDeposit out of range");
      requiredCoinDeposit = newRequiredCoinDeposit;
    } else if (Memory.compareStrings(key, "powerFactor")) {
      require(value.length == 32, "length of powerFactor mismatch");
      uint256 newHashPowerFactor = BytesToTypes.bytesToUint256(32, value);
      require(newHashPowerFactor != 0, "the powerFactor out of range");
      powerFactor = newHashPowerFactor;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /// Collect all dusts and send to DAO treasury
  function gatherDust() external onlyInit onlyGov {
    if (totalDust != 0) {
      payable(FOUNDATION_ADDR).transfer(totalDust);
      totalDust = 0;
    }
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
