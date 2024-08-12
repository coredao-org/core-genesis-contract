pragma solidity 0.8.4;

import "../PledgeAgent.sol";

contract PledgeAgentMock is PledgeAgent {
    int256 public constant CLAIM_ROUND_LIMIT = 500;
    uint256 public constant BTC_UNIT_CONVERSION_MOCK = 5;

    event delegatedCoinOld(address indexed agent, address indexed delegator, uint256 amount, uint256 totalAmount);
    event transferredCoinOld(
        address indexed sourceCandidate,
        address indexed targetCandidate,
        address indexed delegator,
        uint256 amount,
        uint256 realAmount
    );
    event transferredBtcOld(
        bytes32 indexed txid,
        address sourceAgent,
        address targetAgent,
        address delegator,
        uint256 amount,
        uint256 totalAmount
    );
    event undelegatedCoinOld(address indexed candidate, address indexed delegator, uint256 amount);
    event roundReward(address indexed agent, uint256 coinReward, uint256 powerReward, uint256 btcReward);
    event delegatedBtcOld(bytes32 indexed txid, address indexed agent, address indexed delegator, bytes script, uint256 btcvalue);

    error InactiveAgent(address candidate);
    error InactiveCandidate(address candidate);
    error SameCandidate(address candidate);

    function developmentInit() external {
        requiredCoinDeposit = requiredCoinDeposit / 1e16;
        btcFactor = 2;
        minBtcLockRound = 3;
        minBtcValue = 100;
        roundTag = 1;
    }

    function setAgentRound(address agent, uint256 power, uint256 coin) external {
    }

    function setAgentReward(address agent, uint index,
        uint256 totalReward,
        uint256 claimedReward,
        uint256 totalScore,
        uint256 coin,
        uint256 power,
        uint256 round) external {}


    function setCoinDelegator(address agent) external {}

    function setBtcDelegator(address agent) external {}

    function getRewardLength(address agent) external view returns (uint) {
        return agentsMap[agent].rewardSet.length;
    }

    function getAgent2valueMap(uint256 round, address agent) external view returns (uint256 value) {
        BtcExpireInfo storage expireInfo = round2expireInfoMap[round];
        value = expireInfo.agent2valueMap[agent];
        return value;
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

    function setPowerFactor(uint newPowerFactor) external {
        powerFactor = newPowerFactor;
    }

    function setBtcFactor(uint newBtcFactor) external {
        btcFactor = newBtcFactor;
    }


    function setRoundTag(uint value) external {
        roundTag = value;
    }

    function undelegateCoinOld(address agent, address delegator, uint256 amount, bool isTransfer) internal returns (uint256, uint256) {
        Agent storage a = agentsMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        uint256 newDeposit = d.newDeposit;
        if (amount == 0) {
            amount = newDeposit;
        }
        require(newDeposit != 0, "delegator does not exist");
        if (newDeposit != amount) {
            require(amount >= requiredCoinDeposit, "undelegate amount is too small");
            require(newDeposit >= requiredCoinDeposit + amount, "remaining amount is too small");
        }
        uint256 rewardAmount = _collectCoinReward(a, d);
        a.totalDeposit -= amount;
        uint256 deposit = d.changeRound < roundTag ? newDeposit : d.deposit;
        newDeposit -= amount;
        uint256 deductedInDeposit;
        uint256 deductedOutDeposit;
        if (newDeposit < d.transferInDeposit) {
            deductedInDeposit = d.transferInDeposit - newDeposit;
            d.transferInDeposit = newDeposit;
            if (!isTransfer) {
                debtDepositMap[roundTag][msg.sender] += deductedInDeposit;
            }
            deductedOutDeposit = deposit;
        } else if (newDeposit < d.transferInDeposit + deposit) {
            deductedOutDeposit = d.transferInDeposit + deposit - newDeposit;
        }
        if (deductedOutDeposit != 0) {
            deposit -= deductedOutDeposit;
            if (a.rewardSet.length != 0) {
                Reward storage r = a.rewardSet[a.rewardSet.length - 1];
                if (r.round == roundTag) {
                    if (isTransfer) {
                        d.transferOutDeposit += deductedOutDeposit;
                    } else {
                        r.coin -= deductedOutDeposit;
                    }
                } else {
                    deductedOutDeposit = 0;
                }
            } else {
                deductedOutDeposit = 0;
            }
        }

        if (newDeposit == 0 && d.transferOutDeposit == 0) {
            delete a.cDelegatorMap[delegator];
        } else {
            d.deposit = deposit;
            d.newDeposit = newDeposit;
            d.changeRound = roundTag;
        }

        if (rewardAmount != 0) {
            distributeRewardMock(payable(delegator), rewardAmount);
        }

        return (amount, deductedInDeposit + deductedOutDeposit);
    }

    function delegateCoinOld(address agent, address delegator, uint256 deposit, uint256 transferInDeposit) internal returns (uint256) {
        require(deposit >= requiredCoinDeposit, "deposit is too small");
        Agent storage a = agentsMap[agent];
        CoinDelegator storage d = a.cDelegatorMap[delegator];
        uint256 rewardAmount;
        if (d.changeRound != 0) {
            rewardAmount = _collectCoinReward(a, d);
        }
        a.totalDeposit += deposit;

        if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
            d.newDeposit = deposit;
            d.changeRound = roundTag;
            d.rewardIndex = a.rewardSet.length;
        } else {
            if (d.changeRound < roundTag) {
                d.deposit = d.newDeposit;
                d.changeRound = roundTag;
            }
            d.newDeposit += deposit;
        }

        if (transferInDeposit != 0) {
            d.transferInDeposit += transferInDeposit;
        }

        if (rewardAmount != 0) {
            distributeRewardMock(payable(delegator), rewardAmount);
        }
        return d.newDeposit;
    }

    function delegateCoinOld(address agent) external payable {
        if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(agent)) {
            revert InactiveAgent(agent);
        }
        uint256 newDeposit = delegateCoinOld(agent, msg.sender, msg.value, 0);
        emit delegatedCoinOld(agent, msg.sender, msg.value, newDeposit);
    }


    function undelegateCoinOld(address agent) external {
        undelegateCoinOld(agent, 0);
    }

    function undelegateCoinOld(address agent, uint256 amount) public {
        (uint256 deposit,) = undelegateCoinOld(agent, msg.sender, amount, false);
        Address.sendValue(payable(msg.sender), deposit);
        emit undelegatedCoinOld(agent, msg.sender, deposit);
    }

    function transferCoinOld(address sourceAgent, address targetAgent) external {
        transferCoin(sourceAgent, targetAgent, 0);
    }

    function transferCoinOld(address sourceAgent, address targetAgent, uint256 amount) public {
        if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent)) {
            revert InactiveAgent(targetAgent);
        }
        if (sourceAgent == targetAgent) {
            revert SameCandidate(sourceAgent);
        }
        (uint256 deposit, uint256 deductedDeposit) = undelegateCoinOld(sourceAgent, msg.sender, amount, true);
        uint256 newDeposit = delegateCoinOld(targetAgent, msg.sender, deposit, deductedDeposit);

        emit transferredCoinOld(sourceAgent, targetAgent, msg.sender, deposit, newDeposit);
    }


    function addExpire(BtcReceipt storage br) internal {
        BtcExpireInfo storage expireInfo = round2expireInfoMap[br.endRound];
        if (expireInfo.agentExistMap[br.agent] == 0) {
            expireInfo.agentAddrList.push(br.agent);
            expireInfo.agentExistMap[br.agent] = 1;
        }
        expireInfo.agent2valueMap[br.agent] += br.value;
    }


    function delegateBtcMock(bytes32 txId, uint256 btcValue, address agent, address delegator, bytes memory script, uint32 lockTime, uint256 fee) external {
        BtcReceipt storage br = btcReceiptMap[txId];
        require(br.value == 0, "btc tx confirmed");
        br.endRound = lockTime / ROUND_INTERVAL;
        br.value = btcValue;
        require(br.value >= (minBtcValue == 0 ? INIT_MIN_BTC_VALUE : minBtcValue), "staked value does not meet requirement");
        br.delegator = delegator;
        br.agent = agent;
        if (!ICandidateHub(CANDIDATE_HUB_ADDR).isCandidateByOperate(br.agent)) {
            revert InactiveAgent(br.agent);
        }
        emit delegatedBtcOld(txId, br.agent, br.delegator, script, btcValue);
        if (fee != 0) {
            br.fee = fee;
            br.feeReceiver = payable(msg.sender);
        }
        Agent storage a = agentsMap[br.agent];
        br.rewardIndex = a.rewardSet.length;
        addExpire(br);
        a.totalBtc += br.value;
    }

    /// @param targetAgent the new validator address to stake to
    function transferBtcOld(bytes32 txid, address targetAgent) external {
        BtcReceipt storage br = btcReceiptMap[txid];
        require(br.value != 0, "btc tx not found");
        require(br.delegator == msg.sender, "not the delegator of this btc receipt");
        address agent = br.agent;
        require(agent != targetAgent, "can not transfer to the same validator");
        require(br.endRound > roundTag + 1, "insufficient locking rounds");
        if (!ICandidateHub(CANDIDATE_HUB_ADDR).canDelegate(targetAgent)) {
            revert InactiveAgent(targetAgent);
        }
        (uint256 reward) = _collectBtcReward(txid);
        Agent storage a = agentsMap[agent];
        a.totalBtc -= br.value;
        round2expireInfoMap[br.endRound].agent2valueMap[agent] -= br.value;

        Reward storage r = a.rewardSet[a.rewardSet.length - 1];
        if (r.round == roundTag && br.rewardIndex < a.rewardSet.length) {
            r.coin -= br.value * stateMap[roundTag].btcFactor;
        }

        Agent storage ta = agentsMap[targetAgent];
        br.agent = targetAgent;
        br.rewardIndex = ta.rewardSet.length;
        addExpire(br);
        ta.totalBtc += br.value;

        if (reward != 0) {
            Address.sendValue(payable(msg.sender), reward);
        }

        emit transferredBtcOld(txid, agent, targetAgent, msg.sender, br.value, ta.totalBtc);
    }

    function distributePowerRewardOld(address candidate, address[] calldata miners) external onlyCandidate {
        Agent storage a = agentsMap[candidate];
        uint256 l = a.rewardSet.length;
        if (l == 0) {
            return;
        }
        Reward storage r = a.rewardSet[l - 1];
        if (r.totalReward == 0 || r.round != roundTag) {
            return;
        }
        RoundState storage rs = stateMap[roundTag];
        uint256 reward = (rs.coin + rs.btc * rs.btcFactor) * POWER_BLOCK_FACTOR * rs.powerFactor / 10000 * r.totalReward / r.score;
        uint256 minerSize = miners.length;

        uint256 powerReward = reward * minerSize;
        uint256 undelegateCoinReward;
        uint256 btcScore = a.btc * rs.btcFactor;
        if (a.coin + btcScore > r.coin) {
            undelegateCoinReward = r.totalReward * (a.coin + btcScore - r.coin) * rs.power / r.score;
        }
        uint256 remainReward = r.remainReward;
        require(remainReward >= powerReward + undelegateCoinReward, "there is not enough reward");

        for (uint256 i = 0; i < minerSize; i++) {
            rewardMap[miners[i]] += reward;
        }

        if (r.coin == 0) {
            delete a.rewardSet[l - 1];
            undelegateCoinReward = remainReward - powerReward;
        } else if (powerReward != 0 || undelegateCoinReward != 0) {
            r.remainReward -= (powerReward + undelegateCoinReward);
        }

        if (undelegateCoinReward != 0) {
            ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{value: undelegateCoinReward}();
        }
    }

    function getHybridScoreOld(
        address[] calldata candidates,
        uint256[] calldata powers,
        uint256 round
    ) external onlyCandidate returns (uint256[] memory scores) {
        uint256 candidateSize = candidates.length;
        require(candidateSize == powers.length, "the length of candidates and powers should be equal");

        for (uint256 r = roundTag + 1; r <= round; ++r) {
            BtcExpireInfo storage expireInfo = round2expireInfoMap[r];
            uint256 j = expireInfo.agentAddrList.length;
            while (j > 0) {
                j--;
                address agent = expireInfo.agentAddrList[j];
                agentsMap[agent].totalBtc -= expireInfo.agent2valueMap[agent];
                expireInfo.agentAddrList.pop();
                delete expireInfo.agent2valueMap[agent];
                delete expireInfo.agentExistMap[agent];
            }
            delete round2expireInfoMap[r];
        }

        uint256 totalPower = 1;
        uint256 totalCoin = 1;
        uint256 totalBtc;
        for (uint256 i = 0; i < candidateSize; ++i) {
            Agent storage a = agentsMap[candidates[i]];
            a.power = powers[i] * POWER_BLOCK_FACTOR;
            a.btc = a.totalBtc;
            a.coin = a.totalDeposit;
            totalPower += a.power;
            totalCoin += a.coin;
            totalBtc += a.btc;
        }

        uint256 bf = (btcFactor == 0 ? INIT_BTC_FACTOR : btcFactor) * BTC_UNIT_CONVERSION_MOCK;
        uint256 pf = powerFactor;

        scores = new uint256[](candidateSize);
        for (uint256 i = 0; i < candidateSize; ++i) {
            Agent storage a = agentsMap[candidates[i]];
            scores[i] = a.power * (totalCoin + totalBtc * bf) * pf / 10000 + (a.coin + a.btc * bf) * totalPower;
        }

        RoundState storage rs = stateMap[round];
        rs.power = totalPower;
        rs.coin = totalCoin;
        rs.powerFactor = pf;
        rs.btc = totalBtc;
        rs.btcFactor = bf;
    }

    function setNewRoundOld(address[] calldata validators, uint256 round) external onlyCandidate {
        RoundState storage rs = stateMap[round];
        uint256 validatorSize = validators.length;
        for (uint256 i = 0; i < validatorSize; ++i) {
            Agent storage a = agentsMap[validators[i]];
            uint256 btcScore = a.btc * rs.btcFactor;
            uint256 score = a.power * (rs.coin + rs.btc * rs.btcFactor) * rs.powerFactor / 10000 + (a.coin + btcScore) * rs.power;
            a.rewardSet.push(Reward(0, 0, score, a.coin + btcScore, round));
        }

        roundTag = round;
    }

    function addRoundRewardOld(address[] calldata agentList, uint256[] calldata rewardList)
    external
    payable
    onlyValidator
    {
        uint256 agentSize = agentList.length;
        require(agentSize == rewardList.length, "the length of agentList and rewardList should be equal");
        RoundState memory rs = stateMap[roundTag];
        for (uint256 i = 0; i < agentSize; ++i) {
            Agent storage a = agentsMap[agentList[i]];
            if (a.rewardSet.length == 0) {
                continue;
            }
            Reward storage r = a.rewardSet[a.rewardSet.length - 1];
            uint256 roundScore = r.score;
            if (roundScore == 0) {
                delete a.rewardSet[a.rewardSet.length - 1];
                continue;
            }
            if (rewardList[i] == 0) {
                continue;
            }
            r.totalReward = rewardList[i];
            r.remainReward = rewardList[i];
            uint256 coinReward = rewardList[i] * a.coin * rs.power / roundScore;
            uint256 powerReward = rewardList[i] * a.power * rs.coin / 10000 * rs.powerFactor / roundScore;
            uint256 btcReward = rewardList[i] * a.btc * rs.btcFactor * rs.power / roundScore;
            emit roundReward(agentList[i], coinReward, powerReward, btcReward);
        }
    }
    /*********************** Internal methods ***************************/
    function distributeRewardMock(address payable delegator, uint256 reward) internal {
        Address.sendValue(delegator, reward);
        emit claimedReward(delegator, msg.sender, reward, true);
    }

    function collectCoinRewardMock(Reward storage r, uint256 deposit) internal returns (uint256 rewardAmount) {
        require(r.coin >= deposit, "reward is not enough");
        uint256 curReward;
        if (r.coin == deposit) {
            curReward = r.remainReward;
            r.coin = 0;
        } else {
            uint256 rsPower = stateMap[r.round].power;
            curReward = (r.totalReward * deposit * rsPower) / r.score;
            require(r.remainReward >= curReward, "there is not enough reward");
            r.coin -= deposit;
            r.remainReward -= curReward;
        }
        return curReward;
    }

    function collectCoinRewardMock(Agent storage a, CoinDelegator storage d, int256 roundLimit) internal returns (uint256 rewardAmount) {
        uint256 changeRound = d.changeRound;
        uint256 curRound = roundTag;
        if (changeRound < curRound) {
            d.transferInDeposit = 0;
        }

        uint256 rewardLength = a.rewardSet.length;
        uint256 rewardIndex = d.rewardIndex;
        if (rewardIndex >= rewardLength) {
            return 0;
        }
        if (rewardIndex + uint256(roundLimit) < rewardLength) {
            rewardLength = rewardIndex + uint256(roundLimit);
        }

        while (rewardIndex < rewardLength) {
            Reward storage r = a.rewardSet[rewardIndex];
            uint256 rRound = r.round;
            if (rRound == curRound) {
                break;
            }
            uint256 deposit = d.newDeposit;
            // HARDFORK V-1.0.3  
            // d.deposit and d.transferOutDeposit are both eligible for claiming rewards
            // however, d.transferOutDeposit will be used to pay the DEBT for the delegator before that
            // the rewards from the DEBT will be collected and sent to the system reward contract
            if (rRound == changeRound) {
                uint256 transferOutDeposit = d.transferOutDeposit;
                uint256 debt = debtDepositMap[rRound][msg.sender];
                if (transferOutDeposit > debt) {
                    transferOutDeposit -= debt;
                    debtDepositMap[rRound][msg.sender] = 0;
                } else {
                    debtDepositMap[rRound][msg.sender] -= transferOutDeposit;
                    transferOutDeposit = 0;
                }
                if (transferOutDeposit != d.transferOutDeposit) {
                    uint256 undelegateReward = collectCoinRewardMock(r, d.transferOutDeposit - transferOutDeposit);
                    if (r.coin == 0) {
                        delete a.rewardSet[rewardIndex];
                    }
                    ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{value: undelegateReward}();
                }
                deposit = d.deposit + transferOutDeposit;
                d.deposit = d.newDeposit;
                d.transferOutDeposit = 0;
            }
            if (deposit != 0) {
                rewardAmount += collectCoinRewardMock(r, deposit);
                if (r.coin == 0) {
                    delete a.rewardSet[rewardIndex];
                }
            }
            rewardIndex++;
        }

        // update index whenever claim happens
        d.rewardIndex = rewardIndex;
        return rewardAmount;
    }

    /// Claim reward for delegator
    /// @param agentList The list of validators to claim rewards on, it can be empty
    /// @return (Amount claimed, Are all rewards claimed)
    function claimRewardMock(address[] calldata agentList) external returns (uint256, bool) {
        // limit round count to control gas usage
        int256 roundLimit = CLAIM_ROUND_LIMIT;
        uint256 reward;
        uint256 rewardSum = rewardMap[msg.sender];
        if (rewardSum != 0) {
            rewardMap[msg.sender] = 0;
        }

        uint256 agentSize = agentList.length;
        for (uint256 i = 0; i < agentSize; ++i) {
            Agent storage a = agentsMap[agentList[i]];
            if (a.rewardSet.length == 0) {
                continue;
            }
            CoinDelegator storage d = a.cDelegatorMap[msg.sender];
            if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
                continue;
            }
            int256 roundCount = int256(a.rewardSet.length - d.rewardIndex);
            reward = collectCoinRewardMock(a, d, roundLimit);
            roundLimit -= roundCount;
            rewardSum += reward;
            if (d.newDeposit == 0 && d.transferOutDeposit == 0) {
                delete a.cDelegatorMap[msg.sender];
            }
            // if there are rewards to be collected, leave them there
            if (roundLimit < 0) {
                break;
            }
        }
        if (rewardSum != 0) {
            distributeRewardMock(payable(msg.sender), rewardSum);
        }
        return (rewardSum, roundLimit >= 0);
    }
}
