pragma solidity 0.6.12;

interface ILightClient {
  function getRoundPowers(uint256 roundTimeTag, address[] memory candidates) external view returns (uint256[] memory powers);

  function getRoundCandidates(uint256 roundTimeTag) external view returns (address[] memory candidates);
  
  function getRoundMiners(uint256 roundTimeTag, address candidate) external view returns (address[] memory miners);
}