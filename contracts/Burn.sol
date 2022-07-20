pragma solidity ^0.6.4;
import "./System.sol";
import "./interface/IParamSubscriber.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IBurn.sol";

contract Burn is System, IBurn, IParamSubscriber {
  uint256 public constant BURN_CAP = 105e25;

  uint256 public burnCap;

  /*********************** init **************************/
  function init() external onlyNotInit {
    burnCap = BURN_CAP;
    alreadyInit = true;
  }

  event burned(address indexed to, uint256 amount);
  event paramChange(string key, bytes value);

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
      msg.sender.transfer(remain);
    }
    if (v > 0) emit burned(msg.sender, v);
  }

  /*********************** Param update ********************************/
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "burnCap")) {
      require(value.length == 32, "length of burnCap mismatch");
      uint256 newBurnCap = BytesToTypes.bytesToUint256(32, value);
      require(newBurnCap != 0 && newBurnCap > address(this).balance, "the burnCap out of range");
      burnCap = newBurnCap;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }
}
