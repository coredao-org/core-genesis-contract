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
  uint256 public constant CORE_DECIMAL = 1e18;
  uint256 public constant INIT_UTXO_FEE = 1e4;

  address public lstToken;

  uint256 public utxoFee;
  bytes32[] public wallets;
  mapping(byte32 => uint256) walletStatus;

  // key: roundtag
  // value: reward per BTC accumulated
  mapping(uint256 => uint256) rewardPerBTC;

  // delegated value in the current round.
  uint256 public totalAmount;

  uint256 public lastRoundTag;

  Redeem[] public redeemRequests;

  uint256 public surplus;

  struct Redeem {
    address delegator;
    uint256 amount;
    bytes32 pkscriptHash;
  }

  event paramChange(string key, bytes value);
  event delegated(bytes32 indexed txid, address indexed delegator, uint256 amount);
  event transferredBtc(
    bytes32 indexed txid,
    address sourceAgent,
    address targetAgent,
    address delegator,
    uint256 amount,
    uint256 totalAmount
  );

  function init() external onlyNotInit {
    utxoFee = INIT_UTXO_FEE;
    alreadyInit = true;
  }

  function parsePayload(bytes29 payload) internal pure returns (address delegator, uint256 fee) {
    require(payload.len() >= 28, "payload length is too small");
    delegator = payload.indexAddress(7);
    fee = payload.indexUint(27, 1) * CORE_DECIMAL;
  }

  function delegate(bytes memory payload, bytes memory script, uint256 value) external onlyBtcAgent returns (address delegator, uint256 fee) {
    (delegator, fee) = parsePayload(payload);
    lstToken.mint(delegator, value);
  }

  function redeem(uint256 amount, bytes calldata pkscript) external {
    // check there is enough balance.
    require(amount + utxoFee <= lstToken.balanceOf(msg.sender), "Not enough btc token");
    if (amount == 0) {
      amount = lstToken.balanceOf(msg.sender) - utxoFee;
      require (amount >= utxoFee, "The redeem amount is too small.");
    }
    lstToken.burn(msg.sender, amount + utxoFee);
    redeemRequests.push[Redeem(msg.sender, amount, pkscript)];
    surplus += msg.sender;
    // TODO consider fee liabilities
  }

  function undelegate(bytes memory stxos, bytes29 voutView) external onlyBtcAgent {
    // Finds total number of outputs
    uint _numberOfOutputs = uint256(indexCompactInt(voutView, 0));
    uint64 _value;
    bytes memory _lockingScript;
    bytes32 pkScriptHash;
    uint256 redeemIndex;
    uint256 redeemSize;
    uint256 changeIndex;

    for (uint index = 0; index < _numberOfOutputs; ++index) {
      (_value, _lockingScript) = voutView.parseOutputValueAndScript(index);
      pkScriptHash = keccak256(_lockingScript);
      redeemSize = redeemRequests.length;
      for (redeemIndex = 0; redeemIndex < redeemSize; ++redeemIndex) {
        Redeem storage redeem = redeemRequests[redeemIndex];
        if (redeem.amount == _value && redeem.pkscript == pkScriptHash) {
          // TODO emit event
          if (redeemIndex + 1 < redeemSize) {
            redeemRequests[redeemIndex].pkscript = redeemRequests[redeemSize].pkscript;
            redeemRequests[redeemIndex]._value = redeemRequests[redeemSize]._value;
            redeemRequests[redeemIndex].delegator = redeemRequests[redeemSize].delegator;
          }
          redeemRequests.pop();
          break;
        }
      }
    }
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
