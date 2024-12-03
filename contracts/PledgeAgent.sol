// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IPledgeAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ISystemReward.sol";
import "./lib/Address.sol";
import "./lib/TypedMemView.sol";
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
  using TypedMemView for *;

  // Deprecated in V-1.0.13
  // minimal CORE require to stake
  uint256 public requiredCoinDeposit;

  // Deprecated in V-1.0.13
  // powerFactor/10000 determines the weight of BTC hash power vs CORE stakes
  // the default value of powerFactor is set to 20000 
  // which means the overall BTC hash power takes 2/3 total weight 
  // when calculating hybrid score and distributing block rewards
  uint256 public powerFactor;

  // Deprecated in V-1.0.13
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

  // Deprecated in V-1.0.13
  // btcReceiptMap keeps all BTC staking receipts on Core
  mapping(bytes32 => BtcReceipt) public btcReceiptMap;

  // Deprecated in V-1.0.13
  // round2expireInfoMap keeps the amount of expired BTC staking value for each round
  mapping(uint256 => BtcExpireInfo) round2expireInfoMap;

  // Deprecated in V-1.0.13
  uint256 public btcFactor;
  uint256 public minBtcLockRound;
  uint32 public btcConfirmBlock;
  uint256 public minBtcValue;
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
  event received(address indexed from, uint256 amount);

  function init() external onlyNotInit {
    roundTag = block.timestamp / SatoshiPlusHelper.ROUND_INTERVAL;
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

  // HARDFORK V-1.0.12
  /*********************** Move data ***************************/
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

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "clearDeprecatedMembers")) {
      requiredCoinDeposit = 0;
      powerFactor = 0;
      btcFactor = 0;
      minBtcLockRound = 0;
      btcConfirmBlock = 0;
      minBtcValue = 0;
      delegateBtcGasPrice = 0;
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

  function getExpireList(uint256 round) external view returns (address[] memory){
    return round2expireInfoMap[round].agentAddrList;
  }

  receive() external payable {
    if (msg.value != 0) {
      emit received(msg.sender, msg.value);
    }
  }
}