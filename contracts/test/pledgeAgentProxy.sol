pragma solidity 0.8.4;

contract PledgeAgentProxy {
    address public pledgeAgent;
    address public stakeHub;
    bool public  receiveState;

    event delegate(bool success);
    event claim(uint256 liabilityAmount, bool allClaimed, address delegator, uint256 [] rewards);
    constructor(address pledgeAgentAddress, address stakeHubAddress) public {
        pledgeAgent = pledgeAgentAddress;
        stakeHub = stakeHubAddress;
    }
    function delegateCoin(address agent) external payable {
        bytes memory payload = abi.encodeWithSignature("delegateCoin(address)", agent);
        (bool success, bytes memory returnData) = pledgeAgent.call{value: msg.value}(payload);
        emit delegate(success);
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
