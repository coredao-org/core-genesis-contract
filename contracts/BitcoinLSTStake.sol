// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinLSTStake.sol";
import "./interface/IPledgeAgent.sol";
import "./lib/Address.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./System.sol";

contract BitcoinLSTStake is IBitcoinLSTStake, System, IParamSubscriber {

  uint256 public constant ST_ACTIVE = 1;
  uint256 public constant ST_INACTIVE = 2;

  IERC20 public lstToken;
  bytes32[] public wallets;
  mapping(bytes32 => uint256) walletStatus;

  // key: roundtag
  // value: accrued reward per BTC
  mapping(uint256 => uint256) public accruedRewardPerBTC;

  uint256 public constant ROUND_INTERVAL = 86400;
  uint256 public constant BTC_DECIMAL = 1e8;

  uint256 public lastRewardDistributionTimestamp;
  IPledgeAgent public pledgeAgent;

  event RewardDistributed(uint256 reward, uint256 roundTag);
  event RewardClaimed(address indexed user, uint256 rewardAmount);

  // User stake information
  struct UserStakeInfo {
    uint256 stakedAmount; // Amount of BTC staked
    uint256 rewardDebt; // Accumulated reward per BTC
    uint256 lastClaimRound; // Last claimed round
  }

  mapping(address => UserStakeInfo) public userStakeInfo;

  uint256 public totalBTCStaked;
  uint256 public lastRoundTag;

  constructor(address _pledgeAgent, IERC20 _lstToken) {
    pledgeAgent = IPledgeAgent(_pledgeAgent);
    lastRewardDistributionTimestamp = block.timestamp;
    lstToken = _lstToken;
  }

  modifier onlyPledgeAgent() {
    require(msg.sender == address(pledgeAgent), "only pledge agent can call this function");
    _;
  }

  function claimReward() external {
    UserStakeInfo storage user = userStakeInfo[msg.sender];
    require(user.lastClaimRound < lastRoundTag, "No rewards to claim");

    // Calculate the pending reward for the user up to the latest round
    uint256 pendingReward = (user.stakedAmount * (accruedRewardPerBTC[lastRoundTag] - accruedRewardPerBTC[user.lastClaimRound])) / BTC_DECIMAL;

    // If there's a pending reward, transfer it to the user
    if (pendingReward > 0) {
        Address.sendValue(payable(msg.sender), pendingReward);
        emit RewardClaimed(msg.sender, pendingReward);
    }

    // Update the user's last claim round and reward debt
    user.lastClaimRound = lastRoundTag;
    user.rewardDebt = (user.stakedAmount * accruedRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;
  }

  function distributeReward(uint256 roundTag) external payable onlyPledgeAgent {
    require(block.timestamp - lastRewardDistributionTimestamp >= ROUND_INTERVAL, "Reward distribution interval too short");
    require(msg.value > 0, "Reward amount must be greater than 0");
    require(totalBTCStaked > 0, "No BTC staked");

    lastRewardDistributionTimestamp = block.timestamp;
    uint256 rewardAmount = msg.value;

    accruedRewardPerBTC[roundTag] = accruedRewardPerBTC[lastRoundTag] + (rewardAmount * BTC_DECIMAL / totalBTCStaked);
    lastRoundTag = roundTag;

    emit RewardDistributed(rewardAmount, roundTag);
  }

  function _updateUserRewards(address userAddress) internal {
    UserStakeInfo storage user = userStakeInfo[userAddress];
    if (user.lastClaimRound < lastRoundTag) {
      uint256 pendingReward = (user.stakedAmount * (accruedRewardPerBTC[lastRoundTag] - accruedRewardPerBTC[user.lastClaimRound])) / BTC_DECIMAL;

      if (pendingReward > 0) {
        Address.sendValue(payable(userAddress), pendingReward);
        emit RewardClaimed(userAddress, pendingReward);
      }

      user.lastClaimRound = lastRoundTag;
      user.rewardDebt = (user.stakedAmount * accruedRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;
    }
  }

  function delegate(bytes memory payload, bytes memory script, uint256 value) external onlyBtcAgent {
    address delegator = parsePayload(payload);
    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "only delegator or relayer can submit the BTC transaction");

    _updateUserRewards(delegator);

    UserStakeInfo storage user = userStakeInfo[delegator];
    user.stakedAmount += value;
    //setting their debt to the current accrued rewards per user, so that when they join they have no rewards to claim for that
    user.rewardDebt = (user.stakedAmount * accruedRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;

    totalBTCStaked += value;
  }

  function undelegate(bytes memory btcTransaction) external onlyBtcAgent {
    bytes[] memory lockScripts;
    uint256[] memory amounts;
    // Parse btcTransaction to get lockScripts and amounts
    for (uint256 i = 0; i < lockScripts.length; i++) {
      uint256 amount = amounts[i];
      address holder = address(uint160(uint256(lockScripts[i])));
      
      _updateUserRewards(holder);

      UserStakeInfo storage user = userStakeInfo[holder];
      user.stakedAmount -= amount;
      user.rewardDebt = (user.stakedAmount * accruedRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;

      lstToken.burn(holder, amount);
      totalBTCStaked -= amount;
    }
  }

  function parsePayload(bytes29 payload) internal pure returns (address delegator) {
    require(payload.len() >= 27, "payload length is too small");
    delegator = payload.indexAddress(7);
  }

  function getStakeAmount() external view returns (uint256 totalAmount) {
    return lstToken.totalSupply();
  }

/*********************** Governance ********************************/
/// Update parameters through governance vote
/// @param key The name of the parameter
/// @param value the new value set to the parameter

  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "add")) {
      addMultisigAddress(value);
    } else if (Memory.compareStrings(key, "remove")) {
      removeWallet(value);
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  function addWallet(bytes memory addr) internal {
    // decode address -> bytes32addr, networkId
    // verify bitcoin networkId
    // wallets.push(bytes32addr)
    // walletStatus[addr] = ST_ACTIVE
  }

  function removeWallet(bytes memory addr) internal {
    // decode address -> bytes32addr, networkId
    // verify bitcoin networkId
    // walletStatus[addr] = ST_INACTIVE
  }
}
