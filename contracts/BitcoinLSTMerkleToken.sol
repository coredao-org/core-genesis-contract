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

    mapping(address => uint256) public lastClaimedRound; // Last round a user claimed rewards

    event RewardsAdded(bytes32 merkleRoot, uint256 roundEndTime, uint256 roundNumber);
    event RewardClaimed(address indexed account, uint256 amount);
    event LSTBurned(address indexed account, uint256 amount, string bitcoinAddress);

    constructor(string memory _name, string memory _symbol, address _bitcoinLSTStake) ERC20(_name, _symbol) {
        bitcoinLSTStake = _bitcoinLSTStake;
        currentRound = 0;
        currentRoundTime = block.timestamp;
    }

    modifier onlyBtcAgent() {
        require(msg.sender == bitcoinLSTStake, "Only BTC Agent can call this function");
        _;
    }

    function updateRewards(bytes32 _merkleRoot, uint256 _roundEndTime) external payable onlyBtcAgent {
        merkleRoot = _merkleRoot;
        lastRewardRoundEndTime = _roundEndTime;
        currentRound++;
        emit RewardsAdded(merkleRoot, lastRewardRoundEndTime, roundNumber);
    }

    function mint(address to, uint256 amount) external onlyBtcAgent {
        _mint(to, amount);
    }

    //User must pass in the bitcoin address during a burn event, so we know where to send the unlocked BTC (important is LST has been traded)
    function burn(uint256 amount, string memory bitcoinAddress) external {
        _burn(msg.sender, amount);
        emit LSTBurned(msg.sender, amount, bitcoinAddress);
    }

    function claimReward(uint256 amount, bytes32[] calldata merkleProof) external whenNotPaused {
        require(lastClaimedRound[msg.sender] < currentRound, "Rewards already claimed for this round");

        bytes32 node = keccak256(abi.encodePacked(msg.sender, amount));
        require(MerkleProof.verify(merkleProof, merkleRoot, node), "Invalid Merkle proof");

        lastClaimedRound[msg.sender] = currentRound;

        payable(msg.sender).transfer(amount);

        emit RewardClaimed(msg.sender, amount);
    }

    function pause() external onlyBtcAgent {
        _pause();
    }

    function unpause() external onlyBtcAgent {
        _unpause();
    }

    receive() external payable {}
}
