// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/IParamSubscriber.sol";
import "./lib/Memory.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";
import "./lib/BytesLib.sol";
import "./lib/RLPDecode.sol";
import "./lib/SafeCast.sol";

/// This contract handles BTC staking. 
/// It interacts with BitcoinStake.sol and BitcoinLSTStake.sol for
/// non-custodial BTC staking and LST BTC staking correspondingly. 
contract BitcoinAgent is IAgent, System, IParamSubscriber {
  using BytesLib for *;
  using SafeCast for *;
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.Iterator;
  using RLPDecode for RLPDecode.RLPItem;
  using SafeCast for uint256;

  uint256 public constant DEFAULT_CORE_BTC_CONVERSION = 1e10;

  // key: candidate
  // value: staked BTC amount
  mapping (address => StakeAmount) public candidateMap;

  // CORE grading applied to BTC stakers
  DualStakingGrade[] public grades;

  // whether the CORE grading is enabled
  bool public gradeActive;

  // conversion rate between CORE and the asset
  uint256 public assetWeight;

  // the same grade percentage applies to all LST stakes
  uint256 public lstGradePercentage;

  struct StakeAmount {
    // staked BTC amount from LST
    uint256 lstStakeAmount;
    // staked BTC amount from non custodial
    uint256 stakeAmount;
  }

  struct DualStakingGrade {
    uint32 stakeRate;
    uint32 percentage;
  }

  event claimedBtcReward(address indexed delegator, uint256 amount, uint256 unclaimedAmount, int256 floatReward, uint256 accStakedAmount, uint256 dualStakingRate);
  event claimedBtcLstReward(address indexed delegator, uint256 amount, uint256 unclaimedAmount, int256 floatReward, uint256 accStakedAmount, uint256 percent);

  function init() external onlyNotInit {
    assetWeight = DEFAULT_CORE_BTC_CONVERSION;
    lstGradePercentage = SatoshiPlusHelper.DENOMINATOR;
    alreadyInit = true;
  }

  /*********************** IAgent implementations ***************************/
  /// Receive round rewards from StakeHub, which is triggered at the beginning of turn round.
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList, uint256 /*round*/) external override onlyStakeHub {
    uint256 validatorSize = validators.length;
    require(validatorSize == rewardList.length, "the length of validators and rewardList should be equal");

    uint256[] memory rewards = new uint256[](validatorSize);
    StakeAmount memory sa;
    for (uint256 i = 0; i < validatorSize; ++i) {
      if (rewardList[i] == 0) {
        continue;
      }
      sa = candidateMap[validators[i]];
      if (sa.lstStakeAmount + sa.stakeAmount == 0) {
        continue;
      }
      rewards[i] = rewardList[i] * sa.lstStakeAmount / (sa.lstStakeAmount + sa.stakeAmount);
    }
    IBitcoinStake(BTCLST_STAKE_ADDR).distributeReward(validators, rewards);

    for (uint256 i = 0; i < validatorSize; ++i) {
      /// @dev could be 0-0
      rewards[i] = rewardList[i] - rewards[i];
    }
    IBitcoinStake(BTC_STAKE_ADDR).distributeReward(validators, rewards);
  }

  /// Get staked BTC amount
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of staked BTC amounts of all candidates in this round
  /// @return totalAmount Total BTC staked on all candidates in this round
  function getStakeAmounts(address[] calldata candidates, uint256 /*round*/) external override onlyStakeHub returns (uint256[] memory amounts, uint256 totalAmount) {
    uint256 candidateSize = candidates.length;
    uint256[] memory lstAmounts = IBitcoinStake(BTCLST_STAKE_ADDR).getStakeAmounts(candidates);
    amounts = IBitcoinStake(BTC_STAKE_ADDR).getStakeAmounts(candidates);
    for (uint256 i = 0; i < candidateSize; ++i) {
      candidateMap[candidates[i]].lstStakeAmount = lstAmounts[i];
      candidateMap[candidates[i]].stakeAmount = amounts[i];
      amounts[i] += lstAmounts[i];
      totalAmount += amounts[i];
    }
  }

  /// Start new round, this is called by the StakeHub contract
  /// @param validators List of elected validators in this round
  /// @param round The new round tag
  function setNewRound(address[] calldata validators, uint256 round) external override onlyStakeHub {
    IBitcoinStake(BTC_STAKE_ADDR).setNewRound(validators, round);
    IBitcoinStake(BTCLST_STAKE_ADDR).setNewRound(validators, round);
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @param coreAmount the accumurated amount of staked CORE.
  /// @param settleRound the settlement round
  /// @return reward Amount claimed
  /// @return floatReward floating reward amount
  /// @return accStakedAmount accumulated stake amount (multiplied by rounds), used for grading calculation
  function claimReward(address delegator, uint256 coreAmount, uint256 settleRound) external override onlyStakeHub returns (uint256 reward, int256 floatReward, uint256 accStakedAmount) {
    (uint256 btcReward, uint256 btcRewardUnclaimed, uint256 btcAccStakedAmount) = IBitcoinStake(BTC_STAKE_ADDR).claimReward(delegator, settleRound);
    uint256 gradeLength = grades.length;
    uint256 p = SatoshiPlusHelper.DENOMINATOR;
    if (gradeActive && gradeLength != 0 && btcAccStakedAmount != 0) {
      uint256 stakeRate = coreAmount / btcAccStakedAmount / assetWeight;
      p = grades[0].percentage;
      for (uint256 j = gradeLength - 1; j != 0; j--) {
        if (stakeRate >= grades[j].stakeRate) {
          p = grades[j].percentage;
          break;
        }
      }
      uint256 pReward = btcReward * p / SatoshiPlusHelper.DENOMINATOR;
      floatReward = pReward.toInt256() - btcReward.toInt256();
      btcReward = pReward;
    }
    emit claimedBtcReward(delegator, btcReward, btcRewardUnclaimed, floatReward, btcAccStakedAmount, p);
    if (btcRewardUnclaimed != 0) {
      floatReward -= btcRewardUnclaimed.toInt256();
    }

    (uint256 btclstReward, , uint256 btclstAccStakedAmount) = IBitcoinStake(BTCLST_STAKE_ADDR).claimReward(delegator, settleRound);
    int256 lstFloatReward;
    if (lstGradePercentage != SatoshiPlusHelper.DENOMINATOR) {
      uint256 pLstReward = btclstReward * lstGradePercentage / SatoshiPlusHelper.DENOMINATOR;
      lstFloatReward = (pLstReward.toInt256() - btclstReward.toInt256());
      btclstReward = pLstReward;
    }
    floatReward += lstFloatReward;

    emit claimedBtcLstReward(delegator, btclstReward, 0, lstFloatReward, btclstAccStakedAmount, lstGradePercentage);
    return (btcReward + btclstReward, floatReward, btcAccStakedAmount + btclstAccStakedAmount);
  }

  /*********************** External methods ********************************/
  function getGrades() external view returns (DualStakingGrade[] memory) {
    return grades;
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "grades")) {
      uint256 lastLength = grades.length;

      RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
      uint256 currentLength = items.length;
      if (currentLength == 0) {
         revert MismatchParamLength(key);
      }

      for (uint256 i = currentLength; i < lastLength; i++) {
        grades.pop();
      }

      uint256 stakeRate;
      uint256 percentage;
      for (uint256 i = 0; i < currentLength; i++) {
        RLPDecode.RLPItem[] memory itemArray = items[i].toList();
        stakeRate = RLPDecode.toUint(itemArray[0]);
        percentage = RLPDecode.toUint(itemArray[1]);
        if (stakeRate > 1e8) {
          revert OutOfBounds('stakeRate', stakeRate, 0, 1e8);
        }
        if (percentage > SatoshiPlusHelper.DENOMINATOR * 100) {
          revert OutOfBounds('percentage', percentage, 0, SatoshiPlusHelper.DENOMINATOR * 100);
        }
        if (i >= lastLength) {
          grades.push(DualStakingGrade(uint32(stakeRate), uint32(percentage)));
        } else {
          grades[i] = DualStakingGrade(uint32(stakeRate), uint32(percentage));
        }
      }
      // check stakeRate & percentage in order.
      for (uint256 i = 1; i < currentLength; i++) {
        require(grades[i-1].stakeRate < grades[i].stakeRate, "stakeRate disorder");
        require(grades[i-1].percentage < grades[i].percentage, "percentage disorder");
      }
      require(grades[0].stakeRate == 0, "lowest stakeRate must be zero");
    } else if (Memory.compareStrings(key, "gradeActive")) {
      if (value.length != 1) {
        revert MismatchParamLength(key);
      }
      uint8 newGradeActive = value.toUint8(0);
      if (newGradeActive > 1) {
        revert OutOfBounds(key, newGradeActive, 0, 1);
      }
      gradeActive = newGradeActive == 1;
    } else if (Memory.compareStrings(key, "lstGradePercentage")) {
      if (value.length != 32) {
        revert MismatchParamLength(key);
      }
      uint256 newPercentage = value.toUint256(0);
      if (newPercentage == 0 || newPercentage > SatoshiPlusHelper.DENOMINATOR * 10) {
        revert OutOfBounds(key, newPercentage, 1, SatoshiPlusHelper.DENOMINATOR * 10);
      }
      lstGradePercentage = newPercentage;
    } else {
        revert UnsupportedGovParam(key);
    }

    emit paramChange(key, value);
  }
}