pragma solidity ^0.6.4;
import "./System.sol";

contract Foundation is System {
  event received(address indexed from, uint256 amount);
  event fundSuccess(address indexed payee, uint256 amount);
  event fundFailed(address indexed payee, uint256 amount, uint256 balance);

  receive() external payable {
    if (msg.value > 0) {
      emit received(msg.sender, msg.value);
    }
  }

  function fund(address payable payee, uint256 amount) external onlyGov {
    bool ret = payee.send(amount);
    if (ret) {
      emit fundSuccess(payee, amount);
    } else {
      emit fundFailed(payee, amount, address(this).balance);
    }
  }
}
