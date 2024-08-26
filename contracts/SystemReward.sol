// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./interface/ISystemReward.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBurn.sol";
import "./lib/BytesLib.sol";
import "./lib/Memory.sol";

/// This smart contract manages funds for relayers and verifiers
contract SystemReward is System, ISystemReward, IParamSubscriber {
  using BytesLib for *;
  uint256 public constant INCENTIVE_BALANCE_CAP = 1e25;

  uint256 public incentiveBalanceCap;
  uint256 public numOperator;
  mapping(address => bool) public operators;
  bool public isBurn;

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
        if (isBurn) {
          IBurn(BURN_ADDR).burn{ value: value }();
        } else {
          payable(FOUNDATION_ADDR).transfer(value);
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
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }
}
