// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import '@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol';
import '@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol';
import '@openzeppelin/contracts/token/ERC20/ERC20.sol';
import './interface/IBitcoinLSTToken.sol';
import "./interface/IParamSubscriber.sol";
import "./System.sol";

contract BTCLSTToken is ERC20, ERC20Burnable, Pausable, IBitcoinLSTToken, System, IParamSubscriber {

    modifier onlyBtcLSTStake() {
        require(msg.sender == BTCLST_STAKE_ADDR, "only invoked by bitcoin lst stake");
        _;
    }

    constructor(string memory _name, string memory _symbol) ERC20(_name, _symbol) {
    }

    function mint(address to, uint256 amount) external override onlyBtcLSTStake whenNotPaused {
        _mint(to, amount);
    }

    function burn(address to, uint256 amount) external override onlyBtcLSTStake whenNotPaused {
        _burn(to, amount);
    }

    function transfer(address to, uint256 amount) public override whenNotPaused returns (bool) {
        bool b = super.transfer(to, amount);
        address owner = _msgSender();
        _onTransfer(owner, to, amount);
        return b;
    }

    function transferFrom(address from, address to, uint256 amount) public override whenNotPaused returns (bool) {
        bool b = super.transferFrom(from, to, amount);
        _onTransfer(from, to, amount);
        return b;
    }

    function _onTransfer(address from, address to, uint256 amount) internal {
        (bool success, ) = BTCLST_STAKE_ADDR.call(
            abi.encodeWithSignature("onTokenTransfer(address,address,uint256)",
                from, to, amount)
        );
        require(success, "call lstStake.onTokenTransfer failed.");
    }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "pause")) {
      _pause();
    } else if (Memory.compareStrings(key, "unpause")) {
      _unpause();
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }
}
