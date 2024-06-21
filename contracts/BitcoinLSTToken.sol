// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "./interfaces/IBitcoinLSTStake.sol";

contract BTCLSTToken is ERC20 {

    address public bitcoinLSTStake;
    uint256 public rewardPerTokenStored; // Accumulated reward per token
    uint256 public lastUpdateTime; // Last time rewards were updated
    uint256 public lastRewardRoundEndTime; // End time of the last reward round

    mapping(address => uint256) public userRewardPerTokenPaid; // User's reward per token paid
    mapping(address => uint256) public rewards; // User's accumulated rewards
    mapping(address => uint256) public lastStakeTime; // Timestamp of the last stake

    event RewardsDistributed(address[] accounts, uint256[] amounts);
    
    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) {
        bitcoinLSTStake = _bitcoinLSTStake;
    }

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = block.timestamp;
        if (account != address(0)) {
            rewards[account] = _calculateEarned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    function rewardPerToken() public view returns (uint256) {
        if (totalSupply() == 0) {
            return rewardPerTokenStored;
        }
        return rewardPerTokenStored;
    }

    function _calculateEarned(address account) internal view returns (uint256) {
        return (balanceOf(account) * (rewardPerTokenStored - userRewardPerTokenPaid[account]) / 1e18) + rewards[account];
    }

    function mint(address to, uint256 amount) external updateReward(to) {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can mint");
        _mint(to, amount);
        lastStakeTime[to] = block.timestamp;
    }

    function burn(uint256 amount) external {

        if(lastStakeTime[msg.sender] <= lastRewardRoundEndTime && rewards[msg.sender] > 0) {
            claimReward();
        }

        _burn(msg.sender, amount);
    }

    function distributeRewards(uint256 reward, uint256 roundTag) external {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can distribute rewards");

        // Calculate new reward per token stored
        if (totalSupply() > 0) {
            rewardPerTokenStored += (reward * 1e18 / totalSupply());
        }

        // Update last update time and last reward round end time
        lastUpdateTime = block.timestamp;
        lastRewardRoundEndTime = block.timestamp;
    }

    function claimReward() external updateReward(msg.sender) {
        require(lastStakeTime[msg.sender] <= lastRewardRoundEndTime, "Must be staked for at least one full round to claim rewards");

        uint256 reward = rewards[msg.sender];
        require(reward > 0, "No rewards to claim");
        rewards[msg.sender] = 0;
        payable(msg.sender).transfer(reward); // Assuming the contract has ETH balance to pay rewards
    }

    receive() external payable {}
}
