// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./interface/ISystemReward.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBurn.sol";
import "./lib/BytesLib.sol";
import "./lib/Memory.sol";
import "./lib/RLPDecode.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./lib/Address.sol";
import "./System.sol";

/// This smart contract manages funds for relayers and verifiers
contract SystemReward is System, ISystemReward, IParamSubscriber {
  using BytesLib for *;
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.RLPItem;
  uint256 public constant INCENTIVE_BALANCE_CAP = 1e25;

  uint256 public incentiveBalanceCap;
  // Add STAKE_HUB_ADDR into operators via gov in v1.0.12
  uint256 public numOperator;
  mapping(address => bool) public operators;
  bool public isBurn;

  mapping(address => uint256) public whiteLists;
  WhiteList[] public whiteListSet;

  struct WhiteList {
    address member;
    uint32 percentage;
  }

  /*********************** init **************************/
  function init() external onlyNotInit {
    operators[LIGHT_CLIENT_ADDR] = true;
    operators[SLASH_CONTRACT_ADDR] = true;
    numOperator = 2;
    incentiveBalanceCap = INCENTIVE_BALANCE_CAP;
    alreadyInit = true;
  }

  modifier onlyOperator() {
    require(operators[msg.sender], "only operator is allowed to call the method");
    _;
  }

  /*********************** events **************************/
  event rewardTo(address indexed to, uint256 amount);
  event rewardEmpty();
  event receiveDeposit(address indexed from, uint256 amount);
  event whitelistTransferSuccess(address indexed member, uint256 value);
  event whitelistTransferFailed(address indexed member, uint256 value);

  receive() external payable {
    if (msg.value != 0) {
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

  /// Receive funds from system, burn the portion which exceeds cap
  function receiveRewards() external payable override onlyInit {
    if (msg.value != 0) {
      if (address(this).balance > incentiveBalanceCap) {
        uint256 value = address(this).balance - incentiveBalanceCap;
        uint256 remain = value;
        for (uint256 i = 0; i < whiteListSet.length; i++) {
          uint256 toWhiteListValue = value * whiteListSet[i].percentage / SatoshiPlusHelper.DENOMINATOR;
          if (remain >= toWhiteListValue) {
            bool success = payable(whiteListSet[i].member).send(toWhiteListValue);
            if (success) {
              remain -= toWhiteListValue;
              emit whitelistTransferSuccess(whiteListSet[i].member, toWhiteListValue);
            } else {
              emit whitelistTransferFailed(whiteListSet[i].member, toWhiteListValue);
            }
          }
        }
        if (remain != 0) {
          if (isBurn) {
            IBurn(BURN_ADDR).burn{ value: remain }();
          } else {
            payable(FOUNDATION_ADDR).transfer(remain);
          }
        }
      }
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

  /// Claim rewards, this method can only be called by valid operator addresses
  /// @param to The address to claim rewards to
  /// @param amount The amount to claim
  function claimRewards(address payable to, uint256 amount)
    external
    override(ISystemReward)
    onlyInit
    onlyOperator
    returns (uint256)
  {
    uint256 actualAmount = amount < address(this).balance ? amount : address(this).balance;
    if (to != address(0) && actualAmount != 0) {
      to.transfer(actualAmount);
      emit rewardTo(to, actualAmount);
    } else {
      emit rewardEmpty();
    }
    return actualAmount;
  }

  /// Whether the given address is a valid operator
  /// @param addr The address to check
  /// @return true/false
  function isOperator(address addr) external view returns (bool) {
    return operators[addr];
  }

  function getWhiteListSet() external view returns(WhiteList[] memory) {
    return whiteListSet;
  }

  /*********************** Param update ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "incentiveBalanceCap")) {
      if (value.length != 32) {
        revert MismatchParamLength(key);
      }
      uint256 newIncentiveBalanceCap = value.toUint256(0);
      if (newIncentiveBalanceCap == 0) {
        revert OutOfBounds(key, newIncentiveBalanceCap, 1, type(uint256).max);
      }
      incentiveBalanceCap = newIncentiveBalanceCap;
    } else if (Memory.compareStrings(key, "isBurn")) {
      if (value.length != 1) {
        revert MismatchParamLength(key);
      }
      uint8 newIsBurn = value.toUint8(0);
      if (newIsBurn > 1) {
        revert OutOfBounds(key, newIsBurn, 0, 1);
      }
      isBurn = newIsBurn == 1;
    } else if (Memory.compareStrings(key, "addOperator")) {
      if (value.length != 20) {
        revert MismatchParamLength(key);
      }
      address newOperator = value.toAddress(0);
      if (!operators[newOperator]) {
        operators[newOperator] = true;
        numOperator++;
      }
    } else if (Memory.compareStrings(key, "addWhiteList")) {
      (address member, uint32 percentage) = _decodeWhiteList(key, value);
      require(whiteLists[member] == 0, "whitelist member already exists");
      whiteListSet.push(WhiteList(member, percentage));
      whiteLists[member] = whiteListSet.length;
      _checkPercentage();
    } else if (Memory.compareStrings(key, "modifyWhiteList")) {
      (address member, uint32 percentage) = _decodeWhiteList(key, value);
      require(whiteLists[member] != 0, "whitelist member does not exist");
      whiteListSet[whiteLists[member] - 1].percentage = percentage;
      _checkPercentage();
    } else if (Memory.compareStrings(key, "removeWhiteList")) {
      if (value.length != 20) {
        revert MismatchParamLength(key);
      }
      address member = value.toAddress(0);
      uint256 index = whiteLists[member];
      require(index != 0, "whitelist member does not exist");
      if (index != whiteListSet.length) {
        WhiteList storage whiteList = whiteListSet[whiteListSet.length - 1];
        whiteListSet[index - 1] = whiteList;
        whiteLists[whiteList.member] = index;
      }
      whiteListSet.pop();
      delete whiteLists[member];
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }

  function _decodeWhiteList(string calldata key, bytes calldata value) internal pure returns(address, uint32) {
    if (value.length > 25) {
      revert MismatchParamLength(key);
    }
    RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
    address member = RLPDecode.toAddress(items[0]);
    uint256 percentage = RLPDecode.toUint(items[1]);
    if (percentage == 0 || percentage > SatoshiPlusHelper.DENOMINATOR) {
      revert OutOfBounds(key, percentage, 1, SatoshiPlusHelper.DENOMINATOR);
    }
    return (member, uint32(percentage));
  }

  function _checkPercentage() internal view{
    uint32 totalPercentage = 0;
    for (uint256 i = 0; i < whiteListSet.length; i++) {
      totalPercentage += whiteListSet[i].percentage;
    }
    require(totalPercentage <= SatoshiPlusHelper.DENOMINATOR, "total precentage exceeds the upper limit");
  }
}
