// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./interface/ILightClient.sol";
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

  uint256 public delegateBtcGasPrice;

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
  event paramChange(string key, bytes value);
  event claimedReward(address indexed delegator, address indexed operator, uint256 amount, bool success);
  event transferredBtcFee(bytes32 indexed txid, address payable feeReceiver, uint256 fee);
  event failedTransferBtcFee(bytes32 indexed txid, address payable feeReceiver, uint256 fee);
  event btcPledgeExpired(bytes32 indexed txid, address indexed delegator);

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

  /*********************** External methods ***************************/
  /// Delegate coin to a validator
  /// @param agent The operator address of validator
  /// HARDFORK V-1.0.10 Deprecated
  function delegateCoin(address agent) external payable override {
    move2CoreAgent(agent, msg.sender);
    distributeReward(msg.sender);

    (bool success, ) = CORE_AGENT_ADDR.call {value:msg.value} (abi.encodeWithSignature("proxyDelegate(address,address)", agent, msg.sender));
    require (success, "call CORE_AGENT_ADDR.proxyDelegate fail");
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  /// HARDFORK V-1.0.10 Deprecated
  function undelegateCoin(address agent) external override {
    undelegateCoin(agent, 0);
  }

  /// Undelegate coin from a validator
  /// @param agent The operator address of validator
  /// @param amount The amount of CORE to undelegate
  /// HARDFORK V-1.0.10 Deprecated
  function undelegateCoin(address agent, uint256 amount) public override {
    move2CoreAgent(agent, msg.sender);
    distributeReward(msg.sender);

    (bool success, ) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("proxyUnDelegate(address,address,uint256)", agent, msg.sender, amount));
    require (success, "call CORE_AGENT_ADDR.proxyUnDelegate fail");
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  // HARDFORK V-1.0.10 Deprecated
  function transferCoin(address sourceAgent, address targetAgent) external override {
    transferCoin(sourceAgent, targetAgent, 0);
  }

  /// Transfer coin stake to a new validator
  /// @param sourceAgent The validator to transfer coin stake from
  /// @param targetAgent The validator to transfer coin stake to
  /// @param amount The amount of CORE to transfer
  // HARDFORK V-1.0.10 Deprecated
  function transferCoin(address sourceAgent, address targetAgent, uint256 amount) public override {
    move2CoreAgent(sourceAgent, msg.sender);
    move2CoreAgent(targetAgent, msg.sender);
    distributeReward(msg.sender);

    (bool success, ) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("proxyTransfer(address,address,address,uint256)", sourceAgent, targetAgent, msg.sender, amount));
    require (success, "call CORE_AGENT_ADDR.proxyTransfer fail");
  }

  /// Claim reward for delegator
  /// @param agentList The list of validators to claim rewards on, it can be empty
  /// @return (Amount claimed, Are all rewards claimed)
  function claimReward(address[] calldata agentList) external override returns (uint256, bool) {
    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      move2CoreAgent(agentList[i], msg.sender);
    }
    uint256 rewardSum = rewardMap[msg.sender];
    distributeReward(msg.sender);
    return (rewardSum, true);
  }

  function calculateReward(address[] calldata agentList, address delegator) external override returns (uint256) {
    uint256 agentSize = agentList.length;
    for (uint256 i = 0; i < agentSize; ++i) {
      move2CoreAgent(agentList[i], delegator);
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

      uint256 reward = collectBtcReward(txid);
      rewardSum += reward;
      if (br.value == 0) {
        emit btcPledgeExpired(txid, delegator);
      }
    }

    if (rewardSum != 0) {
      rewardMap[msg.sender] += rewardSum;
      distributeReward(msg.sender);
    }
    return rewardSum;
  }

  // HARDFORK V-1.0.10
  /*********************** Move data ***************************/
  function cleanDelegateInfo(bytes32 txid) external onlyBtcStake returns (address candidate, address delegator, uint256 amount, uint256 round, uint256 lockTime) {
    BtcReceipt storage br = btcReceiptMap[txid];
    if (br.value == 0) {
      return (address(0), address(0), 0, 0, 0);
    }

    // Set return values
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
    // distribute reward
    uint256 rewardAmount = collectBtcReward(txid);
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

  function moveAgent(address[] memory candidates) external {
    uint256 l = candidates.length;
    uint256[] memory amounts = new uint256[](l);
    uint256[] memory realAmounts = new uint256[](l);

    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      require(!agent.moved && agent.totalDeposit != 0, "agent has been moved");
      amounts[i] = agent.coin;
      realAmounts[i] = agent.totalDeposit;
      agent.coin = 0;
      agent.moved = true;
    }
    (bool success,) = CORE_AGENT_ADDR.call(abi.encodeWithSignature("initHardforkRound(address[],uint256[],uint256[])", candidates, amounts, realAmounts));
    require (success, "call CORE_AGENT_ADDR.initHardforkRound fail");

    for (uint256 i = 0; i < l; ++i) {
      Agent storage agent = agentsMap[candidates[i]];
      amounts[i] = agent.btc;
      realAmounts[i] = agent.totalBtc;
      agent.btc = 0;
    }
    (success,) = BTC_STAKE_ADDR.call(abi.encodeWithSignature("initHardforkRound(address[],uint256[],uint256[])", candidates, amounts, realAmounts));
    require (success, "call BTC_STAKE_ADDR.initHardforkRound fail");
  }

  function moveDelegator(address agent, address delegator) external {
    move2CoreAgent(agent, delegator);
  }

  /*********************** Internal methods ***************************/
  function distributeReward(address delegator) internal {
    uint256 reward = rewardMap[delegator];
    if (reward != 0) {
      rewardMap[delegator] = 0;
      Address.sendValue(payable(delegator), reward);
      emit claimedReward(delegator, msg.sender, reward, true);
    }
  }

  function move2CoreAgent(address agent, address delegator) internal {
    Agent storage a = agentsMap[agent];
    CoinDelegator storage d = a.cDelegatorMap[delegator];
    if (d.changeRound != 0) {
      uint256 reward = collectCoinReward(a, d);
      if (reward != 0) {
        rewardMap[delegator] += reward;
      }

      (bool success, ) = CORE_AGENT_ADDR.call {value: d.newDeposit} (abi.encodeWithSignature("moveData(address,address,uint256,uint256,uint256)", agent, delegator, d.deposit, d.transferOutDeposit, roundTag));
      require (success, "call CORE_AGENT_ADDR.moveData fail");

      a.totalDeposit -= d.newDeposit;
      delete a.cDelegatorMap[delegator];
      delete debtDepositMap[roundTag][delegator];
    }
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

  function collectCoinReward(Agent storage a, CoinDelegator storage d) internal returns (uint256 rewardAmount) {
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

  function collectBtcReward(bytes32 txid) internal returns (uint256) {
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
      reward += collectCoinReward(r, deposit);
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

  /// Get expire information of a validator by round and agent
  /// @param round The end round of the btc lock
  /// @param agent The operator address of validator
  /// @return expireValue The expire value of the agent in the round
  function getExpireValue(uint256 round, address agent) external view returns (uint256){
    BtcExpireInfo storage expireInfo = round2expireInfoMap[round];
    return expireInfo.agent2valueMap[agent];
  }

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
}