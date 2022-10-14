pragma solidity 0.6.12;
import "./System.sol";
import "./interface/ISystemReward.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBurn.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";

contract SystemReward is System, ISystemReward, IParamSubscriber {
  uint256 public constant INCENTIVE_BALANCE_CAP = 1e25;

  uint256 public incentiveBalanceCap;
  uint256 public numOperator;
  mapping(address => bool) operators;

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
  event paramChange(string key, bytes value);

  receive() external payable{
    if (msg.value>0) {
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

  function receiveRewards() external payable override {
    if (msg.value > 0) {
      if (address(this).balance > incentiveBalanceCap) {
        IBurn(BURN_ADDR).burn{value:address(this).balance - incentiveBalanceCap}();
      }
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

  function claimRewards(address payable to, uint256 amount)
    external
    override(ISystemReward)
    onlyInit
    onlyOperator
    returns (uint256)
  {
    uint256 actualAmount = amount < address(this).balance ? amount : address(this).balance;
    if (actualAmount > 0) {
      to.transfer(actualAmount);
      emit rewardTo(to, actualAmount);
    } else {
      emit rewardEmpty();
    }
    return actualAmount;
  }

  function isOperator(address addr) external view returns (bool) {
    return operators[addr];
  }

  /*********************** Param update ********************************/
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "incentiveBalanceCap")) {
      require(value.length == 32, "length of incentiveBalanceCap mismatch");
      uint256 newIncentiveBalanceCap = BytesToTypes.bytesToUint256(32, value);
      require(newIncentiveBalanceCap >= INCENTIVE_BALANCE_CAP/10, "the incentiveBalanceCap out of range");
      incentiveBalanceCap = newIncentiveBalanceCap;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }
}
