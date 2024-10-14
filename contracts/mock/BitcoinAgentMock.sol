pragma solidity 0.8.4;

import "../BitcoinAgent.sol";

contract BitcoinAgentMock is BitcoinAgent {

    function setCandidateMap(address agent, uint256 value, uint256 value1) external {
        candidateMap[agent] = StakeAmount(value, value1);
    }
    function setPercentage(uint256 value) external {
        lstGradePercentage = value;
    }

    function setInitLpRates(uint32 value1, uint32 value01, uint32 value2, uint32 value02, uint32 value3, uint32 value03, uint32 value4, uint32 value04) external {
        while (grades.length > 0) {
            grades.pop();
        }
        grades.push(DualStakingGrade(value1, value01));
        grades.push(DualStakingGrade(value2, value02));
        grades.push(DualStakingGrade(value3, value03));
        grades.push(DualStakingGrade(value4, value04));
    }

    function setLpRates(uint32 value1, uint32 balue01) external {
        grades.push(DualStakingGrade(value1, balue01));
    }

    function setAssetWeight(uint256 value) external {
        assetWeight = value;
    }
    
    function getGradesLength() external view returns (uint256) {
        return grades.length;
    }

    function popLpRates() external {
        delete grades;
    }
    
    function setIsActive(bool value) external {
        gradeActive = value;
    }


}
