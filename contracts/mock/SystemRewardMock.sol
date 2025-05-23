pragma solidity 0.8.4;

import "../SystemReward.sol";

contract SystemRewardMock is SystemReward {
    function setOperator(address operator) public {
        operators[operator] = true;
        numOperator++;
    }

    function getWhiteListSet(uint256 index) external view returns (WhiteList memory) {
        return whiteListSet[index];
    }

    function getWhiteListSetLength() external view returns (uint256) {
        return whiteListSet.length;
    }


}
