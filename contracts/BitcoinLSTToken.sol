// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "./interface/IBitcoinLSTStake.sol";

contract BTCLSTToken is ERC20 {

    address public bitcoinLSTStake;

    event RewardsDistributed(address[] accounts, uint256[] amounts);
    
    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) {
        bitcoinLSTStake = _bitcoinLSTStake;
    }

    function mint(address to, uint256 amount) external {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can mint");
        _mint(to, amount);
    }

    function burn(uint256 amount) external {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can mint");
        _burn(msg.sender, amount);
    }

    receive() external payable {}
}
