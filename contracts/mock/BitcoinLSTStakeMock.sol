pragma solidity 0.8.4;

import "../BitcoinAgent.sol";
import {BitcoinLSTStake} from "../BitcoinLSTStake.sol";

contract BitcoinLSTStakeMock is BitcoinLSTStake {

    function developmentInit() external {
        utxoFee = INIT_UTXO_FEE / 100;
    }


    function setInitRound(uint256 value) external {
        initRound = value;
    }

    function setWallet(bytes memory pkscript) external {
        _addWallet(pkscript);
    }

    function setRoundTag(uint256 value) external {
        roundTag = value;
    }

    function setBtcLstRewardMap(address delegator, uint256 reward, uint256 accStakedAmount) external {
        rewardMap[delegator] = Reward(reward, accStakedAmount);
    }

 

    function setUtxoFee(uint64 value) external {
        utxoFee = value;
    }

    function setStakedAmount(uint64 value) external {
        stakedAmount = value;
    }
    
    function setRealtimeAmount(uint64 value) external {
        realtimeAmount = value;
    }

    function getRedeemMap(bytes32 value) external view returns (uint256) {
        return redeemMap[value];
    }

    function getWalletMap(bytes32 value) external view returns (uint256) {
        return walletMap[value];
    }


    function getAccuredRewardPerBTCMap(uint256 round) external view returns (uint256) {
        uint256 reward = accuredRewardPerBTCMap[round];
        return reward;
    }

    function setAccuredRewardPerBTCMap(uint256 round, uint256 value) external {
        accuredRewardPerBTCMap[round] = value;
    }


    function getRedeemRequestsLength() external view returns (uint) {
        return redeemRequests.length;
    }

}
