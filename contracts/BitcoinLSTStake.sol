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
  uint256 public constant WST_ACTIVE = 1;
  uint256 public constant WST_INACTIVE = 2;
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
  event redeemed(address indexed delegator, uint256 amount, uint256 utxoFee);
  event undelegated(bytes32 indexed txid, address indexed delegator, uint256 amount);

  function init() external onlyNotInit {
    utxoFee = INIT_UTXO_FEE;
    alreadyInit = true;
  }

  function parsePayload(bytes29 payload) internal pure returns (address delegator, uint256 fee) {
    require(payload.len() >= 28, "payload length is too small");
    delegator = payload.indexAddress(7);
    fee = payload.indexUint(27, 1);
  }

  function delegate(bytes32 txid, bytes29 payload, bytes memory script, uint256 value) external override onlyBtcAgent returns (address delegator, uint256 fee) {
    (delegator, fee) = parsePayload(payload);
    // check in walletStatus
    require(walletStatus[sha256(script)] != 0, "Unknown LST wallet");
    lstToken.mint(delegator, value);
    delegated(txid, delegator, value);
  }

  function redeem(uint256 amount, bytes calldata btcAddress) external {
    // check there is enough balance.
    require(amount + utxoFee <= lstToken.balanceOf(msg.sender), "Not enough btc token");
    if (amount == 0) {
      amount = lstToken.balanceOf(msg.sender) - utxoFee;
      require (amount >= utxoFee, "The redeem amount is too small.");
    }
    lstToken.burn(msg.sender, amount + utxoFee);
    // TODO decode btcAddress.
    // push btcaddress into redeem.
    redeemRequests.push[Redeem(msg.sender, amount, sha256(pkscript))];
    surplus += msg.sender;
    // TODO consider fee liabilities

    redeemed(msg.sender, amount, utxoFee, pkscript);
  }

  function undelegate(bytes32 txid, bytes memory stxos, bytes29 voutView) external onlyBtcAgent {
    // Finds total number of outputs
    uint _numberOfOutputs = uint256(indexCompactInt(voutView, 0));
    uint64 _amount;
    bytes29 _pkScript;
    bytes32 pkScriptHash;
    uint256 rIndex; // redeemIndex;
    uint256 redeemSize;
    uint256 changeIndex;

    for (uint index = 0; index < _numberOfOutputs; ++index) {
      (_amount, _pkScript) = voutView.parseOutputValueAndScript(index);
      pkScriptHash = sha256(_lockingScript);
      redeemSize = redeemRequests.length;
      for (rIndex = 0; rIndex < redeemSize; ++rIndex) {
        Redeem storage redeem = redeemRequests[rIndex];
        if (redeem.amount == _amount && redeem.pkscript == pkScriptHash) {
          // emit event
          undelegated(txid, redeem.delegator, _amount, _lockingScript);
          if (rIndex + 1 < redeemSize) {
            redeemRequests[rIndex].pkscript = redeemRequests[redeemSize].pkscript;
            redeemRequests[rIndex].amount = redeemRequests[redeemSize].amount;
            redeemRequests[rIndex].delegator = redeemRequests[redeemSize].delegator;
          }
          redeemRequests.pop();
          break;
        }
      }
      if (rIndex == redeemSize) {
        if (_lockingScript.length == 34 && _lockingScript[0] == 0 &&
            _lockingScript[1] == 32 && _scriptPubkeyView.index(2, 32)) {
          if (walletStatus[sha256(_scriptPubkeyView)])
        }

        (_scriptPubkeyView.len() == 34 && 
                    _scriptPubkeyView.indexUint(0, 1) == 0 &&
                    _scriptPubkeyView.indexUint(1, 1) == 32 &&
                    _scriptPubkeyView.index(2, 32) == sha256(_script)
      }
    }
  }

  function distributeReward(uint256 reward, uint256 roundTag) external override payable onlyBtcAgent{
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

  function ExtractPkScriptAddrs(bytes memory pkScript) internal {
    /***
    // Check for pay-to-pubkey-hash script.
    if hash := extractPubKeyHash(pkScript); hash != nil {
      return PubKeyHashTy, pubKeyHashToAddrs(hash, chainParams), 1, nil
    }

    // Check for pay-to-script-hash.
    if hash := extractScriptHash(pkScript); hash != nil {
      return ScriptHashTy, scriptHashToAddrs(hash, chainParams), 1, nil
    }

    // Check for pay-to-pubkey script.
    if data := extractPubKey(pkScript); data != nil {
      var addrs []btcutil.Address
      addr, err := btcutil.NewAddressPubKey(data, chainParams)
      if err == nil {
        addrs = append(addrs, addr)
      }
      return PubKeyTy, addrs, 1, nil
    }

    // Check for multi-signature script.
    #const scriptVersion = 0
    #details := extractMultisigScriptDetails(scriptVersion, pkScript, true)
    #if details.valid {
    #  // Convert the public keys while skipping any that are invalid.
    #  addrs := make([]btcutil.Address, 0, len(details.pubKeys))
    #  for _, pubkey := range details.pubKeys {
    #    addr, err := btcutil.NewAddressPubKey(pubkey, chainParams)
    #    if err == nil {
    #      addrs = append(addrs, addr)
    #    }
    #  }
    #  return MultiSigTy, addrs, details.requiredSigs, nil
    #}

    // Check for null data script.
    if isNullDataScript(scriptVersion, pkScript) {
      // Null data transactions have no addresses or required signatures.
      return NullDataTy, nil, 0, nil
    }

    if hash := extractWitnessPubKeyHash(pkScript); hash != nil {
      var addrs []btcutil.Address
      addr, err := btcutil.NewAddressWitnessPubKeyHash(hash, chainParams)
      if err == nil {
        addrs = append(addrs, addr)
      }
      return WitnessV0PubKeyHashTy, addrs, 1, nil
    }

    if hash := extractWitnessV0ScriptHash(pkScript); hash != nil {
      var addrs []btcutil.Address
      addr, err := btcutil.NewAddressWitnessScriptHash(hash, chainParams)
      if err == nil {
        addrs = append(addrs, addr)
      }
      return WitnessV0ScriptHashTy, addrs, 1, nil
    }

    if rawKey := extractWitnessV1KeyBytes(pkScript); rawKey != nil {
      var addrs []btcutil.Address
      addr, err := btcutil.NewAddressTaproot(rawKey, chainParams)
      if err == nil {
        addrs = append(addrs, addr)
      }
      return WitnessV1TaprootTy, addrs, 1, nil
    }
    **/
  }
}
