// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./lib/Address.sol";
import "./lib/BitcoinHelper.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";

/// This contract manages user delegate, also known as stake
/// Including both coin delegate and hash delegate

/// HARDFORK V-1.0.3
/// `effective transfer` is introduced in this hardfork to keep the rewards for users 
/// when transferring CORE tokens from one validator to another
/// `effective transfer` only contains the amount of CORE tokens transferred 
/// which are eligible for claiming rewards in the acting round

/// HARDFORK V-1.0.12
/// This contract is retired. 
/// It's role is replaced by StakeHub and 3 agent contracts to handle different types of staking assets separately
/// It is kept in the codebase for backward compatibiliy

contract PledgeAgent is IPledgeAgent, System, IParamSubscriber {
  using BitcoinHelper for *;
  using TypedMemView for *;

  uint256 public constant INIT_REQUIRED_COIN_DEPOSIT = 1e18;
  uint256 public constant INIT_HASH_POWER_FACTOR = 20000;
  uint256 public constant POWER_BLOCK_FACTOR = 1e18;
  uint32 public constant INIT_BTC_CONFIRM_BLOCK = 3;
  uint256 public constant INIT_MIN_BTC_LOCK_ROUND = 7;
  uint256 public constant ROUND_INTERVAL = 86400;
  uint256 public constant INIT_MIN_BTC_VALUE = 1e6;
  uint256 public constant INIT_BTC_FACTOR = 5e4;
  uint256 public constant BTC_STAKE_MAGIC = 0x5341542b;
  uint256 public constant CHAINID = 1116;
  uint256 public constant FEE_FACTOR = 1e18;
  uint256 public constant BTC_UNIT_CONVERSION = 1e10;
  uint256 public constant INIT_DELEGATE_BTC_GAS_PRICE = 1e12;

  // minimal CORE require to stake
  uint256 public requiredCoinDeposit;

  // powerFactor/10000 determines the weight of BTC hash power vs CORE stakes
  // the default value of powerFactor is set to 20000 
  // which means the overall BTC hash power takes 2/3 total weight 
  // when calculating hybrid score and distributing block rewards
  uint256 public powerFactor;

  // key: candidate's operateAddr
  mapping(address => Agent) public agentsMap;

  // This field is used to store collected rewards of delegators. 
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

  // HARDFORK V-1.0.7
  // btcReceiptMap keeps all BTC staking receipts on Core
  mapping(bytes32 => BtcReceipt) public btcReceiptMap;

  // round2expireInfoMap keeps the amount of expired BTC staking value for each round
  mapping(uint256 => BtcExpireInfo) round2expireInfoMap;

  // staking weight of each BTC vs. CORE
  uint256 public btcFactor;

  // minimum rounds to stake for a BTC staking transaction
  uint256 public minBtcLockRound;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // minimum value to stake for a BTC staking transaction
  uint256 public minBtcValue;

  // NOT USED
  // Depreated in V-1.0.12
  uint256 public delegateBtcGasPrice;

  // reentrant lock
  bool private reentrantLocked;

  // HARDFORK V-1.0.7
  struct BtcReceipt {
    address agent;
    address delegator;
    uint256 value;
    uint256 endRound;
    uint256 rewardIndex;
    address payable feeReceiver;
    uint256 fee;
  }

  // HARDFORK V-1.0.7
  struct BtcExpireInfo {
    address[] agentAddrList;
    mapping(address => uint256) agent2valueMap;
    mapping(address => uint256) agentExistMap;
  }

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
    uint256 btc;
    uint256 totalBtc;
    bool    moved;
  }

  struct RoundState {
    uint256 power;
    uint256 coin;
    uint256 powerFactor;
    uint256 btc;
    uint256 btcFactor;
  }

  /*********************** events **************************/
  event claimedReward(address indexed delegator, address indexed operator, uint256 amount, bool success);
  event transferredBtcFee(bytes32 indexed txid, address payable feeReceiver, uint256 fee);
  event failedTransferBtcFee(bytes32 indexed txid, address payable feeReceiver, uint256 fee);
  event btcPledgeExpired(bytes32 indexed txid, address indexed delegator);
  event received(address indexed from, uint256 amount);

  function init() external onlyNotInit {
    requiredCoinDeposit = INIT_REQUIRED_COIN_DEPOSIT;
    powerFactor = INIT_HASH_POWER_FACTOR;
    btcFactor = INIT_BTC_FACTOR;
    minBtcLockRound = INIT_MIN_BTC_LOCK_ROUND;
    btcConfirmBlock = INIT_BTC_CONFIRM_BLOCK;
    minBtcValue = INIT_MIN_BTC_VALUE;
    roundTag = block.timestamp / ROUND_INTERVAL;
    alreadyInit = true;
  }

  modifier noReentrant() {
    require(!reentrantLocked, "PledgeAgent reentrant call.");
    reentrantLocked = true;
    _;
    reentrantLocked = false;
  }

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param agent The operator address of validator
  /// HARDFORK V-1.0.12 Deprecated, the method is kept here for backward compatibility
  function delegateCoin(address agent) external payable override noReentrant{
    _moveCOREData(agent, msg.sender);
    _distributeReward(msg.sender);

    (bool success, ) = CORE_AGENT_ADDR.call {value: msg.value} (abi.encodeWithSignature("proxyDelegate(address,address)", agent, msg.sender));
    require (success, "call CORE_AGENT_ADDR.proxyDelegate() failed");
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  /// HARDFORK V-1.0.12 Deprecated, the method is kept here for backward compatibility
  function undelegateCoin(address agent) external override {
    undelegateCoin(agent, 0);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  /// @param amount The amount of CORE to undelegate
  /// HARDFORK V-1.0.12 Deprecated, the method is kept here for backward compatibility
  function undelegateCoin(address agent, uint256 amount) public override noReentrant{
    _moveCOREData(agent, msg.sender);
    _distributeReward(msg.sender);

    (bool success, bytes memory data) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("proxyUnDelegate(address,address,uint256)", agent, msg.sender, amount));
    require (success, "call CORE_AGENT_ADDR.proxyUnDelegate() failed");
    uint256 undelegateAmount =  abi.decode(data, (uint256));
    Address.sendValue(payable(msg.sender), undelegateAmount);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  // HARDFORK V-1.0.12 Deprecated, the method is kept here for backward compatibility
  function transferCoin(address sourceAgent, address targetAgent) external override {
    transferCoin(sourceAgent, targetAgent, 0);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  /// @param amount The amount of CORE to transfer
  // HARDFORK V-1.0.12 Deprecated, the method is kept here for backward compatibility
  function transferCoin(address sourceAgent, address targetAgent, uint256 amount) public override noReentrant{
    _moveCOREData(sourceAgent, msg.sender);
    _moveCOREData(targetAgent, msg.sender);
    _distributeReward(msg.sender);

    (bool success, ) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("proxyTransfer(address,address,address,uint256)", sourceAgent, targetAgent, msg.sender, amount));
    require (success, "call CORE_AGENT_ADDR.proxyTransfer() failed");
  }

  /// Claim rewards for delegator
  /// @param agentList The list of validators to claim rewards on, it can be empty
  /// @return (Amount claimed, Are all rewards claimed)
  function claimReward(address[] calldata agentList) external override noReentrant returns (uint256, bool) {
    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      _moveCOREData(agentList[i], msg.sender);
    }
    uint256 rewardSum = rewardMap[msg.sender];

    (bool success, bytes memory data) = STAKE_HUB_ADDR.call(abi.encodeWithSignature("proxyClaimReward(address)", msg.sender));
    require (success, "call STAKE_HUB_ADDR.proxyClaimReward() failed");
    uint256 proxyRewardSum =  abi.decode(data, (uint256));

    if (proxyRewardSum != 0) {
      rewardMap[msg.sender] += proxyRewardSum;
    }
    
    _distributeReward(msg.sender);

    return (rewardSum + proxyRewardSum, true);
  }

  /// calculate reward for delegator
  /// the rewards will be collected to rewardMap after execution
  /// @param agentList The list of validators to calculate rewards
  /// @param delegator the delegator to calculate rewards
  function calculateReward(address[] calldata agentList, address delegator) external override returns (uint256) {
    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      _moveCOREData(agentList[i], delegator);
    }
    return rewardMap[delegator];
  }

  // HARDFORK V-1.0.7 
  /// claim BTC staking rewards
  /// @param txidList the list of BTC staking transaction id to claim rewards 
  /// @return rewardSum amount of reward claimed
  function claimBtcReward(bytes32[] calldata txidList) external override returns (uint256 rewardSum) {
    uint256 len = txidList.length;
    for(uint256 i = 0; i < len; i++) {
      bytes32 txid = txidList[i];
      BtcReceipt storage br = btcReceiptMap[txid];
      require(br.value != 0, "btc tx not found");
      address delegator = br.delegator;
      require(delegator == msg.sender, "not the delegator of this btc receipt");

      uint256 reward = _collectBtcReward(txid);
      rewardSum += reward;
      if (br.value == 0) {
        emit btcPledgeExpired(txid, delegator);
      }
    }

    if (rewardSum != 0) {
      rewardMap[msg.sender] += rewardSum;
      _distributeReward(msg.sender);
    }
    return rewardSum;
  }

  // HARDFORK V-1.0.12
  /*********************** Move data ***************************/
  /// move BTC data to BitcoinStake by transaction id
  /// the reward will be calculated and saved in rewardMap and the record will be deleted
  /// this method is called by BitcoinStake.moveData
  /// @param txid the BTC stake transaction id
  /// @return candidate the validator candidate address
  /// @return delegator the delegator address
  /// @return amount the staked BTC amount
  /// @return round the round of stake
  /// @return lockTime the CLTV locktime value
  function moveBtcData(bytes32 txid) external onlyBtcStake returns (address candidate, address delegator, uint256 amount, uint256 round, uint256 lockTime) {
    BtcReceipt storage br = btcReceiptMap[txid];
    if (br.value == 0) {
      return (address(0), address(0), 0, 0, 0);
    }

    // set return values, which will be used by BitcoinStake to restore staking record
    candidate = br.agent;
    delegator = br.delegator;
    amount = br.value;
    lockTime = br.endRound * SatoshiPlusHelper.ROUND_INTERVAL;

    Agent storage agent = agentsMap[br.agent];
    if (br.rewardIndex == agent.rewardSet.length) {
      round = roundTag;
    } else {
      Reward storage reward = agent.rewardSet[br.rewardIndex];
      if (reward.round == 0) {
        round = roundTag;
      } else {
        round = roundTag - 1;
      }
    }

    // calculate and record rewards
    uint256 rewardAmount = _collectBtcReward(txid);
    rewardMap[delegator] += rewardAmount;

    // Clean round2expireInfoMap
    BtcExpireInfo storage expireInfo = round2expireInfoMap[br.endRound];
    uint256 length = expireInfo.agentAddrList.length;
    for (uint256 j = length; j != 0; j--) {
      if (expireInfo.agentAddrList[j-1] == candidate) {
        agentsMap[candidate].totalBtc -= amount;
        if (expireInfo.agent2valueMap[candidate] == amount) {
          delete expireInfo.agent2valueMap[candidate];
          delete expireInfo.agentExistMap[candidate];
          if (j != length) {
             expireInfo.agentAddrList[j-1] = expireInfo.agentAddrList[length - 1];
          }
          expireInfo.agentAddrList.pop();
        } else {
          expireInfo.agent2valueMap[candidate] -= amount;
        }
        break;
      }
    }
    if (expireInfo.agentAddrList.length == 0) {
      delete round2expireInfoMap[br.endRound];
    }

    // Clean btcReceiptMap
    delete btcReceiptMap[txid];
  }

  /// Move active candidates data - this method is called by StakeHub to migrate data from PledgeAgent after 1.0.12 hardfork is activated
  /// At the round of N where 1.0.12 takes effect at block S
  /// All user staking actions happen on PledgeAgent when block number < S, and on StakeHub when block number >= S
  /// After this method is called, StakeHub obtains full staking data with a smooth transition
  /// @param candidates list of validator candidate addresses
  function moveCandidateData(address[] memory candidates) external {
    uint256 l = candidates.length;

    uint256 count;
    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      if (!agent.moved && (agent.totalDeposit != 0 || agent.coin != 0 || agent.totalBtc != 0 || agent.btc != 0)) {
        count++;
      }
    }
    if (count == 0) {
      return;
    }
    uint256[] memory amounts = new uint256[](count);
    uint256[] memory realAmounts = new uint256[](count);
    address[] memory targetCandidates = new address[](count);
    uint j;

    // move CORE stake data to CoreAgent
    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      if (!agent.moved && (agent.totalDeposit != 0 || agent.coin != 0 || agent.totalBtc != 0 || agent.btc != 0)) {
        amounts[j] = agent.coin;
        realAmounts[j] = agent.totalDeposit;
        targetCandidates[j] = candidates[i];
        j++;
      }
    }
    (bool success,) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("_initializeFromPledgeAgent(address[],uint256[],uint256[])", targetCandidates, amounts, realAmounts));
    require (success, "call CORE_AGENT_ADDR._initializeFromPledgeAgent() failed");

    // move BTC stake data to BitcoinStake
    j = 0;
    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      if (!agent.moved && (agent.totalDeposit != 0 || agent.coin != 0 || agent.totalBtc != 0 || agent.btc != 0)) {
        amounts[j] = agent.btc;
        realAmounts[j] = agent.totalBtc;
        agent.moved = true;
        j++;
      }
    }
    (success,) = BTC_STAKE_ADDR.call(abi.encodeWithSignature("_initializeFromPledgeAgent(address[],uint256[],uint256[])", targetCandidates, amounts, realAmounts));
    require (success, "call BTC_STAKE_ADDR._initializeFromPledgeAgent() failed");

    (success,) = BTC_AGENT_ADDR.call(abi.encodeWithSignature("_initializeFromPledgeAgent(address[],uint256[])", targetCandidates, amounts));
    require (success, "call BTC_AGENT_ADDR._initializeFromPledgeAgent() failed");
  }

  /// move delegator data to new contracts
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  function moveCOREData(address candidate, address delegator) external {
    _moveCOREData(candidate, delegator);
  }

  /*********************** Internal methods ***************************/
  /// send rewards to delegator and clear the record in rewardMap
  /// @param delegator the delegator address
  function _distributeReward(address delegator) internal {
    uint256 reward = rewardMap[delegator];
    if (reward != 0) {
      rewardMap[delegator] = 0;
      Address.sendValue(payable(delegator), reward);
      emit claimedReward(delegator, msg.sender, reward, true);
    }
  }

  /// move historical CORE stake information from PledgeAgent to CoreAgent
  /// the record will be removed in PledgeAgent after move
  /// @param candidate the validator candidate address
  /// @param delegator the delegator address
  function _moveCOREData(address candidate, address delegator) internal returns(bool) {
    Agent storage a = agentsMap[candidate];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    if (d.changeRound != 0) {
      uint256 reward = _collectCoinReward(a, d);
      if (reward != 0) {
        rewardMap[delegator] += reward;
      }

      uint256 deposit = d.deposit;
      if (d.changeRound < roundTag) {
        deposit = d.newDeposit;
      }
      (bool success, ) = CORE_AGENT_ADDR.call {value: d.newDeposit} (abi.encodeWithSignature("moveData(address,address,uint256,uint256,uint256)", candidate, delegator, deposit, d.transferOutDeposit, roundTag));
      require (success, "call CORE_AGENT_ADDR.moveData() failed");

      a.totalDeposit -= d.newDeposit;
      delete a.cDelegatorMap[delegator];
      delete debtDepositMap[roundTag][delegator];
      return true;
    }
    return false;
  }

  /// collect rewards on a given reward map
  /// @param r the reward map to collect
  /// @param deposit the amount of stake
  /// @return rewardAmount the amount of reward to claim
  function _collectFromRoundReward(Reward storage r, uint256 deposit) internal returns (uint256 rewardAmount) {
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

  /// collect rewards on a candidate/delegator paris
  /// @param a the validator candidate
  /// @param d the delegator
  /// @return rewardAmount the amount of reward to claim
  function _collectCoinReward(Agent storage a, CoinDelegator storage d) internal returns (uint256 rewardAmount) {
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
          uint256 undelegateReward = _collectFromRoundReward(r, d.transferOutDeposit - transferOutDeposit);
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
        rewardAmount += _collectFromRoundReward(r, deposit);
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

  /// calculate reward for a BTC stake transaction
  /// @param txid the BTC transaction id
  function _collectBtcReward(bytes32 txid) internal returns (uint256) {
    uint256 curRound = roundTag;
    BtcReceipt storage br = btcReceiptMap[txid];
    uint256 reward = 0;
    Agent storage a = agentsMap[br.agent];
    uint256 rewardIndex = br.rewardIndex;
    uint256 rewardLength = a.rewardSet.length;
    while (rewardIndex < rewardLength) {
      Reward storage r = a.rewardSet[rewardIndex];
      uint256 rRound = r.round;
      if (rRound == curRound || br.endRound <= rRound) {
        break;
      }
      uint256 deposit = br.value * stateMap[rRound].btcFactor;
      reward += _collectFromRoundReward(r, deposit);
      if (r.coin == 0) {
        delete a.rewardSet[rewardIndex];
      }
      rewardIndex += 1;
    }
    
    uint256 fee = br.fee;
    uint256 feeReward;
    if (fee != 0) {
      if (fee <= reward) {
        feeReward = fee;
      } else {
        feeReward = reward;
      }

      if (feeReward != 0) {
        br.fee -= feeReward;
        bool success = br.feeReceiver.send(feeReward);
        if (success) {
          reward -= feeReward;
          emit transferredBtcFee(txid, br.feeReceiver, feeReward);
        } else {
          emit failedTransferBtcFee(txid, br.feeReceiver, feeReward);
        }
      }
    }

    if (br.endRound <= (rewardIndex == rewardLength ? curRound : a.rewardSet[rewardIndex].round)) {
      delete btcReceiptMap[txid];
    } else {
      br.rewardIndex = rewardIndex;
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
    } else if (Memory.compareStrings(key, "powerFactor")) {
      uint256 newHashPowerFactor = BytesToTypes.bytesToUint256(32, value);
      if (newHashPowerFactor == 0) {
        revert OutOfBounds(key, newHashPowerFactor, 1, type(uint256).max);
      }
      powerFactor = newHashPowerFactor;
    } else if (Memory.compareStrings(key, "btcFactor")) {
      uint256 newBtcFactor = BytesToTypes.bytesToUint256(32, value);
      if (newBtcFactor == 0) {
        revert OutOfBounds(key, newBtcFactor, 1, type(uint256).max);
      }
      btcFactor = newBtcFactor;
    } else if (Memory.compareStrings(key, "minBtcLockRound")) {
      uint256 newMinBtcLockRound = BytesToTypes.bytesToUint256(32, value);
      if (newMinBtcLockRound == 0) {
        revert OutOfBounds(key, newMinBtcLockRound, 1, type(uint256).max);
      }
      minBtcLockRound = newMinBtcLockRound;
    } else if (Memory.compareStrings(key, "btcConfirmBlock")) {
      uint256 newBtcConfirmBlock = BytesToTypes.bytesToUint256(32, value);
      if (newBtcConfirmBlock == 0) {
        revert OutOfBounds(key, newBtcConfirmBlock, 1, type(uint256).max);
      }
      btcConfirmBlock = uint32(newBtcConfirmBlock);
    } else if (Memory.compareStrings(key, "minBtcValue")) {
      uint256 newMinBtcValue = BytesToTypes.bytesToUint256(32, value);
      if (newMinBtcValue == 0) {
        revert OutOfBounds(key, newMinBtcValue, 1e4, type(uint256).max);
      }
      minBtcValue = newMinBtcValue;
    } else if (Memory.compareStrings(key,"delegateBtcGasPrice")) {
      uint256 newDelegateBtcGasPrice = BytesToTypes.bytesToUint256(32, value);
      if (newDelegateBtcGasPrice < 1e9) {
        revert OutOfBounds(key, newDelegateBtcGasPrice, 1e9, type(uint256).max);
      }
      delegateBtcGasPrice = newDelegateBtcGasPrice;
    } else {
      revert UnsupportedGovParam(key);
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

  /// Get expire information of a validator by round and agent
  /// @param round The end round of the btc lock
  /// @param agent The operator address of validator
  /// @return expireValue The expire value of the agent in the round
  function getExpireValue(uint256 round, address agent) external view returns (uint256){
    BtcExpireInfo storage expireInfo = round2expireInfoMap[round];
    return expireInfo.agent2valueMap[agent];
  }

  /// Get stake information - this method is called by StakeHub to migrate data from PledgeAgent after 1.0.12 hardfork is activated
  /// At the round of N where 1.0.12 takes effect at block S
  /// All user staking actions happen on PledgeAgent when block number < S, and on StakeHub when block number >= S
  /// After this method is called, StakeHub obtains full staking data with a smooth transition
  /// Note only data of active validators in round N are migrated at block S
  /// @param candidates list of validator candidate addresses
  /// @return cores list of CORE staked value of the given candidates
  /// @return hashs list of BTC hash powered staked (measured in blocks) of the given candidates
  /// @return btcs list of BTC staked value of the given candidates
  function getStakeInfo(address[] memory candidates) external view returns (uint256[] memory cores, uint256[] memory hashs, uint256[] memory btcs) {
    uint256 l = candidates.length;
    cores = new uint256[](l);
    hashs = new uint256[](l);
    btcs = new uint256[](l);

    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      cores[i] = agent.coin;
      hashs[i] = agent.power / POWER_BLOCK_FACTOR;
      btcs[i] = agent.btc;
    }
  }

  receive() external payable {
    if (msg.value != 0) {
      emit received(msg.sender, msg.value);
    }
  }
}