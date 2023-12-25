// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;
import "../BtcLightClient.sol";
import "../lib/BytesLib.sol";
import {BaseMock} from "./BaseMock.sol";

contract BtcLightClientMock is BtcLightClient, BaseMock {
    using BytesLib for bytes;
    uint32 public mockBlockHeight;
    uint256 public constant MOCK_SCORE = 24371874614346;
    uint32 public constant MOCK_ADJUSTMENT = 11;
    uint32 public constant MOCK_INIT_CHAIN_HEIGHT = 717696;
    bytes private constant MOCK_INIT_CONSENSUS_STATE_BYTES = hex"000040209acaa5d26d392ace656c2428c991b0a3d3d773845a1300000000000000000000aa8e225b1f3ea6c4b7afd5aa1cecf691a8beaa7fa1e579ce240e4a62b5ac8ecc2141d9618b8c0b170d5c05bb";

    constructor() BtcLightClient() {
        mockBlockHeight = MOCK_INIT_CHAIN_HEIGHT;
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
        for (uint i=0; i< candidates.length; i++) {
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
        for (uint i=0; i<rewardAddrs.length; i++) {
            r.powerMap[candidate].miners.push(rewardAddrs[i]);
            r.powerMap[candidate].btcBlocks.push(bytes32(0));
        }
    }

    function _initChainHeight() internal override pure returns (uint32) {
        return MOCK_INIT_CHAIN_HEIGHT;
    }

    function _initConsensusState() internal override pure returns (bytes memory){
        return MOCK_INIT_CONSENSUS_STATE_BYTES;
    }

    function addMinerPowerMock(bytes32 blockHash) external {
        addMinerPower(blockHash);
    }

    function _isBlockProducer() internal override pure returns (bool) {
        return true;
    }

    function _zeroGasPrice() internal override pure returns (bool) {
        return true;
    }


    // -- address mock overrides --

    function _validatorSet() view internal override returns (address) {
        return _notNull(s_validatorSet);
    }

    function _slash() view internal override returns (address) {
        return _notNull(s_slash);
    }

    function _systemReward() view internal override returns (address) {
        return _notNull(s_systemReward);   
    }

    function _lightClient() view internal override returns (address) {
        return _notNull(s_lightClient); 
    }

    function _relayerHub() view internal override returns (address) {
        return _notNull(s_relayerHub);  
    }

    function _candidateHub() view internal override returns (address) {
        return _notNull(s_candidateHub);  
    }

    function _govHub() view internal override returns (address) {
        return _notNull(s_govHub);
    }

    function _pledgeAgent() view internal override returns (address) {
        return _notNull(s_pledgeAgent);  
    }

    function _burn() view internal override returns (address) {
        return _notNull(s_burn);  
    }

    function _foundation() view internal override returns (address) {
        return _notNull(s_foundation);  
    }    
}

