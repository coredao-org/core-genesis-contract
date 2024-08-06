// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import '@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol';
import '@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol';
import '@openzeppelin/contracts/access/Ownable.sol';
import '@openzeppelin/contracts/token/ERC20/ERC20.sol';
import './interface/IBitcoinLSTToken.sol';

contract BTCLSTToken is ERC20, ERC20Burnable, Pausable, Ownable, IBitcoinLSTToken {
    address public bitcoinLSTStake;

    modifier onlyBtcLSTStake() {
        require(msg.sender == bitcoinLSTStake, "only invoked by bitcoin lst stake");
        _;
    }

    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) Ownable() {
        bitcoinLSTStake = _bitcoinLSTStake;
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
        (bool success, ) = bitcoinLSTStake.call(
            abi.encodeWithSignature("onTokenTransfer(address,address,uint256)",
                from, to, amount)
        );
        require(success, "call lstStake.onTokenTransfer failed.");
    }

    function setBitcoinLSTStake(address newAddr) external onlyOwner {
        bitcoinLSTStake = newAddr;
    }

    // Functions to pause and unpause the contract
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
