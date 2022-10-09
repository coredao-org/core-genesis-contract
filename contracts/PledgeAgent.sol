pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;
import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./System.sol";
import "./lib/SafeMath.sol";

contract PledgeAgent is IPledgeAgent, System, IParamSubscriber {
  using SafeMath for uint256;

  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;
  uint256 public constant INIT_HASH_POWER_FACTOR = 20000;
  uint256 public constant DUST_LIMIT = 1e13;
  uint256 public constant INVALID_POWER = 1;
  uint256 public constant POWER_BLOCK_FACTOR = 1e18;

  uint256 public requiredCoinDeposit;

  // powerFactor/10000 determines the weight of BTC hash power vs CORE stakes
  // the default value of powerFactor is set to 20000 
  // which means the overall BTC hash power takes 2/3 total weight 
  // when calculating hybrid score and distributing block rewards
  uint256 public powerFactor;

  /* key: candidate's operateAddr */
  mapping(address => Agent) public agentsMap;

  /* key: delegator’s fee address, or eth format address of btc miner
   * value: btc delegator
   */
  mapping(address => BtcDelegator) public btcDelegatorsMap;
  /* key: btc compressed/uncompressed pk hash,
   * value: eth format address of btc miner
   */
  mapping(bytes20 => address) public btc2ethMap;
  /* key: round index
   * value: key state information of round
   */
  mapping(uint256 => RoundState) public stateMap;

  // roundTag is set to be timestamp / round interval,
  // the valid value should be greater than 10,000 since the chain started.
  // It is initialized to 1.
  uint256 public roundTag;

  // there will be unclaimed rewards when delegators exit
  // the rewards for the exit day will be delivered by system but can not be claimed - we call them as dust
  uint256 public totalDust;

  struct BtcDelegator {
    bytes20 pkHash;
    bytes20 compressedPkHash;
    address agent;
    uint256 power;
  }

  struct CoinDelegator {
    uint256 deposit;
    uint256 newDeposit;
    uint256 changeRound;
    uint256 rewardIndex;
  }

  struct Reward {
    uint256 totalReward;
    uint256 remainReward;
    uint256 totalIntegral;
    uint256 coin;
    uint256 round;
  }

  /*
   * The Agent struct for Candidate.
   */
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

  event paramChange(string key, bytes value);
  event delegatedCoin(address indexed agent, address indexed delegator, uint256 amount, uint256 totalAmount);
  event delegatedPower(
    address indexed agent,
    address indexed delegator,
    bytes publickey,
    bytes20 pkHash,
    bytes20 compressPkHash
  );
  event undelegatedCoin(address indexed agent, address indexed delegator, uint256 amount);
  event undelegatedPower(address indexed agent, address indexed delegator);
  event transferredCoin(
    address indexed sourceAgent,
    address indexed targetAgent,
    address indexed delegator,
    uint256 amount,
    uint256 totalAmount
  );
  event transferredPower(
    address indexed sourceAgent,
    address indexed targetAgent,
    address indexed delegator
  );
  event roundReward(address indexed agent, uint256 coinReward, uint256 powerReward);
  event claimedReward(address indexed delegator, address indexed operator, uint256 amount, bool success);

  function init() external onlyNotInit {
    requiredCoinDeposit = INIT_REQUIRED_COIN_DEPOSIT;
    powerFactor = INIT_HASH_POWER_FACTOR;
    roundTag = 1;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/
  /**
   * receive round rewards from ValidatorSet, which is triggered at the beginning of turn round
   */
  function addRoundReward(address[] memory agentList, uint256[] memory rewardList)
    external
    payable
    override
    onlyValidator
  {
    require(agentList.length == rewardList.length, "the length of agentList and rewardList should be equal");
    RoundState memory rs = stateMap[roundTag];
    for (uint256 i = 0; i < agentList.length; ++i) {
      Agent storage a = agentsMap[agentList[i]];
      if (a.rewardSet.length == 0) {
        continue;
      }
      Reward storage r = a.rewardSet[a.rewardSet.length - 1];
      uint256 rIntegral = r.totalIntegral;
      if (rIntegral == 0) {
        delete a.rewardSet[a.rewardSet.length - 1];
        continue;
      }
      if (rewardList[i] == 0) {
        continue;
      }
      r.totalReward = rewardList[i];
      r.remainReward = rewardList[i];
      uint256 coinReward = rewardList[i] * a.coin * rs.power / rIntegral;
      uint256 powerReward = rewardList[i] * a.power * rs.coin / 10000 * rs.powerFactor / rIntegral;
      emit roundReward(agentList[i], coinReward, powerReward);
    }
  }

  /**
   * calculate hybrid score for all candidates
   */
  // TODO bad naming, should use `hybrid score` instead of integral
  function getIntegral(
    address[] memory candidates, bytes20[] memory lastMiners,
    bytes20[] memory miners, uint256[] memory powers
  ) external override onlyCandidate
      returns (uint256[] memory integrals, uint256 totalPower, uint256 totalCoin) {
    require(miners.length == powers.length, "the length of miners and powers should be equal");
    // collect hash power rewards, reset delegator's power & agent's power+coin
    uint256 reward = 0;
    for (uint256 i = 0; i < lastMiners.length; i++) {
      address delegator = btc2ethMap[lastMiners[i]];
      if (delegator != address(0x0)) {
        BtcDelegator storage m = btcDelegatorsMap[delegator];
        Agent storage a = agentsMap[m.agent];
        reward = collectPowerReward(a, m);
        distributeReward(payable(delegator), reward, 0);
        m.power = 0;
      }
    }

    uint256 candidateSize = candidates.length;
    for (uint256 i = 0; i < candidateSize; ++i) {
      agentsMap[candidates[i]].power = 0;
    }

    // add power
    for (uint256 i = 0; i < miners.length; i++) {
      address delegator = btc2ethMap[miners[i]];
      if (delegator != address(0x0)) {
        // in order to improve accuracy, the calculation of power is based on 10^18
        powers[i] *= POWER_BLOCK_FACTOR;
        BtcDelegator storage m = btcDelegatorsMap[delegator];
        Agent storage a = agentsMap[m.agent];
        if (a.power % POWER_BLOCK_FACTOR != INVALID_POWER) {
          m.power += powers[i];
          a.power += powers[i];
        }
      }
    }

    totalPower = 1;
    totalCoin = 1;
    for (uint256 i = 0; i < candidateSize; ++i) {
      Agent storage a = agentsMap[candidates[i]];
      a.coin = a.totalDeposit;
      totalPower += a.power;
      totalCoin += a.coin;
    }

    // calc hybrid score
    integrals = new uint256[](candidateSize);
    for (uint256 i = 0; i < candidateSize; ++i) {
      Agent storage a = agentsMap[candidates[i]];
      integrals[i] = a.power * totalCoin * powerFactor / 10000 + a.coin * totalPower;
    }
    return (integrals, totalPower, totalCoin);
  }

  // new round starts
  function setNewRound(address[] memory validators, uint256 totalPower,
      uint256 totalCoin, uint256 round) external override onlyCandidate {
    RoundState memory rs;
    rs.power = totalPower;
    rs.coin = totalCoin;
    rs.powerFactor = powerFactor;
    stateMap[round] = rs;

    roundTag = round;
    for (uint256 i = 0; i < validators.length; ++i) {
      Agent storage a = agentsMap[validators[i]];
      uint256 integral = a.power * rs.coin * powerFactor / 10000 + a.coin * rs.power;
      a.rewardSet.push(Reward(0, 0, integral, a.coin, round));
    }
  }

  function inactiveAgent(address agent) external override onlyCandidate {
    Agent storage a = agentsMap[agent];
    a.power = a.power / POWER_BLOCK_FACTOR * POWER_BLOCK_FACTOR + INVALID_POWER;
  }

  /*********************** External methods ***************************/
  function delegateCoin(address agent) external payable {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent), "agent is inactivated");
    uint256 newDeposit = delegateCoin(agent, msg.sender, msg.value);
    emit delegatedCoin(agent, msg.sender, msg.value, newDeposit);
  }

  function delegateHashPower(address agent, bytes calldata publicKey, bytes32 btcHash) external {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent), "agent is inactivated");
    require(btcDelegatorsMap[msg.sender].agent == address(0x00), "delegator has delegated");

    address addr = address(uint160(uint256(keccak256(abi.encodePacked(publicKey[1:])))));
    require(addr == msg.sender, "the delegator is a fake miner");

    bytes20 miner = ILightClient(LIGHT_CLIENT_ADDR).getMiner(btcHash);
    (bytes20 pkHash, bytes20 compressedPkHash) = getBtcPkHash(publicKey);
    require(miner == pkHash || miner == compressedPkHash, "the miner has no power");

    btcDelegatorsMap[addr] = BtcDelegator(
      pkHash,
      compressedPkHash,
      agent,
      0
    );
    btc2ethMap[pkHash] = msg.sender;
    btc2ethMap[compressedPkHash] = msg.sender;

    emit delegatedPower(agent, addr, publicKey, pkHash, compressedPkHash);
  }

  function undelegateCoin(address agent) external {
    uint256 deposit = undelegateCoin(agent, msg.sender);
    msg.sender.transfer(deposit);
    emit undelegatedCoin(agent, msg.sender, deposit);
  }

  function undelegatePower() external {
    BtcDelegator storage m = btcDelegatorsMap[msg.sender];
    require(m.agent != address(0x00), "delegator does not exist");
    emit undelegatedPower(m.agent, msg.sender);

    delete btc2ethMap[m.pkHash];
    delete btc2ethMap[m.compressedPkHash];
    delete btcDelegatorsMap[msg.sender];
  }

  function transferCoin(address sourceAgent, address targetAgent) external {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent), "agent is inactivated");
    require(sourceAgent!=targetAgent, "source agent and target agent are the same one");
    uint256 deposit = undelegateCoin(sourceAgent, msg.sender);
    uint256 newDeposit = delegateCoin(targetAgent, msg.sender, deposit);
    emit transferredCoin(sourceAgent, targetAgent, msg.sender, deposit, newDeposit);
  }

  function transferPower(address targetAgent) external {
    require(ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent), "agent is inactivated");
    BtcDelegator storage m = btcDelegatorsMap[msg.sender];
    require(m.agent != address(0x00), "delegator does not exist");
    address sourceAgent = m.agent;
    require(sourceAgent!=targetAgent, "source agent and target agent are the same one");
    m.agent = targetAgent;
    m.power = 0;
    emit transferredPower(sourceAgent, targetAgent, msg.sender);
  }

  function claimReward(address payable delegator, address[] calldata agentList) external returns (uint256, bool) {
    // limit round count to control gas usage
    int256 roundLimit = 500;
    uint256 reward;
    uint256 dust;
    uint256 rewardSum = 0;
    uint256 dustSum = 0;

    for (uint256 i = 0; i < agentList.length; ++i) {
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
    require(rewardSum > 0, "no pledge reward");
    distributeReward(delegator, rewardSum, dustSum);
    return (rewardSum, roundLimit >= 0);
  }

  /*********************** Internal methods ***************************/
  function distributeReward(address payable delegator, uint256 reward, uint256 dust) internal {
    if (reward > 0) {
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
      } else if (dust > 0) {
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
    require(newDeposit > 0, "delegator does not exist");

    (uint256 rewardAmount, uint256 dust) = collectCoinReward(a, d, 0x7FFFFFFF);
    distributeReward(delegator, rewardAmount, dust);

    a.totalDeposit -= newDeposit;
    if (a.rewardSet.length > 0) {
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
      curReward = (r.totalReward * deposit * rsPower) / r.totalIntegral;
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

  function collectPowerReward(Agent storage a, BtcDelegator storage m) internal
      returns (uint256 reward) {
    uint256 l = a.rewardSet.length;
    if (m.power == 0 || l == 0) return 0;
    Reward storage r = a.rewardSet[l - 1];
    if (r.totalReward == 0 || r.round != roundTag) return 0;

    uint256 rsCoin = stateMap[r.round].coin;
    uint256 rsFactor = stateMap[r.round].powerFactor;

    reward = r.totalReward * m.power * rsCoin / 10000 * rsFactor / r.totalIntegral;
    require(r.remainReward >= reward, "there is not enough reward");
    r.remainReward -= reward;
    return reward;
  }

  function getBtcPkHash(bytes memory publicKey) private pure returns (bytes20 pkHash, bytes20 compressedPkHash) {
    bytes memory compressedPK = new bytes(33);
    assembly {
        mstore(add(compressedPK, 0x21), mload(add(publicKey, 0x21)))
    }
    compressedPK[0] = bytes1(2 | (uint8(publicKey[64]) & 1));

    pkHash = ripemd160(abi.encodePacked(sha256(publicKey)));
    compressedPkHash = ripemd160(abi.encodePacked(sha256(compressedPK)));
  }

  /*********************** Governance ********************************/
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "requiredCoinDeposit")) {
      require(value.length == 32, "length of requiredCoinDeposit mismatch");
      uint256 newRequiredCoinDeposit = BytesToTypes.bytesToUint256(32, value);
      require(newRequiredCoinDeposit > 0, "the requiredCoinDeposit out of range");
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

  function gatherDust() external onlyInit onlyGov {
    if (totalDust > 0) {
      payable(GOV_HUB_ADDR).transfer(totalDust);
      totalDust = 0;
    }
  }

  /*********************** Public view ********************************/
  function getDelegator(address agent, address delegator) external view returns (CoinDelegator memory) {
    return agentsMap[agent].cDelegatorMap[delegator];
  }

  function getReward(address agent, uint256 index) external view returns (Reward memory) {
    Agent storage a = agentsMap[agent];
    require(index < a.rewardSet.length, "out of up bound");
    return a.rewardSet[index];
  }
}
