// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "./System.sol";
import "./interface/ISystemReward.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IBurn.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";

/// This smart contract manages funds for relayers and verifiers
contract SystemReward is System, ISystemReward, IParamSubscriber {
  uint256 public constant INCENTIVE_BALANCE_CAP = 1e25;

  uint256 public incentiveBalanceCap;
  uint256 public numOperator;
  mapping(address => bool) operators;
  bool isBurn;

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

  receive() external payable {
    if (msg.value != 0) {
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

/* @product Receive external funds - currently not limited to system-only invocation
   @logic
      1. Receive and stores in the contract an eth amount up to the total contract balance of 
         incentiveBalanceCap (default value: 1e25)
      2. If post-transfer balance exeeds incentiveBalanceCap then:
          a. if in isBurn mode then burn the excess, see the Burn.burn() documentation
              for details, especially the part detailing that if the total contract 
              balance (i.e. the sum of all burned tokens) exceeds the burnCap then the 
              excess (up to the limit of the current sum of tokens to burn) is returned to the SystemReward contract
          b. if not in isBurn mode - transfer the excess to the FOUNDATION address
*/
  function receiveRewards() external payable override onlyInit onlyIfPositiveValue {
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

/* @product Called by the Light BTC Client for relayers and by the SlashIndicator contracts 
   to claim a reward for external verifiers (Note: the latter is currently not enforced!)  @openissue
   @logic
      1. The function transfers the eth amount specified by the caller to the destination 
         address.@author.
      2. If the current SystemReward balance is less than the amount specified by the caller, 
         then no error is issued rather the amount gets slashed to the current balance.
*/
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
      require(value.length == 32, "length of incentiveBalanceCap mismatch");
      uint256 newIncentiveBalanceCap = BytesToTypes.bytesToUint256(32, value);
      require(newIncentiveBalanceCap != 0, "the incentiveBalanceCap out of range");
      incentiveBalanceCap = newIncentiveBalanceCap;
    } else if (Memory.compareStrings(key, "isBurn")) {
      require(value.length == 32, "length of isBurn mismatch");
      uint256 newIsBurn = BytesToTypes.bytesToUint256(32, value);
      require(newIsBurn <= 1, "the newIsBurn out of range");
      isBurn = newIsBurn == 1;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }
}
