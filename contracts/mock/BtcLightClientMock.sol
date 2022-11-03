pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;
import "../BtcLightClient.sol";
import "../lib/BytesLib.sol";

contract BtcLightClientMock is BtcLightClient {
    using BytesLib for bytes;
    uint32 public _blockHeight;
    uint256 public constant mockScore = 24371874614346;
    uint32 public constant mockAdjustment = 11;

    constructor() BtcLightClient() public {
        _blockHeight = INIT_CHAIN_HEIGHT;
    }

    function developmentInit() external {
        rewardForSyncHeader = rewardForSyncHeader / 1e16;
    }

    function setBlock(bytes32 hash, bytes32 prevHash, address rewardAddr, address candidateAddr) public {
        _blockHeight = _blockHeight + 1;
        bytes memory headerBytes = new bytes(4);
        headerBytes = headerBytes.concat(abi.encodePacked(prevHash));
        blockChain[hash] = encode(
            headerBytes.concat(new bytes(44)), rewardAddr, mockScore, _blockHeight, mockAdjustment, candidateAddr);
    }

    function setCandidates(uint roundTimeTag, address[] memory candidates) public {
        delete roundPowerMap[roundTimeTag];
        uint i;
        for (i=0; i< candidates.length; i++) {
            roundPowerMap[roundTimeTag].candidates.push(candidates[i]);
        }
    }

    function setMiners(uint roundTimeTag, address candidate, address[] memory rewardAddrs) public {
        RoundPower storage r = roundPowerMap[roundTimeTag];
        bool exist;
        for(uint i=0; i<r.candidates.length; i++) {
            if (r.candidates[i] == candidate) {
                exist = true;
                break;
            }
        }
        if (exist == false) {
            r.candidates.push(candidate);
        }
        delete r.powerMap[candidate];
        uint i;
        for (i=0; i<rewardAddrs.length; i++) {
            r.powerMap[candidate].miners.push(rewardAddrs[i]);
            r.powerMap[candidate].btcBlocks.push(bytes32(0));
        }
    }

    function addMinerPowerMock(bytes32 blockHash) external {
        addMinerPower(blockHash);
    }
}
