// SPDX-License-Identifier: MIT
pragma solidity 0.8.4;

library SatoshiPlusHelper {
  uint256 public constant DENOMINATOR = 1e4;

  // Protocol MAGIC `SAT+`, represents the short name for Satoshi plus protocol.
  uint256 public constant BTC_STAKE_MAGIC = 0x5341542b;
  uint256 public constant BTC_DECIMAL = 1e8;
  uint256 public constant CORE_DECIMAL = 1e18;
  uint256 public constant CORE_STAKE_DECIMAL = 1e24;
  uint256 public constant ROUND_INTERVAL = 86400;
  uint256 public constant CHAINID = 1116;
  uint32 public constant INIT_BTC_CONFIRM_BLOCK = 3;

  uint32 public constant BTC_STAKE_VERSION = 1;
  uint32 public constant BTCLST_STAKE_VERSION = 2;

  // Bech32 encoded segwit addresses start with a human-readable part
  // (hrp) followed by '1'. For Bitcoin mainnet the hrp is "bc"(0x6263), and for
  // testnet it is "tb"(0x7462).
  uint256 public constant BECH32_HRP_SEGWIT = 0x6263;
}
