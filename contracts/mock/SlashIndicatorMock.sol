// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../SlashIndicator.sol";
import "../lib/RLPDecode.sol";

contract SlashIndicatorMock is SlashIndicator {
    using RLPDecode for bytes;
    using RLPDecode for RLPDecode.RLPItem;

    function developmentInit() external {
        rewardForReportDoubleSign = rewardForReportDoubleSign / 1e16;
        felonyDeposit = felonyDeposit / 1e16;
        misdemeanorThreshold = 2;
        felonyThreshold = 4;
    }

    function parseHeader(bytes calldata header) public pure returns (bytes32, address) {
        RLPDecode.RLPItem[] memory items = header.toRLPItem().toList();
        return parseHeader(items);
    }

    function setIndicators(address[] calldata newValidators, uint256[] calldata counts) public {
        for (uint256 i = validators.length; i > 0; i--) {
            delete indicators[validators[i - 1]];
            validators.pop();
        }

        for (uint256 i = newValidators.length; i > 0; i--) {
            indicators[newValidators[i - 1]] = Indicator(0, counts[i - 1], true);
            validators.push(newValidators[i - 1]);
        }
    }


    function getIndicators() public view returns (address[] memory, uint256[] memory) {
        address[] memory v = new address[](validators.length);
        uint256[] memory c = new uint256[](validators.length);
        for (uint256 i = 0; i < validators.length; i++) {
            v[i] = validators[i];
            c[i] = indicators[v[i]].count;
        }
        return (v, c);
    }

    function mockEcrecovery(bytes32 hash, bytes memory sig) public returns (address) {
        return ecrecovery(hash, sig);
    }

    function setMisdemeanorThreshold(uint256 _misdemeanorThreshold) external {
        misdemeanorThreshold = _misdemeanorThreshold;
    }
    function setFelonyThreshold(uint256 _felonyThreshold) external {
        felonyThreshold = _felonyThreshold;
    }

    // for uint test
    function mockSubmitFinalityViolationEvidence(FinalityEvidence memory evidence) external onlyInit {
        if (rewardForReportFinalityViolation == 0) {
            rewardForReportFinalityViolation = INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION;
        }

        // Basic check
        require(evidence.voteA.srcNum + 86400 > block.number &&
        evidence.voteB.srcNum + 86400 > block.number, "too old block involved");
        require(!(evidence.voteA.srcHash == evidence.voteB.srcHash &&
            evidence.voteA.tarHash == evidence.voteB.tarHash), "two identical votes");
        require(evidence.voteA.srcNum < evidence.voteA.tarNum &&
        evidence.voteB.srcNum < evidence.voteB.tarNum, "srcNum bigger than tarNum");

        // Vote rules check
        require((evidence.voteA.srcNum < evidence.voteB.srcNum && evidence.voteB.tarNum < evidence.voteA.tarNum) ||
        (evidence.voteB.srcNum < evidence.voteA.srcNum && evidence.voteA.tarNum < evidence.voteB.tarNum) ||
        evidence.voteA.tarNum == evidence.voteB.tarNum, "no violation of vote rules");

        // BLS verification 
        // Default BLS verification passed.
        // require(verifyBLSSignature(evidence.voteA, evidence.voteAddr) &&
        // verifyBLSSignature(evidence.voteB, evidence.voteAddr), "verify signature failed");

        (address[] memory vals, bytes[] memory voteAddrs) = IValidatorSet(VALIDATOR_CONTRACT_ADDR).getLivingValidators();
        if (voteAddrs.length <= 1) {
            return;
        }
        for (uint256 i; i < voteAddrs.length; ++i) {
            if (BytesLib.equal(voteAddrs[i], evidence.voteAddr)) {
                indicators[vals[i]].count = 0;
                ISystemReward(SYSTEM_REWARD_ADDR).claimRewards(payable(msg.sender), rewardForReportFinalityViolation);
                IValidatorSet(VALIDATOR_CONTRACT_ADDR).felony(vals[i], felonyRound, felonyDeposit);
                break;
            }
        }
    }
    function mockSlashWithBlockCount(address validator, uint256 blockCount) external {
        slashWithBlockCount(validator, blockCount);
    }
}
