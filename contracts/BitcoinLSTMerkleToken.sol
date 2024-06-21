// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

contract BitcoinLSTMerkleToken is ERC20, Pausable {
    address public bitcoinLSTStake;
    bytes32 public merkleRoot;
    uint256 public lastRewardRoundEndTime; // End time of the last reward round
    uint256 public currentRound; // Current reward round number

    mapping(address => uint256) public lastStakeTime; // Timestamp of the last stake
    mapping(address => uint256) public claimedRewards; // Total claimed rewards per user
    mapping(address => uint256) public lastClaimedRound; // Last round a user claimed rewards

    event RewardsDistributed(bytes32 merkleRoot, uint256 roundEndTime, uint256 roundNumber);
    event RewardClaimed(address indexed account, uint256 amount);

    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) {
        bitcoinLSTStake = _bitcoinLSTStake;
        currentRound = 0;
    }

    modifier onlyBtcAgent() {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can call this function");
        _;
    }

    function updateRewards(bytes32 _merkleRoot, uint256 _roundEndTime) external onlyBtcAgent whenPaused {
        merkleRoot = _merkleRoot;
        lastRewardRoundEndTime = _roundEndTime;
        currentRound++;

        emit RewardsDistributed(merkleRoot, lastRewardRoundEndTime, currentRound);
    }

    function mint(address to, uint256 amount) external onlyBtcAgent {
        _mint(to, amount);
        lastStakeTime[to] = block.timestamp;
    }

    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }

    function claimReward(uint256 amount, bytes32[] calldata merkleProof) external whenNotPaused {
        require(lastStakeTime[msg.sender] < lastRewardRoundEndTime, "Must be staked for at least one full round to claim rewards");
        require(lastClaimedRound[msg.sender] < currentRound, "Rewards already claimed for this round");

        bytes32 node = keccak256(abi.encodePacked(msg.sender, amount));
        require(MerkleProof.verify(merkleProof, merkleRoot, node), "Invalid Merkle proof");

        uint256 claimableAmount = amount - claimedRewards[msg.sender];
        claimedRewards[msg.sender] = amount;
        lastClaimedRound[msg.sender] = currentRound;

        payable(msg.sender).transfer(claimableAmount);

        emit RewardClaimed(msg.sender, claimableAmount);
    }

    function pause() external onlyBtcAgent {
        _pause();
    }

    function unpause() external onlyBtcAgent {
        _unpause();
    }

    receive() external payable {}
}
