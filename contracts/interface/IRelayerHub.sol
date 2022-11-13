pragma solidity 0.8.4;

interface IRelayerHub {
  function isRelayer(address sender) external view returns (bool);
}


