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
  mapping(byte32 => uint256) walletStatus;

  // key: roundtag
  // value: reward per BTC accumulated
  mapping(uint256 => uint256) public cumulativeRewardPerBTC;

  // delegated value in the current round.
  uint256 public totalAmount;

  uint256 public constant ROUND_INTERVAL = 86400;
  uint256 public constant BTC_DECIMAL = 1e8;

  uint256 public lastRewardDistributionTimestamp;
  IPledgeAgent public pledgeAgent;

  event RewardDistributed(uint256 reward, uint256 roundTag);
  event RewardClaimed(address indexed user, uint256 rewardAmount);


  //this may be merkleized for reward claiming, so we can have scalability
  struct UserStakeInfo {
    uint256 stakedAmount; // Amount of BTC staked
    uint256 rewardDebt; // Accumulated reward per BTC
  }

  mapping(address => UserStakeInfo) public userStakeInfo;

  /* These value will need to be converted to merkle tree */
  mapping(address => bool) public holders;
  address[] public holderAddresses;
  /* </end merkle tree values >*/


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
      require(cumulativeRewardPerBTC.length > lastRoundTag , "No cumulativeRewardPerBTC for lastRoundTag");
      UserStakeInfo storage user = userStakeInfo[msg.sender];
      
      // Calculate the pending reward for the user up to the latest round
      uint256 pendingReward = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL - user.rewardDebt;
      
      // If there's a pending reward, transfer it to the user
      if (pendingReward > 0) {
          Address.sendValue(payable(msg.sender), pendingReward);
          emit RewardClaimed(msg.sender, pendingReward);
      }
      
      // Update the rewardDebt to reflect the rewards claimed up to the latest round
      user.rewardDebt = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;
  }

  function distributeReward(uint256 roundTag) external payable onlyPledgeAgent {
      require(block.timestamp - lastRewardDistributionTimestamp >= ROUND_INTERVAL, "Reward distribution interval too short");
      require(msg.value > 0, "Reward amount must be greater than 0");
      require(totalBTCStaked > 0, "No BTC staked");
      
      lastRewardDistributionTimestamp = block.timestamp;
      uint256 rewardAmount = msg.value;

      // Distribute rewards to all current holders
      uint256 totalSupply = lstToken.totalSupply();
      require(totalSupply > 0, "Total supply must be greater than 0");

      for (uint256 i = 0; i < holderAddresses.length; i++) {
          address holder = holderAddresses[i];
          uint256 holderBalance = lstToken.balanceOf(holder);
          if (holderBalance > 0) {
              uint256 holderReward = (rewardAmount * holderBalance) / totalSupply;
              if (holderReward > 0) {
                  Address.sendValue(payable(holder), holderReward);
                  emit RewardClaimed(holder, holderReward);
              }
          }
      }

      cumulativeRewardPerBTC[roundTag] = cumulativeRewardPerBTC[lastRoundTag] + (rewardAmount * BTC_DECIMAL / totalBTCStaked);
      lastRoundTag = roundTag;

      emit RewardDistributed(rewardAmount, roundTag);
  }

  function parsePayload(bytes29 payload) internal pure returns (address delegator) {
    require(payload.len() >= 27, "payload length is too small");
    //get the CORE evm address that the user chose to get the lst tokens sent to, out of the bitcoin transaction
    delegator = payload.indexAddress(7);
  }


  /*
  Function for the delegator or the relayer to tell the LST contract they've deposited BTC, and then the delegator gets LST tokens
  */
  function delegate(bytes memory payload, bytes memory script, uint256 value) external onlyBtcAgent {
    address delegator = parsePayload(payload);
    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "only delegator or relayer can submit the BTC transaction");

    _mint(delegator, value);

    UserStakeInfo storage user = userStakeInfo[delegator];
    uint256 pendingReward = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL - user.rewardDebt;

    user.stakedAmount += value;
    user.rewardDebt = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;

    if (pendingReward > 0) {
        Address.sendValue(payable(delegator), pendingReward);
        emit RewardClaimed(delegator, pendingReward);
    }

    totalBTCStaked += value;

    // Track holders
    if (!holders[delegator]) {
        holders[delegator] = true;
        holderAddresses.push(delegator);
    }
  }

  /*
  Function for the validator to burn the LST token and get the BTC back
  */
  function undelegate(bytes memory btcTransaction) external onlyBtcAgent {
    // TODO mark a burn workflow finish
    bytes[] memory lockScripts;
    uint256[] memory amounts;
    // Parse btcTransaction to get lockScripts and amounts
    // Iterate over lockScripts and amounts to burn tokens and update user info
    // example:
    // _burn(delegator, amount);

    // Update holder tracking (assuming the burn updates the total supply correctly)
    for (uint256 i = 0; i < lockScripts.length; i++) {
        uint256 amount = amounts[i];
        address holder = address(uint160(uint256(lockScripts[i]))); //somehow get the eth address from the lockscript:
        UserStakeInfo storage user = userStakeInfo[holder];
        uint256 pendingReward = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL - user.rewardDebt;
        
        user.stakedAmount -= amount;
        user.rewardDebt = (user.stakedAmount * cumulativeRewardPerBTC[lastRoundTag]) / BTC_DECIMAL;

        lstToken.burn(holder, amount);

        if (pendingReward > 0) {
            Address.sendValue(payable(holder), pendingReward);
            emit RewardClaimed(holder, pendingReward);
        }

        totalBTCStaked -= amount;

        if (lstToken.balanceOf(holder) == 0) {
            holders[holder] = false;
            // Remove from holderAddresses (not efficient, consider using a more efficient structure)
            for (uint256 j = 0; j < holderAddresses.length; j++) {
                if (holderAddresses[j] == holder) {
                    holderAddresses[j] = holderAddresses[holderAddresses.length - 1];
                    holderAddresses.pop();
                    break;
                }
            }
        }
    }
  }

  /// Get stake amount
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmount() external view returns (uint256 totalAmount) {
    return lstToken.totalSupply();
  }

  /// Get stake amount
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getLastStakeAmount() external view returns (uint256 totalAmount) {
    return totalAmount;
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

  /*********************** Inner Methods *****************************/
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
