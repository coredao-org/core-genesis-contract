pragma experimental ABIEncoderV2;
pragma solidity 0.6.12;

import "../CandidateHub.sol";

contract CandidateHubUnitMock is CandidateHub {
  uint256[] public integrals;
  uint256 public totalPower;
  uint256 public totalCoin;

  constructor() public CandidateHub() {}

  function developmentInit() external {
    requiredMargin = 1e19;
    roundInterval = 1;
    roundTag = 7;
    maxCommissionChange = 100;
  }

  function setRoundTimeTag(uint256 value) external {
    roundTag = value;
  }

  function setJailMap(address k, uint256 v) public {
    jailMap[k] = v;
  }

  function setCandidateMargin(address k, int256 v) public {
    candidateSet[operateMap[k] - 1].margin = v;
  }

  function setCandidateStatus(address k, uint256 v) public {
    candidateSet[operateMap[k] - 1].status = v;
  }

  function getCandidate(address k) public view returns (Candidate memory) {
    return candidateSet[operateMap[k] - 1];
  }

  function getIntegralMock(
    address[] memory candidates,
    bytes20[] memory lastMiners,
    bytes20[] memory miners,
    uint256[] memory powers
  ) external {
    (integrals, totalPower, totalCoin) = IPledgeAgent(PLEDGE_AGENT_ADDR).getIntegral(
      candidates,
      lastMiners,
      miners,
      powers
    );
  }

  function getIntegrals() external view returns (uint256[] memory) {
    return integrals;
  }

  function getValidatorsMock(
    address[] memory candidateList,
    uint256[] memory integralList,
    uint256 count
  ) public pure returns (address[] memory validatorList) {
    return getValidators(candidateList, integralList, count);
  }

  function inactiveAgentMock(address agent) external {
    IPledgeAgent(PLEDGE_AGENT_ADDR).inactiveAgent(agent);
  }

  function cleanMock() public {
    ISlashIndicator(SLASH_CONTRACT_ADDR).clean();
  }

  function registerMock(
    address operateAddr,
    address consensusAddr,
    address payable feeAddr,
    uint32 commissionThousandths
  ) external payable onlyInit {
    uint256 status = SET_CANDIDATE;
    candidateSet.push(
      Candidate(
        operateAddr,
        consensusAddr,
        feeAddr,
        commissionThousandths,
        int256(msg.value),
        status,
        roundTag,
        commissionThousandths
      )
    );
    uint256 index = candidateSet.length;
    operateMap[operateAddr] = index;
    consensusMap[consensusAddr] = index;

    emit registered(operateAddr, consensusAddr, feeAddr, commissionThousandths, int256(msg.value));
  }
}
