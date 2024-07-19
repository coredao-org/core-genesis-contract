// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

interface ILightClient {
  function getRoundPowers(uint256 roundTimeTag, address[] calldata candidates) external view returns (uint256[] memory powers, uint256 totalPower);

  function getRoundCandidates(uint256 roundTimeTag) external view returns (address[] memory candidates);
  
  function getRoundMiners(uint256 roundTimeTag, address candidate) external view returns (address[] memory miners);

  function checkTxProof(bytes32 txid, uint32 blockHeight, uint32 confirmBlock, bytes32[] calldata nodes, uint256 index) external view returns (bool, uint64);
}