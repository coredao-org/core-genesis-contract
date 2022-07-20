pragma solidity ^0.6.4;
pragma experimental ABIEncoderV2;
import "../BtcLightClient.sol";

contract BtcLightClientMock is BtcLightClient {
    uint32 _blockHeight;

    constructor() BtcLightClient() public {
        _blockHeight = INIT_CHAIN_HEIGHT;
    }

    function developmentInit() external {
        rewardForSyncHeader = rewardForSyncHeader / 1e16;
    }

    function setBlock(bytes32 hash, bytes20 coinbase) public {
        _blockHeight = _blockHeight + 1;
        bytes memory headerBytes = new bytes(80);
        blockChain[hash] = encode(headerBytes, coinbase, 1000, _blockHeight, 11);
    }

    function resetMiners(uint roundTimeTag) public {
        delete roundMinerPowerMap[roundTimeTag];
    }

    function setMiners(uint roundTimeTag, bytes20[] memory miners) public {
        RoundMinersPower storage rp = roundMinerPowerMap[roundTimeTag];
        uint i;
        for (i=0; i < miners.length; i++) {
            if (i < rp.miners.length) {
                rp.miners[i] = miners[i];
            } else {
                rp.miners.push(miners[i]);
            }
        }
        while (rp.miners.length > miners.length) {
          rp.miners.pop();
        }
    }

    function setMinerCount(uint roundTimeTag, bytes20 miner, uint count) public {
        roundMinerPowerMap[roundTimeTag].powerMap[miner] = count;
    }

    function addMiner(uint roundTimeTag, bytes20 miner, uint count) external {
        RoundMinersPower storage rp = roundMinerPowerMap[roundTimeTag];
        uint i;
        for (i=0; i<rp.miners.length; i++) {
            if (rp.miners[i] == miner) {
                break;
            }
        }
        if (i == rp.miners.length) {
            rp.miners.push(miner);
        }
        rp.powerMap[miner] = count;
    }

    function getMinerPower(uint roundTimeTag, bytes20 miner) external view returns(uint) {
        return roundMinerPowerMap[roundTimeTag].powerMap[miner];
    }

    function batchSetMiners(uint[] calldata roundTimeTags, bytes20[][] calldata miners, uint[][] calldata counts) external {
        uint i;
        for (i=0; i<roundTimeTags.length; i++) {
            RoundMinersPower storage rp = roundMinerPowerMap[roundTimeTags[i]];
            uint j;
            for (j=0; j < miners[i].length; j++) {
                uint k;
                for (k=0; k<rp.miners.length;k++) {
                    if (rp.miners[k] == miners[i][j]) {
                        break;
                    }
                }
                if (k == rp.miners.length) {
                    rp.miners.push(miners[i][j]);
                }
                rp.powerMap[miners[i][j]] = counts[i][j];
            }
        }
    }
}
