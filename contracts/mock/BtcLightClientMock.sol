pragma solidity 0.8.4;

import "../BtcLightClient.sol";
import "../lib/BytesLib.sol";

contract BtcLightClientMock is BtcLightClient {
    using BytesLib for bytes;
    uint32 public mockBlockHeight;
    uint256 public constant MOCK_SCORE = 24371874614346;
    uint32 public constant MOCK_ADJUSTMENT = 11;

    constructor() BtcLightClient() {
        mockBlockHeight = INIT_CHAIN_HEIGHT;
    }

    function developmentInit() external {
        rewardForSyncHeader = rewardForSyncHeader / 1e16;
    }

    function setBlock(bytes32 hash, bytes32 prevHash, address rewardAddr, address candidateAddr) public {
        mockBlockHeight = mockBlockHeight + 1;
        bytes memory headerBytes = new bytes(4);
        headerBytes = headerBytes.concat(abi.encodePacked(prevHash));
        blockChain[hash] = encode(
            headerBytes.concat(new bytes(44)), rewardAddr, MOCK_SCORE, mockBlockHeight, MOCK_ADJUSTMENT, candidateAddr);
    }

    function setCandidates(uint roundTimeTag, address[] memory candidates) public {
        delete roundPowerMap[roundTimeTag];
        for (uint i = 0; i < candidates.length; i++) {
            roundPowerMap[roundTimeTag].candidates.push(candidates[i]);
        }
    }

    function setCheckResult(bool value, uint64 value1) public {
        checkResult = value;
        timesTamp = value1;
    }

    function setMiners(uint roundTimeTag, address candidate, address[] memory rewardAddrs) public {
        RoundPower storage r = roundPowerMap[roundTimeTag];
        bool exist;
        for (uint i = 0; i < r.candidates.length; i++) {
            if (r.candidates[i] == candidate) {
                exist = true;
                break;
            }
        }
        if (exist == false) {
            r.candidates.push(candidate);
        }
        delete r.powerMap[candidate];
        for (uint i = 0; i < rewardAddrs.length; i++) {
            r.powerMap[candidate].miners.push(rewardAddrs[i]);
            r.powerMap[candidate].btcBlocks.push(bytes32(0));
        }
    }

    function addMinerPowerMock(bytes32 blockHash) external {
        addMinerPower(blockHash);
    }
    /// Get powers of given candidates (number of BTC blocks delegated to candidates) in a specific round
    /// @param roundTimeTag The specific round time
    /// @param candidates The given candidates to get their powers
    /// @return powers The corresponding powers of given candidates
    function getRoundPowersMock(uint256 roundTimeTag, address[] calldata candidates) external view returns (uint256[] memory powers) {
        uint256 count = candidates.length;
        powers = new uint256[](count);

        RoundPower storage r = roundPowerMap[roundTimeTag];
        for (uint256 i = 0; i < count; ++i) {
            powers[i] = r.powerMap[candidates[i]].miners.length;
        }
        return powers;
    }
}
