pragma solidity 0.8.4;

contract PledgeAgentProxy {
    address pledgeAgent;
    bool public  receiveState;

    event delegate(bool success);
    event claim(uint256 reward, bool allClaimed);
    constructor(address pledgeAgentAddress) {
        pledgeAgent = pledgeAgentAddress;
    }

    function delegateCoin(address agent) external payable {
        bytes memory payload = abi.encodeWithSignature("delegateCoin(address)", agent);
        (bool success, bytes memory returnData) = pledgeAgent.call{value: msg.value}(payload);
        (returnData);
        emit delegate(success);
    }

    function claimReward(address[] calldata agentList) external returns(uint256) {
        bytes4 funcSelector = bytes4(keccak256("claimReward(address[])"));
        (funcSelector);
        bytes memory payload = abi.encodeWithSignature("claimReward(address[])", agentList);
        (bool success, bytes memory returnData) = pledgeAgent.call(payload);
        require(success, "call to claimReward failed");
        (uint256 rewardSum, bool allClaimed) = abi.decode(returnData, (uint256, bool));
        emit claim(rewardSum, allClaimed);
        return rewardSum;
    }

    function setReceiveState(bool state) external {
        receiveState = state;
    }
    receive() external payable {
        if (receiveState == false){
            revert("refused");
        }
    }
}
