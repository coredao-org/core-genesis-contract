pragma solidity 0.6.12;

interface IRelayerHub {
  function isRelayer(address sender) external view returns (bool);
}


