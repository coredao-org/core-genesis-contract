// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IAgent.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/ILightClient.sol";
import "./interface/IBitcoinLSTStake.sol";
import "./interface/IPledgeAgent.sol";
import "./lib/Address.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./System.sol";

contract BitcoinLSTStake is IBitcoinLSTStake, System, IParamSubscriber {
  uint256 public constant ST_ACTIVE = 1;
  uint256 public constant ST_INACTIVE = 2;

  address public lstToken;
  bytes32[] public wallets;
  mapping(byte32 => uint256) walletStatus;

  // key: roundtag
  // value: reward per BTC accumulated
  mapping(uint256 => uint256) rewardPerBTC;

  // delegated value in the current round.
  uint256 public totalAmount;

  uint256 public lastRoundTag;

  function parsePayload(bytes29 payload) internal pure returns (address delegator) {
    require(payload.len() >= 27, "payload length is too small");
    delegator = payload.indexAddress(7);
  }

  function delegate(bytes memory payload, bytes memory script, uint256 value) external onlyBtcAgent {

    uint256 delegator = parsePayload(payload);

    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "only delegator or relayer can submit the BTC transaction");

    lstToken.mint(delegator, value);
  }

  function burn(uint256 amount) external {
    // TODO
    // Step 1
    // 1. User commit a burn tx with amount,
    // 2. burn btctoken from erc20
    //    lstToken.burn(delegator, value);
    // 3. calculate reward.
    // 4. emit event
    // Step 2 offline
    // 1. multisig build a tx & PSBT process & broadcast to BTC network
    // Step 3 
    // 1. relayer submit a btc tx in BitcoinAgent.verifyBurnTx
  }

  function undelegate(bytes btctx) external onlyBtcAgent {
    // TODO mark a burn workflow finish
  }

  function distributeReward(uint256 reward, uint256 roundTag) external payable {
    rewardPerBTC[roundTag] += rewardPerBTC[lastRoundTag] + reward * BTC_DECIMAL / totalAmount;
    lastRoundTag = roundTag;
  }

  /// Get stake amount
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getStakeAmount() external view returns (uint256 totalAmount) {
    return lstToken.totalSupply();
  }

  /// Get stake amount
  /// @return totalAmount The sum of all amounts of valid/invalid candidates.
  function getLastStakeAmount() external view returns (uint256 totalAmount) {
    return totalAmount;
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "add")) {
      addMultisigAddress(value);
    } else if (Memory.compareStrings(key, "remove")) {
      removeWallet(value);
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /*********************** Inner Methods *****************************/
  function addWallet(bytes memory addr) internal {
    // decode address -> bytes32addr, networkId
    // verify bitcoin networkId
    // wallets.push(bytes32addr)
    // walletStatus[addr] = INACTIVE
  }

  function removeWallet(bytes memory addr) internal {
    // decode address -> bytes32addr, networkId
    // verify bitcoin networkId
    // walletStatus[addr] = ST_INACTIVE
  }
}
