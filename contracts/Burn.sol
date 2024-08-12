// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./interface/IParamSubscriber.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IBurn.sol";

/// This contract burns CORE tokens up to pre defined CAP
contract Burn is System, IBurn, IParamSubscriber {
  uint256 public constant BURN_CAP = 105e25;

  uint256 public burnCap;

  /*********************** init **************************/
  function init() external onlyNotInit {
    burnCap = BURN_CAP;
    alreadyInit = true;
  }

  /*********************** events **************************/
  event burned(address indexed to, uint256 amount);

  /// Burn incoming CORE tokens
  /// Send back the portion which exceeds the cap
  function burn() external payable override {
    uint256 v = msg.value;
    if (address(this).balance > burnCap) {
      uint256 remain = address(this).balance - burnCap;
      if (remain >= msg.value) {
        remain = msg.value;
        v = 0;
      } else {
        v = msg.value - remain;
      }
      payable(msg.sender).transfer(remain);
    }
    if (v != 0) emit burned(msg.sender, v);
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
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }
}
