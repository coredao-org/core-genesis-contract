pragma solidity ^0.6.4;

import "./lib/SafeMath.sol";
import "./lib/Ownable.sol";
import "./System.sol";

contract TeamVesting is Ownable, System {
  using SafeMath for uint256;

  event Received(uint256 value, uint256 balance);
  event Released(uint256 amount);
  event Revoked();

  // beneficiary of tokens after they are released
  address payable public beneficiary;

  uint256 public cliff;
  uint256 public start;
  uint256 public duration;

  bool public revocable;
  bool public revoked;

  uint256 public released;

  /**
   * @dev Creates a vesting contract that vests its balance of native token to the
   * _beneficiary, gradually in a linear fashion until _start + _duration. By then all
   * of the balance will have vested.
   * @param _beneficiary address of the beneficiary to whom vested tokens are transferred
   * @param _cliff duration in seconds of the cliff in which tokens will begin to vest
   * @param _duration duration in seconds of the period in which the tokens will vest
   * @param _revocable whether the vesting is revocable or not
   */
  constructor (
    address payable _beneficiary,
    uint256 _start,
    uint256 _cliff,
    uint256 _duration,
    bool    _revocable
  ) public {
    require(_beneficiary != address(0x0));
    require(_cliff <= _duration);

    beneficiary = _beneficiary;
    start       = _start;
    cliff       = _start.add(_cliff);
    duration    = _duration;
    revocable   = _revocable;
  }

  receive() payable external {
    emit Received(msg.value, address(this).balance);
  }


  /**
   * @notice Only allow calls from the beneficiary of the vesting contract
   */
  modifier onlyBeneficiary() {
    require(msg.sender == beneficiary);
    _;
  }

  /**
   * @notice Allow the beneficiary to change its address
   * @param target the address to transfer the right to
   */
  function changeBeneficiary(address payable target) onlyBeneficiary external {
    require(target != address(0));
    beneficiary = target;
  }

  /**
   * @notice Transfers vested tokens to beneficiary.
   */
  function release() onlyBeneficiary external {
    require(nowTime() >= cliff);
    _releaseTo(beneficiary);
  }

  /**
   * @notice Transfers vested tokens to a target address.
   * @param target the address to send the tokens to
   */
  function releaseTo(address payable target) onlyBeneficiary external {
    require(nowTime() >= cliff);
    _releaseTo(target);
  }

  /**
   * @notice Transfers vested tokens to beneficiary.
   */
  function _releaseTo(address payable target) internal {
    // re-entry protection
    require(!isContract(target), "can not release to a smart contract");
    
    uint256 unreleased = releasableAmount();

    released = released.add(unreleased);

    target.transfer(unreleased);

    emit Released(released);
  }

  /**
   * @notice Allows the owner to revoke the vesting. Tokens already vested are sent to the beneficiary.
   */
  function revoke() onlyOwner external {
    require(revocable);
    require(!revoked);

    // Release all vested tokens
    _releaseTo(beneficiary);

    // Send the remainder to the owner
    owner.transfer(address(this).balance);

    revoked = true;

    emit Revoked();
  }


  /**
   * @dev Calculates the amount that has already vested but hasn't been released yet.
   */
  function releasableAmount() public view returns (uint256) {
    return vestedAmount().sub(released);
  }

  /**
   * @dev Calculates the amount that has already vested.
   */
  function vestedAmount() public view returns (uint256) {
    uint256 currentBalance = address(this).balance;
    uint256 totalBalance = currentBalance.add(released);

    if (nowTime() < cliff) {
      return 0;
    } else if (nowTime() >= start.add(duration) || revoked) {
      return totalBalance;
    } else {
      return totalBalance.mul(nowTime().sub(start)).div(duration);
    }
  }

  function nowTime() virtual public view returns (uint256) {
      return now;
  }
}