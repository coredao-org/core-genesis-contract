// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

contract BitcoinLSTMerkleToken is ERC20 {
    address public bitcoinLSTStake;
    bytes32 public merkleRoot;
    uint256 public lastRewardRoundEndTime; // End time of the last reward round

    mapping(address => uint256) public lastStakeTime; // Timestamp of the last stake
    mapping(address => uint256) public claimedRewards; // Total claimed rewards per user

    event RewardsDistributed(bytes32 merkleRoot, uint256 roundEndTime);
    event RewardClaimed(address indexed account, uint256 amount);

    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) {
        bitcoinLSTStake = _bitcoinLSTStake;
    }

    modifier onlyBtcAgent() {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can call this function");
        _;
    }

    function updateRewards(bytes32 _merkleRoot, uint256 _roundEndTime) external onlyBtcAgent {
        merkleRoot = _merkleRoot;
        lastRewardRoundEndTime = _roundEndTime;

        emit RewardsDistributed(merkleRoot, lastRewardRoundEndTime);
    }

    function mint(address to, uint256 amount) external onlyBtcAgent {
        _mint(to, amount);
        lastStakeTime[to] = block.timestamp;
    }

    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }

    function claimReward(uint256 amount, bytes32[] calldata merkleProof) external {
        require(lastStakeTime[msg.sender] <= lastRewardRoundEndTime, "Must be staked for at least one full round to claim rewards");

        bytes32 node = keccak256(abi.encodePacked(msg.sender, amount));
        require(MerkleProof.verify(merkleProof, merkleRoot, node), "Invalid Merkle proof");

        require(claimedRewards[msg.sender] < amount, "Rewards already claimed");

        uint256 claimableAmount = amount - claimedRewards[msg.sender];
        claimedRewards[msg.sender] = amount;

        payable(msg.sender).transfer(claimableAmount);

        emit RewardClaimed(msg.sender, claimableAmount);
    }

    receive() external payable {}
}
