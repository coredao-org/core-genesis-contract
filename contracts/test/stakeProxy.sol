pragma solidity 0.8.4;

contract delegateCoinProxy {
    address public pledgeAgent;
    address public stakeHub;
    bool public  receiveState;

    event delegate(bool success);
    event claim(bool allClaimed, address delegator, uint256 [] rewards);
    constructor(address pledgeAgentAddress, address stakeHubAddress) public {
        pledgeAgent = pledgeAgentAddress;
        stakeHub = stakeHubAddress;
    }
    function delegateCoin(address agent) external payable {
        bytes memory payload = abi.encodeWithSignature("delegateCoin(address)", agent);
        (bool success, bytes memory returnData) = pledgeAgent.call{value: msg.value}(payload);
        emit delegate(success);
    }

    function claimReward() external {
        bytes memory payload = abi.encodeWithSignature("claimReward()");
        (bool success, bytes memory returnData) = stakeHub.call(payload);
        require(success, "call to claimReward failed");
        (uint256[] memory rewards) = abi.decode(returnData, (uint256 []));
        emit claim(success, msg.sender, rewards);
    }

    function setReceiveState(bool state) external {
        receiveState = state;
    }

    receive() external payable {
        if (receiveState == false) {
            revert("refused");
        }
    }
}


contract delegateBtcLstProxy {
    address public stakeHub;
    address public btcLstStake;
    address public btcLstToken;
    bool public  receiveState;

    event delegateBtcLstSuccess(bool success);
    event redeemBtcLstSuccess(bool success);
    event transferBtcLstSuccess(bool success);
    event claim(uint256 liabilityAmount, bool allClaimed, address delegator, uint256 [] rewards);
    constructor(address btcLstStakeAddress, address stakeHubAddress, address btcLstTokenAddress) public {
        btcLstStake = btcLstStakeAddress;
        stakeHub = stakeHubAddress;
        btcLstToken = btcLstTokenAddress;
    }
    function delegateBtcLst(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index, bytes memory script) external {
        bytes memory payload = abi.encodeWithSignature("delegate(bytes,uint32,bytes32[],uint256,bytes)", btcTx, blockHeight, nodes, index, script);
        (bool success, bytes memory returnData) = btcLstStake.call(payload);
        emit delegateBtcLstSuccess(success);
    }

    function redeemBtcLst(uint64 amount, bytes calldata pkscript) external {
        bytes memory payload = abi.encodeWithSignature("redeem(uint64,bytes)", amount, pkscript);
        (bool success, bytes memory returnData) = btcLstStake.call(payload);
        emit redeemBtcLstSuccess(success);
    }

    function transferBtcLst(address to, uint256 amount) external {
        bytes memory payload = abi.encodeWithSignature("transfer(address,uint256)", to, amount);
        (bool success, bytes memory returnData) = btcLstToken.call(payload);
        emit transferBtcLstSuccess(success);
    }


    function claimReward() external returns (uint256) {
        bytes memory payload = abi.encodeWithSignature("claimReward()");
        (bool success, bytes memory returnData) = stakeHub.call(payload);
        require(success, "call to claimReward failed");
        (uint256[] memory rewards,uint256 liabilityAmount) = abi.decode(returnData, (uint256 [], uint256));
        emit claim(liabilityAmount, success, msg.sender, rewards);
        return liabilityAmount;
    }

    function setReceiveState(bool state) external {
        receiveState = state;
    }

    receive() external payable {
        if (receiveState == false) {
            revert("refused");
        }
    }
}