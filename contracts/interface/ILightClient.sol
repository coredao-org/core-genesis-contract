pragma solidity ^0.6.4;

interface ILightClient {

  function isHeaderSynced(bytes32 appHash) external view returns (bool);

  function getSubmitter(bytes32 appHash) external view returns (address payable);

  function getChainTip() external view returns (bytes32);

  function getRoundPowers(uint256 roundTimeTag) external view returns (bytes20[] memory miners, uint256[] memory powers);

  function getRoundMiners(uint256 roundTimeTag) external view returns (bytes20[] memory miners);

  function getMiner(bytes32 hash) external view returns (bytes20);
}