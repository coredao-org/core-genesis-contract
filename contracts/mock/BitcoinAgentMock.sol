pragma solidity 0.8.4;

import "../BitcoinAgent.sol";

contract BitcoinAgentMock is BitcoinAgent {

    function setCandidateMap(address agent, uint256 value, uint256 value1) external {
        candidateMap[agent] = StakeAmount(value, value1);
    }

}
