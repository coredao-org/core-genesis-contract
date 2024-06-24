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
  
  
  /* Barney and Oscar's Code */

  uint256 public constant ROUND_INTERVAL = 86400;
  uint256 public constant BTC_DECIMAL = 1e8;

  uint256 public lastRewardDistribution;
  IPledgeAgent public pledgeAgent;

  event distributedReward(uint256 reward, uint256 roundTag);

  constructor(address _pledgeAgent) {
    pledgeAgent = IPledgeAgent(_pledgeAgent);
    lastRewardDistribution = block.timestamp;
  }

  modifier onlyPldegeAgent() {
    require(msg.sender == address(pledgeAgent), "only pledge agent can call this function");
    _;
  }

  // implement a way to talk to the consensus engine, and figure out who is staking btc to get LST tokens
    // LST contracts are a black box from the perspective of the protocol contracts, so we need to figure out who's LSTing (we dont get told this)


  // implement a way for the CORE protocol to call a (payable?) function and send in a bunch of Core rewards (probably at the end of each round)

  // implement a function for the LST protocol that distributes the rewards based 


  /* end Barney and Oscar's code */
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
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
    //get the CORE evm address that the user chose to get the lst tokens sent to, out of the bitcoin transaction
    delegator = payload.indexAddress(7);
  }


/*
Function for the delegator or the relayer to tell the LST contract they've deposited BTC, and then the delegator gets LST tokens
*/
  function delegate(bytes memory payload, bytes memory script, uint256 value) external onlyBtcAgent {

    address delegator = parsePayload(payload);

    require(IRelayerHub(RELAYER_HUB_ADDR).isRelayer(msg.sender), "only delegator or relayer can submit the BTC transaction");

    
    lstToken.mint(delegator, value);
  }


/*
Function for the validator to burn the LST token and get the BTC back
*/
  function undelegate(bytes btctx) external onlyBtcAgent {
    // TODO mark a burn workflow finish
    bytes[] lockscripts;
    uint256[] amounts;
    for btctx.vout {
       lockscripts.push(vout[i].pkscript)
       amounts.push(vout[i].value)
    }
    //whos tokens are being burned here? shouldn't the user begin the undelegate process by burning the LST tokens?
    lstToken.burn(lockscripts, amounts); 
  }

  function distributeReward(uint256 reward, uint256 roundTag) external payable onlyPldegeAgent {
    require(block.timestamp - lastRewardDistribution >= ROUND_INTERVAL, "reward distribution interval too short");
    lastRewardDistribution = block.timestamp;
    
    rewardPerBTC[roundTag] += rewardPerBTC[lastRoundTag] + reward * BTC_DECIMAL / totalAmount;
    lastRoundTag = roundTag;

    emit distributedReward(reward, roundTag);
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
