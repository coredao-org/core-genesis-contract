// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./lib/Memory.sol";
import "./lib/BytesToTypes.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./interface/ILightClient.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ISystemReward.sol";
import "./interface/IParamSubscriber.sol";
import "./System.sol";

/// This contract implements a BTC light client on Core blockchain
/// Relayers store BTC blocks to Core blockchain by calling this contract
/// Which is used to calculate hybrid score and reward distribution
contract BtcLightClient is ILightClient, System, IParamSubscriber{

  // error codes for storeBlockHeader
  int256 public constant ERR_DIFFICULTY = 10010; // difficulty didn't match current difficulty
  int256 public constant ERR_RETARGET = 10020;  // difficulty didn't match retarget
  int256 public constant ERR_NO_PREV_BLOCK = 10030;
  int256 public constant ERR_BLOCK_ALREADY_EXISTS = 10040;
  int256 public constant ERR_MERKLE = 10050;
  int256 public constant ERR_PROOF_OF_WORK = 10090;

  // for verifying Bitcoin difficulty
  uint32 public constant DIFFICULTY_ADJUSTMENT_INTERVAL = 2016; // Bitcoin adjusts every 2 weeks
  uint64 public constant TARGET_TIMESPAN = 14 * 24 * 60 * 60; // 2 weeks
  uint64 public constant TARGET_TIMESPAN_DIV_4 = TARGET_TIMESPAN / 4;
  uint64 public constant TARGET_TIMESPAN_MUL_4 = TARGET_TIMESPAN * 4;
  int256 public constant UNROUNDED_MAX_TARGET = 2**224 - 1; // different from (2**16-1)*2**208 http://bitcoin.stackexchange.com/questions/13803/how-exactly-was-the-original-coefficient-for-difficulty-determined

  bytes public constant INIT_CONSENSUS_STATE_BYTES = hex"0000402089138e40cd8b4832beb8013bc80b1425c8bcbe10fc280400000000000000000058a06ab0edc5653a6ab78490675a954f8d8b4d4f131728dcf965cd0022a02cdde59f8e63303808176bbe3919";
  uint32 public constant INIT_CHAIN_HEIGHT = 766080;

  uint256 public highScore;
  bytes32 public heaviestBlock;
  bytes32 public initBlockHash;

  uint256 constant public INIT_REWARD_FOR_SYNC_HEADER = 1e19;
  uint256 public constant CALLER_COMPENSATION_MOLECULE = 50;
  uint256 public constant ROUND_SIZE=100;
  uint256 public constant MAXIMUM_WEIGHT=20;
  uint256 public constant CONFIRM_BLOCK = 6;
  uint256 public constant POWER_ROUND_GAP = 7;
  uint256 public constant INIT_STORE_BLOCK_GAS_PRICE = 35e9;

  uint256 public callerCompensationMolecule;
  uint256 public rewardForSyncHeader;
  uint256 public roundSize;
  uint256 public maxWeight;
  uint256 public countInRound=0;
  uint256 public collectedRewardForHeaderRelayer=0;
  // Expire
  uint256 public roundInterval;

  address payable[] public headerRelayerAddressRecord;
  mapping(address => uint256) public headerRelayersSubmitCount;
  mapping(address => uint256) public relayerRewardVault;

  struct CandidatePower {
    // miner is the reward address of BTC miner
    address[] miners;
    bytes32[] btcBlocks;
  }

  struct RoundPower {
    address[] candidates;
    // Key is candidate address
    mapping(address => CandidatePower) powerMap;
  }
  mapping(uint256 => RoundPower) roundPowerMap;

  // key is blockHash, value composites of following elements
  // | header   |reserved | reward address | score    | height  | ADJUSTMENT hash index| candidate address |                                                                
  // | 80 bytes | 4 bytes | 20 bytes       | 16 bytes | 4 bytes | 4 bytes              | 20 bytes          |
  // header := version, prevBlock, MerkleRoot, Time, Bits, Nonce
  mapping(bytes32 => bytes) public blockChain;
  mapping(uint32 => bytes32) public adjustmentHashes;
  mapping(bytes32 => address payable) public submitters;

  uint256 public storeBlockGasPrice;

  mapping(uint32 => bytes32) public height2HashMap;

  /*********************** events **************************/
  event StoreHeaderFailed(bytes32 indexed blockHash, int256 indexed returnCode);
  event StoreHeader(bytes32 indexed blockHash, address candidate, address indexed rewardAddr, uint32 indexed height, bytes32 bindingHash);

  /*********************** init **************************/
  /// Initialize 
  function init() external onlyNotInit {
    bytes32 blockHash = doubleShaFlip(INIT_CONSENSUS_STATE_BYTES);
    address rewardAddr;
    address candidateAddr;

    highScore = 1;
    uint256 scoreBlock = 1;
    heaviestBlock = blockHash;
    initBlockHash = blockHash;

    bytes memory initBytes = INIT_CONSENSUS_STATE_BYTES;
    uint32 adjustment = INIT_CHAIN_HEIGHT / DIFFICULTY_ADJUSTMENT_INTERVAL;
    adjustmentHashes[adjustment] = blockHash;
    bytes memory nodeBytes = encode(initBytes, rewardAddr, scoreBlock, INIT_CHAIN_HEIGHT, adjustment, candidateAddr);
    blockChain[blockHash] = nodeBytes;
    rewardForSyncHeader = INIT_REWARD_FOR_SYNC_HEADER;
    callerCompensationMolecule=CALLER_COMPENSATION_MOLECULE;
    roundSize = ROUND_SIZE;
    maxWeight = MAXIMUM_WEIGHT;
    storeBlockGasPrice = INIT_STORE_BLOCK_GAS_PRICE;
    alreadyInit = true;
  }

  /// Store a BTC block in Core blockchain
  /// @dev This method is called by relayers
  /// @param blockBytes BTC block bytes
  function storeBlockHeader(bytes calldata blockBytes) external onlyRelayer {
    require(
      tx.gasprice == (storeBlockGasPrice == 0 ? INIT_STORE_BLOCK_GAS_PRICE : storeBlockGasPrice), 
      "must use limited gasprice");
    bytes memory headerBytes = slice(blockBytes, 0, 80);
    bytes32 blockHash = doubleShaFlip(headerBytes);
    require(submitters[blockHash] == address(0x0), "can't sync duplicated header");

    (uint32 blockHeight, uint256 scoreBlock, int256 errCode) = checkProofOfWork(headerBytes, blockHash);
    if (errCode != 0) {
        emit StoreHeaderFailed(blockHash, errCode);
        return;
    }

    require(blockHeight + 720 > getHeight(heaviestBlock), "can't sync header 5 days ago");

    // verify MerkleRoot & pickup candidate address, reward address and bindingHash.
    uint256 length = blockBytes.length + 32;
    bytes memory input = slice(blockBytes, 0, blockBytes.length);
    bytes32[4] memory result;
    address candidateAddr;
    address rewardAddr;
    bytes32 bindingHash;
    /* solium-disable-next-line */
    assembly {
      // call precompiled contract contracts_lightclient.go 
      // contract address: 0x64
      if iszero(staticcall(not(0), 0x64, input, length, result, 128)) {
        revert(0, 0)
      }
      candidateAddr := mload(add(result, 0))
      rewardAddr := mload(add(result, 0x20))
      bindingHash := mload(add(result, 0x40))
    }

    uint32 adjustment = blockHeight / DIFFICULTY_ADJUSTMENT_INTERVAL;
    // save & update rewards
    blockChain[blockHash] = encode(headerBytes, rewardAddr, scoreBlock, blockHeight, adjustment, candidateAddr);
    submitters[blockHash] = payable(msg.sender);

    collectedRewardForHeaderRelayer += rewardForSyncHeader;
    if (headerRelayersSubmitCount[msg.sender]==0) {
      headerRelayerAddressRecord.push(payable(msg.sender));
    }
    headerRelayersSubmitCount[msg.sender]++;
    if (++countInRound >= roundSize) {
      uint256 callerHeaderReward = distributeRelayerReward();
      relayerRewardVault[msg.sender] += callerHeaderReward;
      countInRound = 0;
    }

    // bindingHash is left for future use
    // BTC miners who add latest Core block hash to their OP_RETURN output 
    // will be incentivized with extra rewards

    // equality allows block with same score to become an (alternate) Tip, so
    // that when an (existing) Tip becomes stale, the chain can continue with
    // the alternate Tip
    if (scoreBlock >= highScore) {
      uint32 prevHeight = blockHeight - 1;
      bytes32 prevHash = getPrevHash(blockHash);
      while(height2HashMap[prevHeight] != prevHash && prevHeight + CONFIRM_BLOCK >= blockHeight) {
        height2HashMap[prevHeight] = prevHash;
        if (prevHeight % DIFFICULTY_ADJUSTMENT_INTERVAL == 0) {
          adjustmentHashes[adjustment] = prevHash;
        }
        --prevHeight;
        prevHash = getPrevHash(prevHash);
      }

      if (blockHeight > getHeight(heaviestBlock)) {
        addMinerPower(blockHash);
      }

      if (blockHeight % DIFFICULTY_ADJUSTMENT_INTERVAL == 0) {
        adjustmentHashes[adjustment] = blockHash;
      }

      heaviestBlock = blockHash;
      highScore = scoreBlock;
      height2HashMap[blockHeight] = blockHash;
    }
    
    emit StoreHeader(blockHash, candidateAddr, rewardAddr, blockHeight, bindingHash);
  }


  function addMinerPower(bytes32 blockHash) internal {
    for(uint256 i = 0; i < CONFIRM_BLOCK; ++i){
      if (blockHash == initBlockHash) return;
      blockHash = getPrevHash(blockHash);
    }

    uint256 blockRoundTag = getTimestamp(blockHash) / SatoshiPlusHelper.ROUND_INTERVAL;
    address candidate = getCandidate(blockHash);
    
    // The mining power with rounds less than or equal to frozenRoundTag has been frozen 
    // and there is no need to continue staking, otherwise it may disrupt the reward 
    // distribution mechanism
    uint256 frozenRoundTag = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag() - POWER_ROUND_GAP;
    if (candidate != address(0) && blockRoundTag > frozenRoundTag) {
      address miner = getRewardAddress(blockHash);
      RoundPower storage r = roundPowerMap[blockRoundTag];
      uint256 power = r.powerMap[candidate].miners.length;
      if (power == 0) {
        r.candidates.push(candidate);
      }
      r.powerMap[candidate].miners.push(miner);
      r.powerMap[candidate].btcBlocks.push(blockHash);
    }
  }

  /// Claim relayer rewards
  /// @param relayerAddr The relayer address
  function claimRelayerReward(address relayerAddr) external onlyInit {
     uint256 reward = relayerRewardVault[relayerAddr];
     require(reward != 0, "no relayer reward");
     relayerRewardVault[relayerAddr] = 0;
     address payable recipient = payable(relayerAddr);
     ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(recipient, reward);
  }

  /// Distribute relayer rewards
  /// @dev This method is triggered once per round, the default round value is set to 100 (BTC blocks)
  /// @dev And the weight of each relayer is calculated based on the `calculateRelayerWeight` method
  /// @return The reward for the caller of this method
  function distributeRelayerReward() internal returns (uint256) {
    uint256 totalReward = collectedRewardForHeaderRelayer;

    uint256 totalWeight=0;
    address payable[] memory relayers = headerRelayerAddressRecord;
    uint256 relayerSize = relayers.length;
    uint256[] memory relayerWeight = new uint256[](relayerSize);
    for (uint256 index = 0; index < relayerSize; index++) {
      address relayer = relayers[index];
      uint256 weight = calculateRelayerWeight(headerRelayersSubmitCount[relayer]);
      relayerWeight[index] = weight;
      totalWeight += weight;
    }

    uint256 callerReward = totalReward * callerCompensationMolecule / 10000;
    totalReward -= callerReward;
    uint256 remainReward = totalReward;
    for (uint256 index = 1; index < relayerSize; index++) {
      uint256 reward = relayerWeight[index] * totalReward / totalWeight;
      relayerRewardVault[relayers[index]] += reward;
      remainReward -= reward;
    }
    relayerRewardVault[relayers[0]] += remainReward;

    collectedRewardForHeaderRelayer = 0;
    for (uint256 index = 0; index < relayerSize; index++) {
      delete headerRelayersSubmitCount[relayers[index]];
    }
    delete headerRelayerAddressRecord;
    return callerReward;
  }

  /// Calculate relayer weight based number of BTC blocks relayed
  /// @param count The number of BTC blocks relayed by a specific validator
  /// @return The relayer weight
  function calculateRelayerWeight(uint256 count) public view returns(uint256) {
    if (count <= maxWeight) {
      return count;
    } else if (maxWeight < count && count <= 2*maxWeight) {
      return maxWeight;
    } else if (2*maxWeight < count && count <= (2*maxWeight + 3*maxWeight/4)) {
      return 3*maxWeight - count;
    } else {
      return count/4;
    }
  }

  /// Checks if a tx is included and confirmed on Bitcoin
  /// @dev Checks if the block is confirmed, and Merkle proof is valid
  /// @param txid Desired tx Id in LE form
  /// @param blockHeight of the desired tx
  /// @param confirmBlock of the tx confirmation
  /// @param nodes Part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index of the tx in Merkle tree
  /// @return True if the provided tx is confirmed on Bitcoin
  function checkTxProof(bytes32 txid, uint32 blockHeight, uint32 confirmBlock, bytes32[] calldata nodes, uint256 index) public view override returns (bool) {
    bytes32 blockHash = height2HashMap[blockHeight];
    
    if (blockHeight + confirmBlock > getChainTipHeight() || txid == bytes32(0) || blockHash == bytes32(0)) {
      return false;
    }

    bytes32 root = bytes32(loadInt256(68, blockChain[blockHash]));
    if (nodes.length == 0) {
      return (txid == root);
    }

    bytes32 current = txid;
    for (uint256 i = 0; i < nodes.length; i++) {
      if (index % 2 == 1) {
        current = merkleStep(nodes[i], current);
      } else {
        current = merkleStep(current, nodes[i]);
      }
      index >>= 1;
    }
    return (current == root);
  }

  function checkTxProofAndGetTime(bytes32 txid, uint32 blockHeight, uint32 confirmBlock, bytes32[] calldata nodes, uint256 index) external view override returns (bool, uint64) {
    bool r = checkTxProof(txid, blockHeight, confirmBlock, nodes, index);
    
    if (r) {
      bytes32 blockHash = height2HashMap[blockHeight];
      uint64 timestamp = getTimestamp(blockHash);
      return (r, timestamp);
    }
    return (r, 0);
  }

  function merkleStep(bytes32 l, bytes32 r) private view returns (bytes32 digest) {
    assembly {
      // solium-disable-previous-line security/no-inline-assembly
      let ptr := mload(0x40)
      mstore(ptr, l)
      mstore(add(ptr, 0x20), r)
      pop(staticcall(gas(), 2, ptr, 0x40, ptr, 0x20)) // sha256 #1
      pop(staticcall(gas(), 2, ptr, 0x20, ptr, 0x20)) // sha256 #2
      digest := mload(ptr)
    }
  }
  
  function slice(bytes memory input, uint256 start, uint256 end) internal pure returns (bytes memory _output) {
    uint256 length = end - start;
    _output = new bytes(length);
    uint256 src = Memory.dataPtr(input);
    uint256 dest;
    assembly {
      dest := add(add(_output, 0x20), start)
    }
    Memory.copy(src, dest, length);
    return _output;
  }

  function encode(bytes memory headerBytes, address rewardAddr, uint256 scoreBlock,
      uint32 blockHeight, uint32 adjustment, address candidateAddr) internal pure returns (bytes memory nodeBytes) {
    nodeBytes = new bytes(160);
    // keep 4 reserved bytes in `rewardAddrValue` field
    uint256 rewardAddrValue = uint256(uint160(rewardAddr)) << 64;
    uint256 v = (scoreBlock << (128)) + (uint256(blockHeight) << (96)) + (uint256(adjustment) << 64);
    uint256 candidateValue = uint256(uint160(candidateAddr)) << 96;

    assembly {
        // copy header
        let mc := add(nodeBytes, 0x20)
        let end := add(mc, 80)
        for {
        // The multiplication in the next line has the same exact purpose
        // as the one above.
            let cc := add(headerBytes, 0x20)
        } lt(mc, end) {
            mc := add(mc, 0x20)
            cc := add(cc, 0x20)
        } {
            mstore(mc, mload(cc))
        }
        // copy rewardAddr
        mc := add(end, 0)
        mstore(mc, rewardAddrValue)
        // store score, height, adjustment index
        mc := add(mc, 24)
        mstore(mc, v)
        // store candidate
        mc := add(mc, 24)
        mstore(mc, candidateValue)
    }
    return nodeBytes;
  }

  // Check Proof of Work of a relayed BTC block
  function checkProofOfWork(bytes memory headerBytes, bytes32 blockHash) internal view returns (
      uint32 blockHeight, uint256 scoreBlock, int256 errCode) {
    bytes32 hashPrevBlock = flip32Bytes(bytes32(loadInt256(36, headerBytes))); // 4 is offset for hashPrevBlock
    
    uint256 scorePrevBlock = getScore(hashPrevBlock);
    if (scorePrevBlock == 0) {
        return (blockHeight, scoreBlock, ERR_NO_PREV_BLOCK);
    }
    scoreBlock = getScore(blockHash);
    if (scoreBlock != 0) {
        // block already stored/exists
        return (blockHeight, scoreBlock, ERR_BLOCK_ALREADY_EXISTS);
    }
    uint32 bits = flip4Bytes(uint32(loadInt256(104, headerBytes) >> 224)); // 72 is offset for 'bits'
    uint256 target = targetFromBits(bits);

    // Check proof of work matches claimed amount
    // we do not do other validation (eg timestamp) to save gas
    if (blockHash == 0 || uint256(blockHash) > target) {
      return (blockHeight, scoreBlock, ERR_PROOF_OF_WORK);
    }
    blockHeight = 1 + getHeight(hashPrevBlock);
    uint32 prevBits = getBits(hashPrevBlock);
    if (blockHeight % DIFFICULTY_ADJUSTMENT_INTERVAL != 0) {
      // since blockHeight is 1 more than blockNumber; OR clause is special case for 1st header
      /* we need to check prevBits isn't 0 otherwise the 1st header
       * will always be rejected (since prevBits doesn't exist for the initial parent)
       * This allows blocks with arbitrary difficulty from being added to
       * the initial parent, but as these forks will have lower score than
       * the main chain, they will not have impact.
       */
      if (bits != prevBits && prevBits != 0) {
        return (blockHeight, scoreBlock, ERR_DIFFICULTY);
      }
    } else {
      uint256 prevTarget = targetFromBits(prevBits);
      uint64 prevTime = getTimestamp(hashPrevBlock);

      // (blockHeight - DIFFICULTY_ADJUSTMENT_INTERVAL) is same as [getHeight(hashPrevBlock) - (DIFFICULTY_ADJUSTMENT_INTERVAL - 1)]
      bytes32 startBlock = getAdjustmentHash(hashPrevBlock);
      uint64 startTime = getTimestamp(startBlock);

      // compute new bits
      uint64 actualTimespan = prevTime - startTime;
      if (actualTimespan < TARGET_TIMESPAN_DIV_4) {
          actualTimespan = TARGET_TIMESPAN_DIV_4;
      }
      if (actualTimespan > TARGET_TIMESPAN_MUL_4) {
          actualTimespan = TARGET_TIMESPAN_MUL_4;
      }
      uint256 newTarget;
      assembly{
        newTarget := div(mul(actualTimespan, prevTarget), TARGET_TIMESPAN)
      }
      uint32 newBits = toCompactBits(newTarget);
      if (bits != newBits && newBits != 0) { // newBits != 0 to allow first header
        return (blockHeight, scoreBlock, ERR_RETARGET);
      }
    }
    
    // # https://en.bitcoin.it/wiki/Difficulty
    uint256 blockDifficulty = 0x00000000FFFF0000000000000000000000000000000000000000000000000000 / target;
    scoreBlock = scorePrevBlock + blockDifficulty;
    return (blockHeight, scoreBlock, 0);
  } 

  // reverse 32 bytes given by value
  function flip32Bytes(bytes32 input) internal pure returns (bytes32 v) {
    v = input;

    // swap bytes
    v = ((v & 0xFF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00) >> 8) |
        ((v & 0x00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF00FF) << 8);

    // swap 2-byte long pairs
    v = ((v & 0xFFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000) >> 16) |
        ((v & 0x0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF) << 16);

    // swap 4-byte long pairs
    v = ((v & 0xFFFFFFFF00000000FFFFFFFF00000000FFFFFFFF00000000FFFFFFFF00000000) >> 32) |
        ((v & 0x00000000FFFFFFFF00000000FFFFFFFF00000000FFFFFFFF00000000FFFFFFFF) << 32);

    // swap 8-byte long pairs
    v = ((v & 0xFFFFFFFFFFFFFFFF0000000000000000FFFFFFFFFFFFFFFF0000000000000000) >> 64) |
        ((v & 0x0000000000000000FFFFFFFFFFFFFFFF0000000000000000FFFFFFFFFFFFFFFF) << 64);

    // swap 16-byte long pairs
    v = (v >> 128) | (v << 128);
  }
  
  // reverse 4 bytes given by value
  function flip4Bytes(uint32 input) internal pure returns (uint32 v) {
    v = input;

    // swap bytes
    v = ((v & 0xFF00FF00) >> 8) | ((v & 0x00FF00FF) << 8);

    // swap 2-byte long pairs
    v = (v >> 16) | (v << 16);
  }
  
  // Bitcoin-way of hashing
  function doubleShaFlip(bytes memory dataBytes) internal pure returns (bytes32) {
    return flip32Bytes(sha256(abi.encodePacked(sha256(dataBytes))));
  }
  
  // get the 'timestamp' field from a Bitcoin blockheader
  function getTimestamp(bytes32 hash) public view returns (uint64) {
    return flip4Bytes(uint32(loadInt256(100, blockChain[hash])>>224));
  }
  
  // get the 'bits' field from a Bitcoin blockheader
  function getBits(bytes32 hash) public view returns (uint32) {
    return flip4Bytes(uint32(loadInt256(104, blockChain[hash])>>224));
  }

  function getPrevHash(bytes32 hash) public view returns (bytes32) {
    return flip32Bytes(bytes32(loadInt256(36, blockChain[hash])));
  }

  function getMerkleRoot(bytes32 hash) public view returns (bytes32) {
    return flip32Bytes(bytes32(loadInt256(68, blockChain[hash])));
  }

  function getCandidate(bytes32 hash) public view returns (address) {
    return address(uint160(loadInt256(160, blockChain[hash]) >> 96));
  }

  function getRewardAddress(bytes32 hash) public view returns (address) {
    return address(uint160(loadInt256(116, blockChain[hash]) >> 96));
  }
  
  // Get the score of block
  function getScore(bytes32 hash) public view returns (uint256) {
    return (loadInt256(136, blockChain[hash]) >> 128);
  }

  function getHeight(bytes32 hash) public view returns (uint32) {
    return uint32(loadInt256(152, blockChain[hash]) >> 224);
  }
  
  function getAdjustmentIndex(bytes32 hash) public view returns (uint32) {
    return uint32(loadInt256(156, blockChain[hash]) >> 224);
  }
  
  function getAdjustmentHash(bytes32 hash) public view returns (bytes32) {
    uint32 index = uint32(loadInt256(156, blockChain[hash]) >> 224);
    return adjustmentHashes[index];
  }

  function getChainTipHeight() public view returns (uint32) {
    return getHeight(heaviestBlock);
  }

  // Bitcoin-way of computing the target from the 'bits' field of a blockheader
  // based on http://www.righto.com/2014/02/bitcoin-mining-hard-way-algorithms.html#ref3
  function targetFromBits(uint32 bits) internal pure returns (uint256 target) {
    uint32 nSize = bits >> 24;
    uint32 nWord = bits & 0x00ffffff;
    if (nSize <= 3) {
        nWord >>= 8 * (3 - nSize);
        target = nWord;
    } else {
        target = nWord;
        target <<= 8 * (nSize - 3);
    }

    return (target);
  }

  // Convert uint256 to compact encoding
  // based on https://github.com/petertodd/python-bitcoinlib/blob/2a5dda45b557515fb12a0a18e5dd48d2f5cd13c2/bitcoin/core/serialize.py
  function toCompactBits(uint256 val) internal pure returns (uint32) {
    // calc bit length of val
    uint32 length = 0;
    uint256 int_value = val;
    while (int_value != 0) {
        int_value >>= 1;
        length ++;
    }
    uint32 nbytes = (length + 7) >> 3;
    uint32 compact = 0;
    if (nbytes <= 3) {
        compact = uint32(val & 0xFFFFFF) << (8 * (3 - nbytes));
    } else {
        compact = uint32(val >> (8 * (nbytes - 3)));
        compact = compact & 0xFFFFFF;
    }

    // If the sign bit (0x00800000) is set, divide the mantissa by 256 and
    // increase the exponent to get an encoding without it set.
    if ((compact & 0x00800000) != 0) {
        compact = compact >> 8;
        nbytes ++;
    }
    return (compact | (nbytes << 24));
  }

  function loadInt256(uint256 _offst, bytes memory _input) internal pure returns (uint256 _output) {
    assembly {
        _output := mload(add(_input, _offst))
    }
  }

  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov{
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key,"rewardForSyncHeader")) {
      uint256 newRewardForSyncHeader = BytesToTypes.bytesToUint256(32, value);
      if (newRewardForSyncHeader == 0 || newRewardForSyncHeader > 1e20) {
        revert OutOfBounds(key, newRewardForSyncHeader, 1, 1e20);
      }
      rewardForSyncHeader = newRewardForSyncHeader;
    } else if (Memory.compareStrings(key,"callerCompensationMolecule")) {
      uint256 newCallerCompensationMolecule = BytesToTypes.bytesToUint256(32, value);
      if (newCallerCompensationMolecule > 10000) {
        revert OutOfBounds(key, newCallerCompensationMolecule, 0, 10000);
      }
      callerCompensationMolecule = newCallerCompensationMolecule;
    } else if (Memory.compareStrings(key,"roundSize")) {
      uint256 newRoundSize = BytesToTypes.bytesToUint256(32, value);
      if (newRoundSize < maxWeight) {
        revert OutOfBounds(key, newRoundSize, maxWeight, type(uint256).max);
      }
      roundSize = newRoundSize;
    } else if (Memory.compareStrings(key,"maxWeight")) {
      uint256 newMaxWeight = BytesToTypes.bytesToUint256(32, value);
      if (newMaxWeight == 0 || newMaxWeight > roundSize) {
        revert OutOfBounds(key, newMaxWeight, 1, roundSize);
      }
      maxWeight = newMaxWeight;
    } else if (Memory.compareStrings(key,"storeBlockGasPrice")) {
      uint256 newStoreBlockGasPrice = BytesToTypes.bytesToUint256(32, value);
      if (newStoreBlockGasPrice < 1e9) {
        revert OutOfBounds(key, newStoreBlockGasPrice, 1e9, type(uint256).max);
      }
      storeBlockGasPrice = newStoreBlockGasPrice;
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }

  /// Whether the input BTC block is already stored in Core blockchain
  /// @param btcHash The BTC block hash
  /// @return true/false
  function isHeaderSynced(bytes32 btcHash) external view returns (bool) {
    return getHeight(btcHash) >= INIT_CHAIN_HEIGHT;
  }

  /// Get the submitter/relayer of a specific BTC block
  /// @param btcHash The BTC block hash
  /// @return The address submitted the BTC block
  function getSubmitter(bytes32 btcHash) external view returns (address payable) {
    return submitters[btcHash];
  }

  /// Get the heaviest BTC block
  /// @return The BTC block hash
  function getChainTip() external view returns (bytes32) {
    return heaviestBlock;
  }

  /// Get powers of given candidates (number of BTC blocks delegated to candidates) in a specific round
  /// @param roundTimeTag The specific round time
  /// @param candidates The given candidates to get their powers
  /// @return powers The corresponding powers of given candidates
  function getRoundPowers(uint256 roundTimeTag, address[] calldata candidates) external override view returns (uint256[] memory powers, uint256 totalPower) {
    uint256 count = candidates.length;
    powers = new uint256[](count);

    RoundPower storage r = roundPowerMap[roundTimeTag];
    for (uint256 i = 0; i < count; ++i){
      powers[i] = r.powerMap[candidates[i]].miners.length;
      totalPower += powers[i];
    }
    return (powers, totalPower);
  }

  /// Get miners (in the form of reward addresses) who delegated to a given candidate in a specific round
  /// @param roundTimeTag The specific round time
  /// @param candidate The given candidate to get its miners
  /// @return miners The miners who delegated to the candidate in the round
  function getRoundMiners(uint256 roundTimeTag, address candidate) external override view returns (address[] memory miners) {
    return roundPowerMap[roundTimeTag].powerMap[candidate].miners;
  }

  /// Get BTC blocks delegated to a given candidate in a specific round
  /// @param roundTimeTag The specific round time
  /// @param candidate The given candidate to get its blocks
  /// @return blocks The blocks delegated to the candidate in the round
  function getRoundBlocks(uint256 roundTimeTag, address candidate) external view returns (bytes32[] memory blocks) {
    return roundPowerMap[roundTimeTag].powerMap[candidate].btcBlocks;
  }

  /// Get candidates of a specific round
  /// @param roundTimeTag The specific round time
  /// @return candidates The valid candidates in the round
  function getRoundCandidates(uint256 roundTimeTag) external override view returns (address[] memory candidates) {
    return roundPowerMap[roundTimeTag].candidates;
  }
  
  
}
