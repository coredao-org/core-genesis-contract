// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../BitcoinAgent.sol";

contract BitcoinAgentMock is BitcoinAgent {
    
    
    function setCandidateMap(address candidate, uint256 lstStakeAmount, uint256 stakeAmount) external {
        candidateMap[candidate] = StakeAmount(lstStakeAmount, stakeAmount);
    }
    
    function setInitLpRates(
        uint32[4] calldata values,
        uint32[4] calldata rates
    ) external {
        delete grades;
        for (uint256 i = 0; i < 4; i++) {
            grades.push(DualStakingGrade(values[i], rates[i]));
        }
    }

    function setLpRates(uint32 stakeRate, uint32 percentage) external {
        grades.push(DualStakingGrade(stakeRate, percentage));
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
    function setAssetWeight(uint256 value) external {
        assetWeight = value;
    }

}
