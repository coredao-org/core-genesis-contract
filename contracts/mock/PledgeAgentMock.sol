// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../PledgeAgent.sol";
import "../interface/ICandidateHub.sol";

contract PledgeAgentMock is PledgeAgent {
    int256 public constant CLAIM_ROUND_LIMIT = 500;
    uint256 public constant BTC_UNIT_CONVERSION_MOCK = 5;
    uint256 public constant ROUND_INTERVAL = 86400;
    uint256 public constant BTC_STAKE_MAGIC = 0x5341542b;
    uint256 public constant CHAINID = 1116;
    uint256 public constant BTC_UNIT_CONVERSION = 1e10;
    uint256 public constant INIT_DELEGATE_BTC_GAS_PRICE = 1e12;
    
    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
        btcFactor = 2;
        roundTag = 1;
        alreadyInit = true;
    }

    function setAgentRound(address agent, uint256 power, uint256 coin) external {
    }

    function setRewardMap(address account, uint256 value) external {
        rewardMap[account] = value;
    }


    function getAgentAddrList(uint256 round) external view returns (address[] memory) {
        BtcExpireInfo storage expireInfo = round2expireInfoMap[round];
        uint256 length = expireInfo.agentAddrList.length;
        address[] memory agentAddresses = new address[](length);
        for (uint256 i = 0; i < length; i++) {
            agentAddresses[i] = expireInfo.agentAddrList[i];
        }
        return agentAddresses;
    }


    function getDebtDepositMap(uint256 rRound, address delegator) external view returns (uint) {
        uint256 debt = debtDepositMap[rRound][delegator];
        return debt;
    }

    function setRoundTag(uint value) external {
        roundTag = value;
    }

}
