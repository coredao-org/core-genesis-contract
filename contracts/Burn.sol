// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./interface/IParamSubscriber.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/Address.sol";
import "./interface/IBurn.sol";

/// This contract burns CORE tokens up to pre defined CAP
contract Burn is System, IBurn, IParamSubscriber {
  uint256 public constant BURN_CAP = 105e25;
  uint256 private constant REV_SHARE_ACCURACY = 1000;

  event BurnSumsReroutedToRevShare(uint indexed msgValue, uint indexed revSharePortionMillis, uint indexed revShareSum);

  uint256 public burnCap;
  uint256 public revSharePortionMillis;

  /*********************** init **************************/
  function init() external onlyNotInit {
    burnCap = BURN_CAP;
    revSharePortionMillis = 0; // start with no rev-share
    alreadyInit = true;
  }

  /*********************** events **************************/
  event burned(address indexed to, uint256 amount);

  /// Burn incoming CORE tokens
  /// Send back the portion which exceeds the cap
  function burn() external payable override {
    uint msgValue = _rerouteRevSharePortion(msg.value);
    uint256 v = msgValue;
    if (address(this).balance > burnCap) {
      uint256 remain = address(this).balance - burnCap;
      if (remain >= msgValue) {
        remain = msgValue;
        v = 0;
      } else {
        v = msgValue - remain;
      }
      payable(msg.sender).transfer(remain);
    }
    if (v != 0) emit burned(msg.sender, v);
  }

  function _rerouteRevSharePortion(uint msgValue) private returns(uint) {
    if (msgValue == 0 || revSharePortionMillis == 0) {
      return msgValue;
    }
    uint revShareSum = msgValue * revSharePortionMillis / REV_SHARE_ACCURACY;
    Address.sendValue(payable(REV_SHARE_ADDR), revShareSum); //@safe
    emit BurnSumsReroutedToRevShare(msgValue, revSharePortionMillis, revShareSum);
    return msgValue - revShareSum;
  }

  /*********************** Param update ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "burnCap")) {
      uint256 newBurnCap = BytesToTypes.bytesToUint256(32, value);
      if (newBurnCap < address(this).balance) {
        revert OutOfBounds(key, newBurnCap, address(this).balance, type(uint256).max);
      }
      burnCap = newBurnCap;
    } else if (Memory.compareStrings(key, "revSharePortionMillis")) {
      uint256 newRevShareMillis = BytesToTypes.bytesToUint256(32, value);
	    require(newRevShareMillis <= REV_SHARE_ACCURACY, "rev-share portion cannot exceed 100%");
      revSharePortionMillis = newRevShareMillis;
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }
}
