// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./interface/IBitcoinLSTToken.sol";
import "./interface/IBitcoinStake.sol";
import "./interface/ICandidateHub.sol";
import "./interface/ILightClient.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IStakeHub.sol";
import "./lib/BytesLib.sol";
import "./lib/Memory.sol";
import "./lib/BitcoinHelper.sol";
import "./lib/SatoshiPlusHelper.sol";
import "./System.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/// This contract handles LST BTC staking. 
/// Relayers submit BTC stake/redeem transactions to Core chain here.
contract BitcoinLSTStake is IBitcoinStake, System, IParamSubscriber, ReentrancyGuard {
  using BitcoinHelper for *;
  using TypedMemView for *;
  using BytesLib for *;

  uint32 public constant WALLET_ACTIVE = 1;
  uint32 public constant WALLET_INACTIVE = 2;

  bytes1 constant OP_DUP = 0x76;
  bytes1 constant OP_HASH160 = 0xa9;
  bytes1 constant OP_DATA_20 = 0x14;
  bytes1 constant OP_DATA_32 = 0x20;
  bytes1 constant OP_EQUALVERIFY = 0x88;
  bytes1 constant OP_CHECKSIG = 0xac;
  bytes1 constant OP_EQUAL = 0x87;
  bytes1 constant OP_0 = 0;
  bytes1 constant OP_1 = 0x51;

  uint32 public constant WTYPE_UNKNOWN = 0;
  // 25 OP_DUP OP_HASH160 OP_DATA_20 <hash160> OP_EQUALVERIFY OP_CHECKSIG
  uint32 public constant WTYPE_P2PKH = 1;
  // 23 OP_HASH160 OP_DATA_20 <hash160> OP_EQUAL
  uint32 public constant WTYPE_P2SH = 2;
  // 22 witnessVer OP_0 OP_DATA_20 <hash160>
  uint32 public constant WTYPE_P2WPKH = 4;
  // 34 witnessVer OP_0 OP_DATA_32 <32-byte-hash>
  uint32 public constant WTYPE_P2WSH = 8;
  // 34 witnessVer OP_1 OP_DATA_32 <32-byte-hash>
  uint32 public constant WTYPE_P2TAPROOT = 16;

  uint64 public constant INIT_UTXO_FEE = 1e4;

  // This field records each btc staking tx, and it will never be cleared.
  // key: bitcoin tx id
  // value: bitcoin stake record
  mapping(bytes32 => BtcTx) public btcTxMap;

  // staked BTC amount when the last round snapshot is taken
  uint64 public stakedAmount;

  // realtime staked BTC amount
  uint64 public realtimeAmount;

  // key: delegator address
  // value: stake info.
  mapping(address => UserStakeInfo) public userStakeInfo;

  // key: roundtag
  // value: reward per BTC accumulated
  mapping(uint256 => uint256) accuredRewardPerBTCMap;

  // the number of blocks to mark a BTC staking transaction as confirmed
  uint32 public btcConfirmBlock;

  // This field is used to store lst reward of delegators
  // key: delegator address
  // value: amount of CORE tokens claimable
  mapping(address => uint256) public rewardMap;

  // the current round, it is updated in setNewRound.
  uint256 public roundTag;

  // initial round
  uint256 public initRound;

  // a list of BTC wallet address which holds the BTC assets for the lst product
  WalletInfo[] public wallets;

  // key: keccak256 of pkscript.
  // value: index+1 of wallets.
  mapping(bytes32 => uint256) walletMap;

  // a list of lst redeem/burn request whose BTC payout transaction are in pending status
  Redeem[] public redeemRequests;

  // key: keccak256 of pkscript.
  // value: index+1 of redeemRequests.
  mapping(bytes32 => uint256) redeemMap;

  // Fee paid in BTC to burn lst tokens
  uint64 public utxoFee;

  // Time grading applied to BTC stakers
  // There is no timelock set in the BTC lst stake transaction, as a result a same rate is set to apply to all
  uint256 public percentage;

  // whether the time grading is enabled
  uint256 public gradeActive;

  struct BtcTx {
    uint64 amount;
    uint32 outputIndex;
  }

  struct Redeem {
    bytes32 hash; // it may be 20-byte-hash or 32-bytes-hash.
    uint32  addrType;
    uint64  amount;
  }

  struct WalletInfo {
    bytes32 hash; // it may be 20-byte-hash or 32-bytes-hash.
    uint32 addrType;
    uint32 status;
  }

  struct UserStakeInfo {
    uint256 changeRound; // the round when last op happens, including mint/burn/transfer/claim.
    uint64 realtimeAmount; // realtime staked BTC amount
    uint64 stakedAmount; // staked BTC amount when the last round snapshot is taken
  }

  /*********************** events **************************/
  event delegated(bytes32 indexed txid, address indexed delegator, uint64 amount, uint256 fee);
  event redeemed(address indexed delegator, uint64 amount, uint64 utxoFee, bytes pkscript);
  event undelegated(bytes32 indexed txid, uint32 outputIndex, uint64 amount, bytes pkscript);
  event undelegatedOverflow(bytes32 indexed txid, uint32 outputIndex, uint64 expectAmount, uint64 actualAmount, bytes pkscript);
  event addedWallet(bytes32 indexed _hash, uint64 _type);
  event removedWallet(bytes32 indexed _hash, uint64 _type);

  modifier onlyBtcLSTToken() {
    require(msg.sender == BTCLST_TOKEN_ADDR, 'only btc lst token can call this function');
    _;
  }

  /*********************** Init ********************************/

  function init() external onlyNotInit {
    utxoFee = INIT_UTXO_FEE;
    initRound = ICandidateHub(CANDIDATE_HUB_ADDR).getRoundTag();
    roundTag = initRound;
    btcConfirmBlock = SatoshiPlusHelper.INIT_BTC_CONFIRM_BLOCK;
    percentage = SatoshiPlusHelper.DENOMINATOR / 2;
    gradeActive = 1;
    alreadyInit = true;
  }

  /*********************** Interface implementations ***************************/

  /// Bitcoin LST delegate, it is called by relayer
  ///
  /// User workflow to delegate BTC to Core blockchain
  ///  1. A user creates a bitcoin transaction by minting lstBTC
  ///  2. Relayer transmits BTC tx to Core chain by calling this method
  ///  3. lstBTC token contract is called in this method
  ///
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  /// @param script it is a redeem script of the locked up output
  function delegate(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index, bytes memory script) external override {
    bytes32 txid = btcTx.calculateTxId();
    BtcTx storage bt = btcTxMap[txid];
    require(bt.amount == 0, "btc tx is already delegated.");
    bool txChecked = ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index);
    require(txChecked, "btc tx isn't confirmed");
    checkWallet(script);

    address delegator;
    uint64 btcAmount;
    {
      (,,bytes29 voutView,) = btcTx.extractTx();
      uint32 outputIndex;
      uint256 fee;
      (btcAmount, outputIndex, delegator, fee) = parseVout(voutView, script);
      require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender) || msg.sender == delegator, "only delegator or relayer can submit the BTC transaction");
      require(btcAmount >= utxoFee * 2, "btc amount is too small");
      bt.amount = btcAmount;
      bt.outputIndex = outputIndex;
      if (fee != 0) {
        fee *= SatoshiPlusHelper.CORE_DECIMAL;
        IStakeHub(STAKE_HUB_ADDR).addNotePayable(delegator, msg.sender, fee);
      }
      emit delegated(txid, delegator, btcAmount, fee);
    }

    IBitcoinLSTToken(BTCLST_TOKEN_ADDR).mint(delegator, btcAmount);

    _afterMint(delegator, btcAmount);

    realtimeAmount += btcAmount;   
  }

  /// Bitcoin LST undelegate, it is called by relayer
  /// This method is used to clear redeem requests.
  ///
  /// @param btcTx the BTC transaction data
  /// @param blockHeight block height of the transaction
  /// @param nodes part of the Merkle tree from the tx to the root in LE form (called Merkle proof)
  /// @param index index of the tx in Merkle tree
  function undelegate(bytes calldata btcTx, uint32 blockHeight, bytes32[] memory nodes, uint256 index) external override nonReentrant {
    bytes32 txid = btcTx.calculateTxId();
    bool txChecked = ILightClient(LIGHT_CLIENT_ADDR).checkTxProof(txid, blockHeight, btcConfirmBlock, nodes, index);
    require(txChecked, "btc tx not confirmed");
    (,, bytes29 voutView,) = btcTx.extractTx();

    // Finds total number of outputs
    uint32 _numberOfOutputs = uint32(voutView.indexCompactInt(0));
    uint64 _amount;
    bytes29 _pkScript;

    for (uint32 i = 0; i < _numberOfOutputs; ++i) {
      (_amount, _pkScript) = voutView.parseOutputValueAndScript(i);
      bytes memory pkscript = _pkScript.clone();
      // (hash, addrType) = extractPkScriptAddr(pkscript);
      bytes32 key = keccak256(abi.encodePacked(pkscript));
      uint256 index1 = redeemMap[key];
      if (index1 != 0) {
        Redeem storage rd = redeemRequests[index1 - 1];
        emit undelegated(txid, i, _amount, pkscript);
        if (rd.amount <= _amount) {
          if (rd.amount < _amount) {
            emit undelegatedOverflow(txid, i, rd.amount, _amount, pkscript);
          }
          delete redeemMap[key];
          if (index1 < redeemRequests.length) {
            redeemRequests[index1 - 1] = redeemRequests[redeemRequests.length - 1];
            pkscript = buildPkScript(rd.hash, rd.addrType);
            key = keccak256(abi.encodePacked(pkscript));
            redeemMap[key] = index1;
          }
          redeemRequests.pop();
        } else {
          rd.amount -= _amount;
        }
      } else if (_amount != 0) {
        /// TODO better to use a different error message, which would be easier for debugging
        emit undelegatedOverflow(txid, i, 0, _amount, pkscript);
      }
    }
  }

  /// Receive round rewards from BitcoinAgent. It is triggered at the beginning of turn round.
  /// @param validators List of validator operator addresses
  /// @param rewardList List of reward amount
  function distributeReward(address[] calldata validators, uint256[] calldata rewardList) external override onlyBtcAgent {
    uint256 reward;
    uint256 validatorSize = validators.length;
    for (uint256 i = 0; i < validatorSize; ++i) {
      reward += rewardList[i];
    }
    if (stakedAmount == 0) {
      accuredRewardPerBTCMap[roundTag] = accuredRewardPerBTCMap[roundTag-1];
    } else {
      accuredRewardPerBTCMap[roundTag] = accuredRewardPerBTCMap[roundTag-1] + reward * SatoshiPlusHelper.BTC_DECIMAL / stakedAmount;
    }
  }

  /// Get staked BTC amount.
  ///
  /// @param candidates List of candidate operator addresses
  /// @return amounts List of amounts of all special candidates in this round
  function getStakeAmounts(address[] calldata candidates) external override view returns (uint256[] memory amounts) {
    // LST BTC are hypothetically designed to stake evenly to the living validators
    uint256 length = candidates.length;
    amounts = new uint256[](length);
    uint256 sustainValidatorCount;
    for (uint256 i = 0; i < length; i++) {
      if (ICandidateHub(CANDIDATE_HUB_ADDR).isValidator(candidates[i])) {
        amounts[i] = 1;
        sustainValidatorCount++;
      }
    }
    if (sustainValidatorCount != 0) {
      uint256 avgAmount = realtimeAmount / sustainValidatorCount;
      for (uint256 i = 0; i < length; i++) {
        if (amounts[i] == 1) {
          amounts[i] = avgAmount;
        }
      }
    }
  }

  /// Start new round, this is called by the CandidateHub contract
  /// @param round The new round tag
  function setNewRound(address[] calldata /*validators*/, uint256 round) external override onlyBtcAgent {
    stakedAmount = realtimeAmount;
    roundTag = round;
  }

  /// Prepare for the new round
  function prepare(uint256) external override {
    // nothing to prepare
  }

  /// Claim reward for delegator
  /// @param delegator the delegator address
  /// @return reward Amount claimed
  /// @return rewardUnclaimed Amount unclaimed
  function claimReward(address delegator) external override onlyBtcAgent returns (uint256 reward, uint256 rewardUnclaimed) {
    reward = _updateUserRewards(delegator, true);
    // apply time grading
    if (gradeActive == 1) {
      uint256 rewardClaimed = reward * percentage / SatoshiPlusHelper.DENOMINATOR;
      rewardUnclaimed = reward - rewardClaimed;
      reward = rewardClaimed;
    }
    
    return (reward, rewardUnclaimed);
  }

  /*********************** External implementations ***************************/
  /// Burn LST token and redeem BTC assets.
  /// This method is called by LST holders.
  ///
  /// @param amount redeem amount
  /// @param pkscript pkscript to receive BTC assets
  function redeem(uint64 amount, bytes calldata pkscript) external nonReentrant {
    (bytes32 hash, uint32 addrType) = extractPkScriptAddr(pkscript);
    require(addrType != WTYPE_UNKNOWN, "invalid pkscript");

    UserStakeInfo storage user = userStakeInfo[msg.sender];
    uint64 balance = user.realtimeAmount;
    // check there is enough balance.
    require(amount <= balance, "Not enough btc token");
    if (amount == 0) {
      amount = balance;
    }
    require (amount >= utxoFee * 2, "The redeem amount is too small");
    uint64 burnAmount = amount;
    amount -= utxoFee;

    bytes32 key = keccak256(abi.encodePacked(pkscript));
    uint256 index1 = redeemMap[key];
    if (index1 == 0) {
      redeemRequests.push(Redeem(hash, addrType, amount));
      redeemMap[key] = redeemRequests.length;
    } else {
      redeemRequests[index1 - 1].amount += amount;
    }

    IBitcoinLSTToken(BTCLST_TOKEN_ADDR).burn(msg.sender, uint256(burnAmount));
    emit redeemed(msg.sender, amount, utxoFee, pkscript);

    _afterBurn(msg.sender, burnAmount);
    realtimeAmount -= burnAmount;
  }

  /// This method should be called whenever lst token transfer happens
  /// @param from ERC20 standard from address
  /// @param to ERC20 standard to address
  /// @param value the amount of tokens to transfer
  function onTokenTransfer(address from, address to, uint256 value) external onlyBtcLSTToken {
    uint64 amount = uint64(value);
    require(uint256(amount) == value, 'btc amount limit uint64');
    _afterBurn(from, amount);
    _afterMint(to, amount);
  }

  /// Returns wallets array.
  function getWallets() external view returns (WalletInfo[] memory) {
    return wallets;
  }

  /*********************** Governance ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (Memory.compareStrings(key, "add")) {
      addWallet(value);
    } else if (Memory.compareStrings(key, "remove")) {
      removeWallet(value);
    } else {
      if (value.length != 32) {
        revert MismatchParamLength(key);
      }
      if (Memory.compareStrings(key, "percentage")) {
        uint256 newPercentage = value.toUint256(0);
        if (newPercentage == 0 || newPercentage > SatoshiPlusHelper.DENOMINATOR) {
          revert OutOfBounds(key, newPercentage, 1, SatoshiPlusHelper.DENOMINATOR);
        }
        percentage = newPercentage;
      } else if (Memory.compareStrings(key, "gradeActive")) {
        uint256 newActive = value.toUint256(0);
        if (newActive > 1) {
          revert OutOfBounds(key, newActive, 0, 1);
        }
        gradeActive = newActive;
      } else {
        revert UnsupportedGovParam(key);
      }
    }
    emit paramChange(key, value);
  }

  /*********************** Inner Methods *****************************/
  /// Add a new BTC wallet which holds the BTC assets for the LST product
  /// This method can only be called by `updateParam()` through governance vote
  /// @param pkscript public key script of the wallet
  function addWallet(bytes memory pkscript) internal {
    bytes32 walletKey = keccak256(abi.encodePacked(pkscript));
    uint256 index1 = walletMap[walletKey];
    if (index1 > 0) {
      if (wallets[index1 - 1].status != WALLET_ACTIVE) {
        wallets[index1 - 1].status = WALLET_ACTIVE;
      }
    } else {
      (bytes32 _hash, uint32 _type) = extractPkScriptAddr(pkscript);
      require(_type != WTYPE_UNKNOWN, "Invalid BTC wallet");
      wallets.push(WalletInfo(_hash, _type, WALLET_ACTIVE));
      index1 = wallets.length;
      walletMap[walletKey] = index1;
    }
    emit addedWallet(wallets[index1-1].hash, wallets[index1-1].addrType);
  }

  /// Remove a BTC wallet
  /// This method can only be called by `updateParam()` through governance vote
  /// @param pkscript public key script of the wallet
  function removeWallet(bytes memory pkscript) internal {
    bytes32 walletKey = keccak256(abi.encodePacked(pkscript));
    uint256 index1 = walletMap[walletKey];
    require(index1 != 0, "Wallet not found");
    WalletInfo storage w = wallets[index1 - 1];
    if (w.status != WALLET_INACTIVE) {
     w.status = WALLET_INACTIVE;
    }
    emit removedWallet(w.hash, w.addrType);
  }

  /// check whether the BTC transaction aims for LST staking
  /// @param pkscript redeem script of the locked up output
  function checkWallet(bytes memory pkscript) internal view {
    bytes32 walletKey = keccak256(abi.encodePacked(pkscript));
    uint256 index1 = walletMap[walletKey];
    require(index1 != 0, "Wallet not found");
    require(wallets[index1 - 1].status == WALLET_ACTIVE, "wallet inactive");
  }

  /// extract address information from pkscript
  /// @param pkScript pkscript used in txout
  function extractPkScriptAddr(bytes memory pkScript) internal pure returns (bytes32 whash, uint32 addrType) {
    uint256 len = pkScript.length;
    if (len == 25) {
      // pay-to-pubkey-hash
      // OP_DUP OP_HASH160 OP_DATA_20 <hash160> OP_EQUALVERIFY OP_CHECKSIG
      if (pkScript[0] == OP_DUP && pkScript[1] == OP_HASH160 &&
          pkScript[2] == OP_DATA_20 && pkScript[23] == OP_EQUALVERIFY &&
          pkScript[24] == OP_CHECKSIG) {
        return (pkScript.indexBytes32(3, 20), WTYPE_P2PKH);
      }
    } else if (len == 23) {
      // pay-to-script-hash
      // 23 OP_HASH160 OP_DATA_20 <hash160> OP_EQUAL
      if (pkScript[0] == OP_HASH160 && pkScript[1] == OP_DATA_20 &&
          pkScript[22] == OP_EQUAL) {
        return (pkScript.indexBytes32(2, 20), WTYPE_P2SH);
      }
    } else if (len == 22) {
      // 22 OP_0 OP_DATA_20 <hash160>
      if (pkScript[0] == OP_0 && pkScript[1] == OP_DATA_20) {
        return (pkScript.indexBytes32(2, 20), WTYPE_P2WPKH);
      }
    } else if (len == 34) {
      // 34 OP_0 OP_DATA_32 <hash160>
      if (pkScript[0] == OP_0 && pkScript[1] == OP_DATA_32) {
        return (pkScript.indexBytes32(2, 32), WTYPE_P2WSH);
      }
      // 34 OP_1 OP_DATA_20 <hash160>
      if (pkScript[0] == OP_1 && pkScript[1] == OP_DATA_32) {
        return (pkScript.indexBytes32(2, 32), WTYPE_P2TAPROOT);
      }
    }
    return (0, WTYPE_UNKNOWN);
  }

  /// construct script from hash and address type
  /// @param whash the hash used to build the script
  /// @param addrType the BTC address type used to build the script
  /// @return pkscript the script
  function buildPkScript(bytes32 whash, uint32 addrType) internal pure returns (bytes memory pkscript) {
    if (addrType == WTYPE_P2WSH || addrType == WTYPE_P2TAPROOT) {
      pkscript = new bytes(34);
      pkscript[1] = OP_DATA_32;
      if (addrType == WTYPE_P2WSH) {
        pkscript[0] = OP_0;
      } else if (addrType == WTYPE_P2TAPROOT) {
        pkscript[0] = OP_1;
      }
      assembly {
        mstore(add(pkscript, 0x22), whash)
      }
      return pkscript;
    }
    uint startPos = 0x22;
    if (addrType == WTYPE_P2PKH) {
      pkscript = new bytes(25);
      pkscript[0] = OP_DUP;
      pkscript[1] = OP_HASH160;
      pkscript[2] = OP_DATA_20;
      pkscript[23] = OP_EQUALVERIFY;
      pkscript[24] = OP_CHECKSIG;
      startPos = 0x23;
    } else if (addrType == WTYPE_P2SH) {
      pkscript = new bytes(23);
      pkscript[0] = OP_HASH160;
      pkscript[1] = OP_DATA_20;
      pkscript[22] = OP_EQUAL;
    } else if (addrType == WTYPE_P2WPKH) {
      pkscript = new bytes(22);
      pkscript[0] = OP_0;
      pkscript[1] = OP_DATA_20;
    }
    unchecked {
      uint mask = 256 ** (32 - 20) - 1;
      assembly {
        let srcpart := and(shl(96, whash), not(mask))
        let destpart := and(mload(add(pkscript, startPos)), mask)
        mstore(add(pkscript, startPos), or(destpart, srcpart))
      }
    }
  }

  /// get accrued reward for each unit of BTC of a given round
  /// @param round the round to retrieve reward value
  function getRoundRewardPerBTC(uint256 round) internal view returns (uint256 reward) {
    if (round <= initRound) {
      return 0;
    }
    for (;round != initRound; --round) {
      reward = accuredRewardPerBTCMap[round];
      if (reward != 0) {
        return reward;
      }
    }
    return 0;
  }

  /// calculate user reward and update internal reward map
  /// @param userAddress the user address to update
  /// @param claim whether the return amount of reward will be claimed
  /// @return reward amount of user reward updated/claimed
  function _updateUserRewards(address userAddress, bool claim) internal returns (uint256 reward) {
    UserStakeInfo storage user = userStakeInfo[userAddress];
    uint256 changeRound = user.changeRound;
    if (changeRound != 0 && changeRound < roundTag) {
      uint256 lastRoundTag = roundTag - 1;
      uint256 lastRoundReward = getRoundRewardPerBTC(lastRoundTag);
      reward = uint256(user.stakedAmount) * (lastRoundReward - getRoundRewardPerBTC(changeRound - 1)) / SatoshiPlusHelper.BTC_DECIMAL;

      if (user.realtimeAmount != user.stakedAmount) {
        if (changeRound < lastRoundTag) {
          reward += (user.realtimeAmount - user.stakedAmount) * (lastRoundReward - getRoundRewardPerBTC(changeRound)) / SatoshiPlusHelper.BTC_DECIMAL;
        }
        user.stakedAmount = user.realtimeAmount;
      }
    }
    if (changeRound != roundTag) {
      user.changeRound = roundTag;
    }
    // make sure the caller to send the rewards out
    // otherwise the rewards will be gone
    if (claim) {
      if (rewardMap[userAddress] != 0) {
        reward += rewardMap[userAddress];
        rewardMap[userAddress] = 0;
      }
    } else {
      rewardMap[userAddress] += reward;
    }
  }

  /// this method is called when lst tokens are burnt
  /// @param from the address to burn the tokens
  /// @param value the amount of tokens to burn
  function _afterBurn(address from, uint64 value) internal {
    require(from != address(0), "invalid sender");
    UserStakeInfo storage user = userStakeInfo[from];
    uint64 balance = user.realtimeAmount;
    require(value <= balance, "Insufficient balance");
    _updateUserRewards(from, false);
    user.realtimeAmount -= value;
    if (user.realtimeAmount < user.stakedAmount) {
      user.stakedAmount = user.realtimeAmount;
    }
  }

  /// this method is called when lst tokens are mint
  /// @param to the address to mint tokens
  /// @param value the amount of tokens to mint
  function _afterMint(address to, uint64 value) internal {
    require(to != address(0), "invalid receiver");
    _updateUserRewards(to, false);
    userStakeInfo[to].realtimeAmount += value;
  }

  /// Parses the target output and the op_return of a transaction
  /// @dev  Finds the BTC amount that payload size is less than 80 bytes
  /// @param _voutView    The vout of a Bitcoin transaction
  /// @param _lockingScript redeem script of the locked up output
  /// @return btcAmount   Amount of BTC to stake
  /// @return outputIndex The output index of target output.
  /// @return delegator   The one who delegate the Bitcoin
  /// @return fee         The value pay for relayer.
  function parseVout(
      bytes29 _voutView,
      bytes memory _lockingScript
  ) internal view returns (uint64 btcAmount, uint32 outputIndex, address delegator, uint256 fee) {
    _voutView.assertType(uint40(BitcoinHelper.BTCTypes.Vout));
    bytes29 _outputView;
    bytes29 _scriptPubkeyView;
    bytes29 _scriptPubkeyWithLength;
    bytes29 _arbitraryData;

    // Finds total number of outputs
    uint _numberOfOutputs = uint256(_voutView.indexCompactInt(0));
    bool opreturn;

    for (uint index = 0; index < _numberOfOutputs; index++) {
      _outputView = _voutView.indexVout(index);
      _scriptPubkeyView = _outputView.scriptPubkey();
      _scriptPubkeyWithLength = _outputView.scriptPubkeyWithLength();
      _arbitraryData = _scriptPubkeyWithLength.opReturnPayload();

      // Checks whether the output is an arbitarary data or not
      if(_arbitraryData == TypedMemView.NULL) {
        // Output is not an arbitrary data
        if (keccak256(abi.encodePacked(_scriptPubkeyView.clone())) == keccak256(abi.encodePacked(_lockingScript))
        ) {
          btcAmount = _outputView.value();
          outputIndex = uint32(index);
        }
      } else {
        (delegator, fee) = parsePayloadAndCheckProtocol(_arbitraryData);
        opreturn = true;
      }
    }
    require(btcAmount != 0, "staked value is zero");
    require(opreturn, "no opreturn");
  }

  /// parse the payload and do sanity check for SAT+ bytes
  /// @param payload the BTC transaction payload
  function parsePayloadAndCheckProtocol(bytes29 payload) internal pure returns (address delegator, uint256 fee) {
    require(payload.len() >= 28, "payload length is too small");
    require(payload.indexUint(0, 4) == SatoshiPlusHelper.BTC_STAKE_MAGIC, "wrong magic");
    require(payload.indexUint(5, 2) == SatoshiPlusHelper.CHAINID, "wrong chain id");
    uint32 version = uint32(payload.indexUint(4, 1));
    require(version == SatoshiPlusHelper.BTCLST_STAKE_VERSION, "unsupported sat+ version in btc staking");
    delegator = payload.indexAddress(7);
    fee = payload.indexUint(27, 1);
  }
}
