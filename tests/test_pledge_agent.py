import time

import pytest
from web3 import Web3
import brownie
from brownie import *
from .common import register_candidate, turn_round, stake_hub_claim_reward, get_current_round, set_round_tag
from .delegate import *
from .utils import get_tracker, random_address, expect_event, update_system_contract_address
from .calc_reward import *

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
TOTAL_REWARD = 0
ONE_ETHER = Web3.to_wei(1, 'ether')
TX_FEE = 100
DELEGATE_VALUE = 2000000
BTC_VALUE = 200
FEE = 0
# BTC delegation-related
LOCK_TIME = 1736956800
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
# BTCLST delegation-related
BTCLST_LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
BTCLST_REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-12].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_min_init_delegate_value(min_init_delegate_value):
    global MIN_INIT_DELEGATE_VALUE
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, pledge_agent, stake_hub, core_agent, btc_stake, btc_lst_stake, gov_hub):
    global BLOCK_REWARD, TOTAL_REWARD
    global PLEDGE_AGENT, STAKE_HUB, BTC_STAKE, CORE_AGENT
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    PLEDGE_AGENT = pledge_agent
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    BTC_STAKE = btc_stake
    set_block_time_stamp(150, LOCK_TIME)
    btc_lst_stake.updateParam('add', BTCLST_LOCK_SCRIPT, {'from': gov_hub.address})


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_reinit(pledge_agent):
    with brownie.reverts("the contract already init"):
        pledge_agent.init()


@pytest.mark.parametrize("store_old_data", [True, False])
def test_delegate_coin(pledge_agent, set_candidate, store_old_data: bool):
    operators, consensuses = set_candidate
    if store_old_data:
        pledge_agent.delegateCoinOld(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
        __old_turn_round()
        __old_turn_round(consensuses)
        tx = pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
        assert 'delegatedCoin' in tx.events
        tx = pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
        assert 'delegatedCoin' in tx.events
    else:
        tx = pledge_agent.delegateCoin(operators[0], {"value": web3.to_wei(1, 'ether')})
        assert 'delegatedCoin' in tx.events


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_reentry_stake_hub_claim(pledge_agent, stake_hub, set_candidate, validator_set, operate):
    operators, consensuses = set_candidate
    reentry_ = ClaimRewardReentry.deploy(pledge_agent.address, stake_hub, {'from': accounts[0]})
    accounts[2].transfer(reentry_, ONE_ETHER)
    accounts[2].transfer(stake_hub, ONE_ETHER)
    old_delegate_coin_success(operators[0], reentry_, MIN_INIT_DELEGATE_VALUE)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    if operate == 'delegate':
        tx = reentry_.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    elif operate == 'undelegate':
        tx = reentry_.undelegateCoin(operators[0])
    elif operate == 'transfer':
        tx = reentry_.transferCoin(operators[0], operators[1])
    else:
        tx = reentry_.claimReward([operators[0]])
    assert tx.events['claimedReward']['amount'] == TOTAL_REWARD
    assert len(tx.events['claimedReward']) == 1


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_reentry_pledge_agent_claim(pledge_agent, stake_hub, set_candidate, validator_set, operate):
    operators, consensuses = set_candidate
    reentry_ = OldClaimRewardReentry.deploy(pledge_agent.address, stake_hub, {'from': accounts[0]})
    accounts[2].transfer(reentry_, ONE_ETHER)
    accounts[2].transfer(pledge_agent, ONE_ETHER)
    old_delegate_coin_success(operators[0], reentry_, MIN_INIT_DELEGATE_VALUE)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    reentry_.setAgents(operators)
    after = reentry_.balance()
    amount = 0
    if operate == 'delegate':
        tx = reentry_.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
        assert tx.events['proxyDelegate']['success'] is False
        amount = MIN_INIT_DELEGATE_VALUE
    elif operate == 'undelegate':
        tx = reentry_.undelegateCoin(operators[0])
        assert tx.events['proxyUndelegate']['success'] is False
    elif operate == 'transfer':
        tx = reentry_.transferCoin(operators[0], operators[1])
        assert len(tx.events) == 0
    else:
        tx = reentry_.claimReward([operators[0]])
        assert len(tx.events) == 0
    assert reentry_.balance() == after + amount


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer'])
def test_auto_issue_historical_rewards(pledge_agent, set_candidate, core_agent, operate):
    old_turn_round()
    operators, consensuses = set_candidate
    pledge_agent.delegateCoinOld(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    if operate == 'delegate':
        tx = old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE, False)
    elif operate == 'undelegate':
        tx = old_undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE, False)
    else:
        tx = old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE, False)
    assert tx.events['claimedReward']['amount'] == TOTAL_REWARD


@pytest.mark.parametrize("is_validator", [True, False])
@pytest.mark.parametrize("partial", [True, False])
def test_undelegate_coin(pledge_agent, candidate_hub, is_validator: bool, partial: bool):
    operators = accounts[1:3]
    consensus = []
    for operator in operators:
        consensus.append(register_candidate(operator=operator))
        pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    __old_turn_round()
    __old_turn_round(consensus)
    __init_hybrid_score_mock()
    turn_round(round_count=2)

    undelegate_amount = MIN_INIT_DELEGATE_VALUE if partial else 0
    if is_validator:
        pledge_agent.undelegateCoin(operators[0], undelegate_amount)
        if partial:
            tx = pledge_agent.undelegateCoin(operators[0], undelegate_amount)
            assert 'undelegatedCoin' in tx.events
    else:
        candidate_hub.refuseDelegate({'from': operators[0]})
        turn_round()
        candidate_hub.unregister({'from': operators[0]})
        turn_round()
        pledge_agent.undelegateCoin(operators[0], undelegate_amount)
        if partial:
            tx = pledge_agent.undelegateCoin(operators[0], undelegate_amount)
            assert 'undelegatedCoin' in tx.events


@pytest.mark.parametrize("is_validator", [True, False])
@pytest.mark.parametrize("partial", [True, False])
def test_transfer_coin(pledge_agent, candidate_hub, is_validator: bool, partial: bool):
    operators = accounts[1:3]
    consensus = []
    for operator in operators:
        consensus.append(register_candidate(operator=operator))
        pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    __old_turn_round()
    __old_turn_round(consensus)
    __init_hybrid_score_mock()
    turn_round(round_count=2)

    transfer_amount = MIN_INIT_DELEGATE_VALUE if partial else 0
    if is_validator:
        tx = pledge_agent.transferCoin(operators[0], operators[1], transfer_amount)
        assert 'transferredCoin' in tx.events

        if partial:
            tx = pledge_agent.transferCoin(operators[0], operators[1], transfer_amount)
            assert 'transferredCoin' in tx.events
    else:
        candidate_hub.refuseDelegate({'from': operators[0]})
        turn_round()
        candidate_hub.unregister({'from': operators[0]})
        turn_round()
        tx = pledge_agent.transferCoin(operators[0], operators[1], transfer_amount)
        assert 'transferredCoin' in tx.events

        if partial:
            tx = pledge_agent.transferCoin(operators[0], operators[1], transfer_amount)
            assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("agents_type", ["empty", "all", "partial", "none"])
def test_claim_reward(pledge_agent, candidate_hub, agents_type: str):
    operators = accounts[1:4]
    consensus = []
    for operator in operators:
        consensus.append(register_candidate(operator=operator))
        pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    __old_turn_round(consensus)
    __init_hybrid_score_mock()
    turn_round(round_count=2)
    actual_reward = 0
    event_length = 0
    if agents_type == "empty":
        tx = pledge_agent.claimReward([])
        assert len(tx.events) == 0
    elif agents_type == "all":
        tx = pledge_agent.claimReward(operators)
        actual_reward = TOTAL_REWARD * 3
        event_length = 1
    elif agents_type == "none":
        tx = pledge_agent.claimReward([random_address()])
        assert len(tx.events) == 0
    else:
        event_length = 1
        tx = pledge_agent.claimReward(operators[:2] + [random_address()])
        actual_reward = TOTAL_REWARD * 2
    if event_length == 1:
        assert tx.events['claimedReward']['amount'] == actual_reward


def test_claim_reward_success(btc_agent, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT, percentage=Utils.DENOMINATOR)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    actual_reward = TOTAL_REWARD * 3
    pledge_agent.claimReward(operators)
    assert tracker.delta() == actual_reward - FEE


def test_claim_reward_validator_address_empty(btc_agent, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT, percentage=Utils.DENOMINATOR)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    actual_reward = TOTAL_REWARD * 3
    pledge_agent.claimReward([])
    assert tracker.delta() == actual_reward


def test_claim_validator_reward_individually(btc_agent, pledge_agent, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    __old_turn_round()
    for op in operators[:2]:
        old_delegate_coin_success(op, accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    old_transfer_coin_success(operators[0], operators[2], accounts[0], undelegate_amount)
    __init_hybrid_score_mock()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    old_claim_reward_success(operators[:1], accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2


@pytest.mark.parametrize("agents_type", ["empty", "all", "partial", "none"])
def test_calculate_reward(pledge_agent, candidate_hub, agents_type: str):
    operators = accounts[1:4]
    consensus = []
    for operator in operators:
        consensus.append(register_candidate(operator=operator))
        pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    __old_turn_round(consensus)
    __init_hybrid_score_mock()
    turn_round(round_count=2)
    actual_reward = 0
    calc_reward = 0
    if agents_type == "empty":
        calc_reward = pledge_agent.calculateReward([], accounts[0])
    elif agents_type == "all":
        calc_reward = pledge_agent.calculateReward(operators, accounts[0])
        actual_reward = TOTAL_REWARD * 3
    elif agents_type == "none":
        calc_reward = pledge_agent.calculateReward([random_address()], accounts[0])
    elif agents_type == "partial":
        calc_reward = pledge_agent.calculateReward(operators[:2] + [random_address()], accounts[0])
        actual_reward = TOTAL_REWARD * 2
    assert calc_reward.return_value == actual_reward


@pytest.mark.parametrize("operate", [
    ['undelegate', 'delegate'],
    ['delegate', 'undelegate'],
    ['delegate', 'transfer'],
    ['transfer', 'undelegate'],
    ['delegate', 'delegate', 'transfer'],
    ['delegate', 'delegate', 'undelegate'],
    ['undelegate', 'transfer', 'delegate'],
    ['undelegate', 'undelegate', 'delegate'],
    ["delegate", "undelegate", "transfer"],
    ['transfer', 'undelegate', 'delegate'],
    ['undelegate', 'transfer', 'delegate'],
    ['delegate', 'delegate', 'undelegate', 'undelegate'],
    ['undelegate', 'delegate', 'transfer', 'transfer'],
    ['transfer', 'transfer', 'delegate', 'undelegate']
])
def test_calculate_reward_withdraw_transfer_reward(pledge_agent, set_candidate, operate):
    operators, consensus = set_candidate
    for index, op in enumerate(operators):
        old_delegate_coin_success(op, accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    total_undelegate_amount = 0
    delegate_count = []
    for index, o in enumerate(operate):
        if o == 'delegate':
            tx = old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
            assert 'delegatedCoinOld' in tx.events
            delegate_count.append(index)
        elif o == 'undelegate':
            if len(delegate_count) == 0:
                total_undelegate_amount += MIN_INIT_DELEGATE_VALUE
            else:
                delegate_count.pop()
            tx = old_undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
            assert 'undelegatedCoinOld' in tx.events
        elif o == 'transfer':
            tx = old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
            assert 'transferredCoinOld' in tx.events
    __old_turn_round(consensus)
    __init_hybrid_score_mock()
    debt_reward = (TOTAL_REWARD * total_undelegate_amount // (MIN_INIT_DELEGATE_VALUE * 2))
    calc_reward = pledge_agent.calculateReward(operators, accounts[0])
    assert calc_reward.return_value == TOTAL_REWARD * 3 - debt_reward


def test_claim_btc_reward(pledge_agent, btc_stake):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()

    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    agent = operator
    delegator = accounts[0]
    script = "0x1234"
    lock_time = int(time.time()) + 3600
    fee = 0
    pledge_agent.delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)
    __old_turn_round()
    __old_turn_round([consensus])
    __init_hybrid_score_mock()
    tx = pledge_agent.claimBtcReward([tx_id])
    expect_event(tx, "claimedReward")


@pytest.mark.parametrize("success", [True, False])
def test_move_btc_data_then_claim_btc_reward(pledge_agent, btc_stake, success):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    agent = operator
    delegator = accounts[0]
    script = "0x1234"
    lock_time = int(time.time()) + 3600
    fee = 0
    pledge_agent.delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)
    __old_turn_round()
    __old_turn_round([consensus])
    __init_hybrid_score_mock()
    tx_ids = []
    if success:
        tx_ids.append(tx_id)
        __move_btc_data([tx_id])
        with brownie.reverts("btc tx not found"):
            pledge_agent.claimBtcReward(tx_ids)
    else:
        tx = pledge_agent.claimBtcReward(tx_ids)
        assert len(tx.events) == 0


def test_only_btc_stake_can_call(pledge_agent, btc_stake):
    with brownie.reverts("the msg sender must be bitcoin stake contract"):
        pledge_agent.moveBtcData(random_btc_tx_id(), {'from': accounts[0]})


def test_move_btc_data(pledge_agent, btc_stake):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    agent = operator
    delegator = accounts[0]
    script = "0x1234"
    lock_time = int(time.time()) + 3600
    fee = 0
    pledge_agent.delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)
    __old_turn_round()
    __old_turn_round([consensus])
    update_system_contract_address(pledge_agent, btc_stake=accounts[0])
    candidate, delegator, amount, round, lockTime = pledge_agent.moveBtcData(tx_id, {'from': accounts[0]}).return_value
    assert candidate == agent
    assert delegator == accounts[0]
    assert amount == btc_value
    assert lock_time // Utils.ROUND_INTERVAL * Utils.ROUND_INTERVAL == lockTime
    assert round == get_current_round() - 1
    assert pledge_agent.rewardMap(delegator) == TOTAL_REWARD // 2 * 2


def test_tx_id_not_found(pledge_agent, btc_stake):
    tx_id = random_btc_tx_id()
    update_system_contract_address(pledge_agent, btc_stake=accounts[0])
    candidate, delegator, amount, round, lock_time = pledge_agent.moveBtcData(tx_id, {'from': accounts[0]}).return_value
    assert candidate == delegator == ZERO_ADDRESS
    assert amount == round == lock_time == 0


def test_multiple_txids_end_round(pledge_agent, btc_stake, set_candidate):
    operators, consensuses = set_candidate
    pledge_agent.delegateCoinOld(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    lock_time = int(time.time()) + 3600
    set_round_tag(lock_time // Utils.ROUND_INTERVAL - 3)
    __old_turn_round()
    round_tag = get_current_round()
    btc_value = 1000000
    script = "0x1234"
    fee = 0
    tx_ids0 = []
    tx_ids1 = []
    for index, op in enumerate(operators):
        tx_id0 = random_btc_tx_id()
        tx_id1 = random_btc_tx_id()
        pledge_agent.delegateBtcMock(tx_id0, btc_value + index, op, accounts[0], script, lock_time, fee)
        pledge_agent.delegateBtcMock(tx_id1, btc_value + index, op, accounts[1], script, lock_time, fee)
        tx_ids0.append(tx_id0)
        tx_ids1.append(tx_id1)
    __old_turn_round()
    assert pledge_agent.getAgent2valueMap(round_tag + 2, operators[0]) == btc_value * 2
    assert len(pledge_agent.getAgentAddrList(round_tag + 2)) == 3
    update_system_contract_address(pledge_agent, btc_stake=accounts[0])
    candidate, delegator, amount, _, _ = pledge_agent.moveBtcData(tx_ids0[0], {'from': accounts[0]}).return_value
    assert pledge_agent.getAgent2valueMap(round_tag + 2, operators[0]) == btc_value
    assert len(pledge_agent.getAgentAddrList(round_tag + 2)) == 3
    candidate, delegator, amount, round, _ = pledge_agent.moveBtcData(tx_ids1[0], {'from': accounts[0]}).return_value
    assert pledge_agent.getAgent2valueMap(round_tag + 2, operators[0]) == 0
    assert len(pledge_agent.getAgentAddrList(round_tag + 2)) == 2


def test_move_transferred_btc(pledge_agent, btc_stake, set_candidate):
    operators, consensuses = set_candidate
    pledge_agent.delegateCoinOld(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    btc_value = 1000000
    script = "0x1234"
    fee = 0
    tx_id = random_btc_tx_id()
    pledge_agent.delegateBtcMock(tx_id, btc_value, operators[0], accounts[0], script, LOCK_TIME, fee)
    __old_turn_round()
    old_trannsfer_btc_success(tx_id, operators[1])
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    update_system_contract_address(pledge_agent, btc_stake=accounts[0])
    candidate, delegator, amount, _, _ = pledge_agent.moveBtcData(tx_id, {'from': accounts[0]}).return_value
    assert pledge_agent.rewardMap(delegator) == TOTAL_REWARD


def test_move_candidate_data(pledge_agent, core_agent, btc_stake, btc_agent, candidate_hub):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})

    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    agent = operator
    delegator = accounts[0]
    script = "0x1234"
    lock_time = int(time.time()) + 3600
    fee = 0
    pledge_agent.delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)

    __old_turn_round()
    assert operator in candidate_hub.getCandidates()
    __old_turn_round([consensus])

    pledge_agent.moveCandidateData([operator])
    agent = pledge_agent.agentsMap(operator)
    assert agent[-1] is True

    candidate_in_core_agent = core_agent.candidateMap(operator)
    assert candidate_in_core_agent[0] == MIN_INIT_DELEGATE_VALUE
    assert candidate_in_core_agent[1] == MIN_INIT_DELEGATE_VALUE

    candidate_in_btc_stake = btc_stake.candidateMap(operator)
    assert candidate_in_btc_stake[0] == btc_value
    assert candidate_in_btc_stake[1] == btc_value

    candidate_in_btc_agent = btc_agent.candidateMap(operator)
    assert candidate_in_btc_agent[1] == btc_value


def test_move_expired_btc_stake(pledge_agent, core_agent, btc_agent, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    delegator = accounts[0]
    script = "0x1234"
    fee = 0
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    pledge_agent.delegateBtcMock(tx_id, btc_value, operators[1], delegator, script, LOCK_TIME, fee)
    __old_turn_round()
    __old_turn_round(consensuses, round_count=2)
    pledge_agent.moveCandidateData(operators)
    for op in operators:
        agent_map = pledge_agent.agentsMap(op)
        assert agent_map['moved'] is False


def test_move_candidate_no_stake(pledge_agent, core_agent, btc_agent, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    __old_turn_round()
    __old_turn_round(consensuses, round_count=2)
    pledge_agent.moveCandidateData(operators)
    for op in operators:
        agent_map = pledge_agent.agentsMap(op)
        assert agent_map['moved'] is False


def test_move_candidate_all_moved(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    for index, op in enumerate(operators):
        old_delegate_coin_success(op, accounts[0], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round()
    __old_turn_round(consensuses, round_count=2)
    pledge_agent.moveCandidateData(operators[:2])
    for op in operators[:2]:
        agent_map = pledge_agent.agentsMap(op)
        assert agent_map['moved'] is True
        __check_candidate_map_info(op, {
            'amount': MIN_INIT_DELEGATE_VALUE,
            'realtimeAmount': MIN_INIT_DELEGATE_VALUE
        })
    __check_candidate_map_info(operators[2], {
        'amount': 0,
        'realtimeAmount': 0
    })
    pledge_agent.moveCandidateData([operators[2]])
    for op in operators:
        __check_candidate_map_info(op, {
            'amount': MIN_INIT_DELEGATE_VALUE,
            'realtimeAmount': MIN_INIT_DELEGATE_VALUE
        })


@pytest.mark.parametrize("coin", [True, False])
def test_single_stake_data_move_success(pledge_agent, set_candidate, coin):
    operators, consensuses = set_candidate
    btc_value = 1000000
    for index, op in enumerate(operators):
        if coin:
            old_delegate_coin_success(op, accounts[0], MIN_INIT_DELEGATE_VALUE + index)
        else:
            old_delegate_btc_success(btc_value + index, op, accounts[1])
    __old_turn_round()
    pledge_agent.moveCandidateData(operators)
    for index, op in enumerate(operators):
        agent_map = pledge_agent.agentsMap(op)
        assert agent_map['moved'] is True
        if coin:
            __check_candidate_map_info(op, {
                'amount': MIN_INIT_DELEGATE_VALUE + index,
                'realtimeAmount': MIN_INIT_DELEGATE_VALUE + index
            })
        else:
            __check_btc_candidate_map_info(op, {
                'stakedAmount': btc_value + index,
                'realtimeAmount': btc_value + index
            })


def test_move_candidate_success(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    btc_value = 1000000
    for index, op in enumerate(operators):
        old_delegate_coin_success(op, accounts[0], MIN_INIT_DELEGATE_VALUE + index)
        old_delegate_btc_success(btc_value + index, op, accounts[1])
    __old_turn_round()
    __old_turn_round(consensuses)
    pledge_agent.moveCandidateData(operators)
    for index, op in enumerate(operators):
        agent_map = pledge_agent.agentsMap(op)
        assert agent_map['moved'] is True
        __check_candidate_map_info(op, {
            'amount': MIN_INIT_DELEGATE_VALUE + index,
            'realtimeAmount': MIN_INIT_DELEGATE_VALUE + index
        })
        __check_btc_candidate_map_info(op, {
            'stakedAmount': btc_value + index,
            'realtimeAmount': btc_value + index
        })


def test_move_core_data(pledge_agent, core_agent):
    operator = accounts[1]
    operator2 = accounts[2]
    consensus = register_candidate(operator=operator)
    register_candidate(operator=operator2)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    pledge_agent.delegateCoinOld(operator2, {"value": MIN_INIT_DELEGATE_VALUE})
    __old_turn_round()
    __old_turn_round([consensus])
    tracker = get_tracker(accounts[0])
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    pledge_agent.transferCoinOld(operator, operator2, MIN_INIT_DELEGATE_VALUE * 2)
    assert tracker.delta() == TOTAL_REWARD - MIN_INIT_DELEGATE_VALUE
    __init_hybrid_score_mock()
    turn_round([consensus])
    turn_round([consensus])
    pledge_agent.moveCOREData(operator, accounts[0])
    old_claim_reward_success([operator], accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 2
    delegator_info_in_core_agent = core_agent.getDelegator(operator, accounts[0])
    _staked_amount, _realtime_amount, _transferred_amount, changeRound = delegator_info_in_core_agent
    assert _staked_amount == MIN_INIT_DELEGATE_VALUE
    assert _realtime_amount == MIN_INIT_DELEGATE_VALUE
    assert _transferred_amount == 0
    assert changeRound == get_current_round()


@pytest.mark.parametrize("round", [0, 1, 2, 3])
def test_move_core_success(pledge_agent, core_agent, set_candidate, round):
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    old_delegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round()
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    round_tag = 9
    set_round_tag(round_tag)
    turn_round(consensuses, round_count=round)
    if round == 0:
        change_round = get_current_round()
    else:
        change_round = get_current_round()
    pledge_agent.moveCOREData(operators[0], accounts[0])
    __check_delegate_info(operators[0], accounts[0], {
        'stakedAmount': MIN_INIT_DELEGATE_VALUE * 2,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE * 2,
        'changeRound': change_round,
        'transferredAmount': 0,
    })
    reward_map = __get_reward_map_info(accounts[0])
    assert reward_map == [TOTAL_REWARD * round, MIN_INIT_DELEGATE_VALUE * 2 * round]
    __check_old_delegate_info(operators[0], accounts[0], {
        'changeRound': 0
    })


def test_repeat_move_core_data(pledge_agent, core_agent, set_candidate):
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    old_delegate_coin_success(operators[1], accounts[1], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    for i in range(3):
        pledge_agent.moveCOREData(operators[0], accounts[0])
    __check_delegate_info(operators[0], accounts[0], {
        'stakedAmount': MIN_INIT_DELEGATE_VALUE * 2,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE * 2,
        'changeRound': core_agent.roundTag(),
        'transferredAmount': 0,
    })
    tracker = get_tracker(accounts[0])
    pledge_agent.claimReward(operators)
    assert tracker.delta() == TOTAL_REWARD
    turn_round(consensuses)
    pledge_agent.moveCOREData(operators[0], accounts[0])
    pledge_agent.claimReward([])
    assert tracker.delta() == TOTAL_REWARD


def test_move_core_data_with_reward(pledge_agent, core_agent, set_candidate):
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    pledge_agent.moveCOREData(operators[0], accounts[0])
    __check_delegate_info(operators[0], accounts[0], {
        'stakedAmount': MIN_INIT_DELEGATE_VALUE,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE,
        'changeRound': core_agent.roundTag(),
        'transferredAmount': 0,
    })
    tracker = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0]])
    assert tracker.delta() == TOTAL_REWARD
    turn_round(consensuses)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert len(candidate_list) == 1
    pledge_agent.moveCOREData(operators[1], accounts[0])
    __check_delegate_info(operators[1], accounts[0], {
        'stakedAmount': MIN_INIT_DELEGATE_VALUE,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE,
        'changeRound': get_current_round(),
        'transferredAmount': 0,
    })


def test_cancel_move_data_after_transfer(pledge_agent, core_agent, set_candidate):
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    old_undelegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    pledge_agent.moveCOREData(operators[0], accounts[0])
    __check_delegate_info(operators[0], accounts[0], {
        'stakedAmount': MIN_INIT_DELEGATE_VALUE,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE,
        'changeRound': core_agent.roundTag(),
        'transferredAmount': 0,
    })
    tracker = get_tracker(accounts[0])
    pledge_agent.claimReward(operators)
    assert tracker.delta() == TOTAL_REWARD - TOTAL_REWARD // 2
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD


def test_move_core_data_check_acc_stake_amount(pledge_agent, stake_hub, core_agent, set_candidate):
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    old_undelegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    pledge_agent.moveCOREData(operators[0], accounts[0])
    __check_core_reward_map(accounts[0], {
        'reward': 0,
        'accStakedAmount': 0
    })
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward_map = core_agent.claimReward.call(accounts[0], 0)
    assert reward_map == [TOTAL_REWARD, 0, MIN_INIT_DELEGATE_VALUE]
    update_system_contract_address(core_agent, stake_hub=stake_hub)
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward_map = core_agent.claimReward.call(accounts[0], 0)
    assert reward_map == [TOTAL_REWARD * 2, 0, MIN_INIT_DELEGATE_VALUE * 2]
    update_system_contract_address(core_agent, stake_hub=stake_hub)
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward_map = core_agent.claimReward.call(accounts[0], 0)
    assert reward_map == [TOTAL_REWARD, 0, MIN_INIT_DELEGATE_VALUE]


def test_stake_current_round_move_core_no_reward(pledge_agent, stake_hub, core_agent, set_candidate):
    operators, consensuses = set_candidate
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE * 2)
    __old_turn_round()
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    __init_hybrid_score_mock()
    pledge_agent.moveCOREData(operators[0], accounts[0])
    pledge_agent.moveCOREData(operators[0], accounts[1])
    __get_candidate_map_info(operators[0])
    __get_candidate_map_info(operators[1])
    turn_round(consensuses, round_count=1)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward_map = core_agent.claimReward.call(accounts[1], 0)
    assert reward_map == [TOTAL_REWARD, 0, MIN_INIT_DELEGATE_VALUE * 2]
    reward_map = core_agent.claimReward.call(accounts[0], 0)
    assert reward_map == [0, 0, 0]
    update_system_contract_address(core_agent, stake_hub=stake_hub)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[1])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    assert tracker1.delta() == TOTAL_REWARD
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[1])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 2
    assert tracker1.delta() == TOTAL_REWARD // 2


def test_get_stake_info(pledge_agent):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoinOld(operator, {"value": MIN_INIT_DELEGATE_VALUE})

    tx_id = "88c233d8d6980d2c486a055c804544faa8de93eadc4a00d5bd075d19f3190b4d"
    btc_value = 1000000
    agent = operator
    delegator = accounts[0]
    script = "0x1234"
    lock_time = int(time.time()) + 3600
    fee = 0
    pledge_agent.delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)

    __old_turn_round()
    __old_turn_round([consensus])

    stake_info = pledge_agent.getStakeInfo([operator])
    assert stake_info[0][0] == MIN_INIT_DELEGATE_VALUE
    assert stake_info[2][0] == btc_value


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_move2_core_agent_execution_success(pledge_agent, validator_set, stake_hub, core_agent, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 5)
    old_delegate_coin_success(operators[1], accounts[1], MIN_INIT_DELEGATE_VALUE)
    __check_old_delegate_info(operators[0], accounts[0], {
        'deposit': 0,
        'newDeposit': MIN_INIT_DELEGATE_VALUE * 5,
        'changeRound': get_current_round(),
        'rewardIndex': 1,
        'transferOutDeposit': 0,
        'transferInDeposit': 0,
    })
    __old_turn_round()
    __init_hybrid_score_mock()
    real_amount = delegate_amount
    transferred_amount = 0
    if operate == 'delegate':
        old_delegate_coin_success(operators[0], accounts[0],MIN_INIT_DELEGATE_VALUE, old=False)
        staked_amount = delegate_amount
        real_amount = MIN_INIT_DELEGATE_VALUE * 6
        change_round = core_agent.roundTag()
    elif operate == 'undelegate':
        turn_round()
        tx = old_undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE, old=False)
        assert 'undelegatedCoin' in tx.events
        staked_amount = delegate_amount - MIN_INIT_DELEGATE_VALUE
        real_amount = staked_amount
        change_round = get_current_round()
    elif operate == 'transfer':
        turn_round()
        tx = old_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE, old=False)
        assert 'transferredCoin' in tx.events
        staked_amount = delegate_amount - MIN_INIT_DELEGATE_VALUE
        real_amount = staked_amount
        change_round = get_current_round()
        transferred_amount = MIN_INIT_DELEGATE_VALUE
    else:
        staked_amount = MIN_INIT_DELEGATE_VALUE * 5
        change_round = core_agent.roundTag()
        old_claim_reward_success(operators)
    __check_old_delegate_info(operators[0], accounts[0], {
        'deposit': 0,
        'newDeposit': 0,
        'changeRound': 0,
        'rewardIndex': 0,
        'transferOutDeposit': 0,
        'transferInDeposit': 0,

    })
    __check_delegate_info(operators[0], accounts[0], {
        'stakedAmount': staked_amount,
        'realtimeAmount': real_amount,
        'changeRound': change_round,
        'transferredAmount': transferred_amount
    })


def test_init_hybrid_score_success():
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 3
    for i in range(candidate_size - 1):
        old_delegate_coin_success(operators[i], accounts[i], MIN_INIT_DELEGATE_VALUE * 5 + i)
    __old_turn_round()
    operators1, consensuses1 = __register_candidates(accounts[4:5])
    operators.append(operators1[0])
    consensuses.append(consensuses1[0])
    old_delegate_coin_success(operators[2], accounts[2], MIN_INIT_DELEGATE_VALUE * 5 + 2)
    for i in range(candidate_size):
        coin = delegate_amount + i
        if operators[i] == operators[-1]:
            coin = 0
        __check_old_agent_map_info(operators[i], {
            'totalDeposit': delegate_amount + i,
            'power': 0,
            'coin': coin,
            'btc': 0,
            'totalBtc': 0,
            'moved': False,
        })
    __init_hybrid_score_mock()
    for i in range(candidate_size):
        core_amount = delegate_amount + i
        if operators[i] == operators[-1]:
            core_amount = 0
        __check_candidate_amount_map_info(operators[i], [core_amount, core_amount, 0, 0])


def test_init_hybrid_score_success_with_btc_stake():
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    btc_value = 100
    candidate_size = 3
    for i in range(candidate_size - 1):
        old_delegate_coin_success(operators[i], accounts[i], MIN_INIT_DELEGATE_VALUE * 5 + i)
        old_delegate_btc_success(btc_value + i, operators[i], accounts[i])
    __old_turn_round()
    operators1, consensuses1 = __register_candidates(accounts[4:5])
    operators.append(operators1[0])
    consensuses.append(consensuses1[0])
    old_delegate_coin_success(operators[2], accounts[2], MIN_INIT_DELEGATE_VALUE * 5 + 2)
    for i in range(candidate_size):
        coin = delegate_amount + i
        btc = btc_value + i
        if operators[i] == operators[-1]:
            coin = 0
            btc = 0
        __check_old_agent_map_info(operators[i], {
            'totalDeposit': delegate_amount + i,
            'power': 0,
            'coin': coin,
            'btc': btc,
            'totalBtc': btc,
            'moved': False,
        })
    __init_hybrid_score_mock()
    for i in range(candidate_size):
        core_amount = delegate_amount + i
        btc_amount = int((btc_value + i) * 2e14)
        if operators[i] == operators[-1]:
            core_amount = 0
            btc_amount = 0
        __check_candidate_amount_map_info(operators[i],
                                          [core_amount + btc_amount, core_amount, 0,
                                           btc_amount])


def test_move_agent_success(pledge_agent, validator_set, stake_hub, core_agent):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[i], delegate_amount + i)
        __get_old_delegator_info(operators[i], accounts[i])
    __old_turn_round()
    for i in range(candidate_size):
        __check_old_agent_map_info(operators[i], {
            'totalDeposit': delegate_amount + i,
            'coin': delegate_amount + i,
            'moved': False,
        })
    pledge_agent.moveCandidateData(operators)
    for i in range(candidate_size):
        __check_candidate_map_info(operators[i], {
            'amount': delegate_amount + i,
            'realtimeAmount': delegate_amount + i
        })
        __check_old_agent_map_info(operators[i], {
            # because the contract also has a staked core
            'totalDeposit': delegate_amount + i,
            'coin': delegate_amount + i,
            'moved': True,
        })


@pytest.mark.parametrize("claim", ['old', 'new'])
def test_migration_scenario_1(pledge_agent, validator_set, stake_hub, claim):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[0], delegate_amount + i)
        __get_old_delegator_info(operators[i], accounts[i])
    __old_turn_round(consensuses)
    __old_turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    reward = BLOCK_REWARD
    if claim == 'old':
        old_claim_reward_success(operators, accounts[0])
    else:
        stake_hub_claim_reward(accounts[0])
        reward = 0
    assert tracker0.delta() == reward


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_migration_scenario_2(pledge_agent, validator_set, stake_hub, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[0], delegate_amount + i)
    __old_turn_round(consensuses)
    reward = BLOCK_REWARD
    if operate == 'undelegate':
        old_undelegate_coin_success(operators[0], accounts[0], delegate_amount)
        reward = reward // 2
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == reward


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_migration_scenario_3(pledge_agent, validator_set, stake_hub, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    reward = BLOCK_REWARD
    if operate == 'undelegate':
        old_undelegate_coin_success(operators[0], accounts[0])
        reward = reward // 2
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    __init_hybrid_score_mock()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == reward


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_migration_scenario_4(pledge_agent, validator_set, stake_hub, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    reward = BLOCK_REWARD
    if operate == 'undelegate':
        old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
        reward = TOTAL_REWARD + BLOCK_REWARD // 4
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)
    __init_hybrid_score_mock()
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == reward
    assert stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_migration_scenario_5(pledge_agent, validator_set, stake_hub, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    candidate_size = 2
    for i in range(candidate_size):
        old_delegate_coin_success(operators[i], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    reward = BLOCK_REWARD
    if operate == 'undelegate':
        old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
        reward = TOTAL_REWARD + TOTAL_REWARD - TOTAL_REWARD // 2
        delegate_amount0 = delegate_amount // 2
        delegate_amount1 = delegate_amount
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)
        delegate_amount0 = delegate_amount // 2
        delegate_amount1 = delegate_amount + delegate_amount // 2
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == reward + BLOCK_REWARD
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount0)],
        "btc": [],
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount1)],
        "btc": [],
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]]


@pytest.mark.parametrize("round_count", [0, 1])
@pytest.mark.parametrize("tests", [
    {'delegator': ['tr', 'de', 'un'], 'actual_reward': 27090, 'reward_after_round_switch': 40635},
    {'delegator': ['de', 'un', 'un', 'un'], 'actual_reward': 20317, 'reward_after_round_switch': 27090},
    {'delegator': ['de', 'un', 'un'], 'actual_reward': 27090, 'reward_after_round_switch': 27090},
    {'delegator': ['de', 'tr', 'un', 'un'], 'actual_reward': 20317, 'reward_after_round_switch': 40635},
    {'delegator': ['un', 'un', 'de'], 'actual_reward': 13545, 'reward_after_round_switch': 27090},
    {'delegator': ['un', 'de', 'tr'], 'actual_reward': 20317, 'reward_after_round_switch': 40635},
])
def test_move_data_claim_reward_correct(pledge_agent, validator_set, stake_hub, tests, round_count):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    operators, consensuses = __register_candidates(accounts[2:5])
    __old_turn_round()
    for op in operators[:2]:
        old_delegate_coin_success(op, accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    for d in tests['delegator']:
        if d == 'de':
            old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
        elif d == 'un':
            old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
        elif d == 'tr':
            old_transfer_coin_success(operators[0], operators[2], accounts[0], undelegate_amount)
    __init_hybrid_score_mock()
    turn_round(consensuses, round_count=round_count)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    old_claim_reward_success(operators, accounts[0])
    actual_reward = tests['actual_reward']
    if round_count == 0:
        actual_reward = 0
    assert tracker.delta() == actual_reward
    if round_count > 0:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        assert tracker.delta() == tests['reward_after_round_switch']


@pytest.mark.parametrize("tests", [
    {'delegator': ['tr', 'de', 'un'], 'actual_reward': 67725},
    {'delegator': ['de', 'un', 'un'], 'actual_reward': 54180},
    {'delegator': ['un', 'un', 'de'], 'actual_reward': 40635},
    {'delegator': ['un', 'tr', 'de'], 'actual_reward': 60952}
])
def test_upgrade_claim_reward_after_skip_round(pledge_agent, validator_set, stake_hub, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    operators, consensuses = __register_candidates(accounts[2:5])
    __old_turn_round()
    for op in operators[:2]:
        old_delegate_coin_success(op, accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    for d in tests['delegator']:
        if d == 'de':
            old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
        elif d == 'un':
            old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
        elif d == 'tr':
            old_transfer_coin_success(operators[0], operators[2], accounts[0], undelegate_amount)
    __init_hybrid_score_mock()
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    old_claim_reward_success(operators, accounts[0])
    actual_reward = tests['actual_reward']
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("old_claim", [True, False])
@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", [
    {'delegator': ['tr', 'de'], 'actual_reward': 13545, 'inter_round_reward': 54180},
    {'delegator': ['de', 'de'], 'actual_reward': 27090, 'inter_round_reward': 54180},
    {'delegator': ['tr'], 'actual_reward': 13545, 'inter_round_reward': 40635},
    {'delegator': ['de', 'tr'], 'actual_reward': 27090, 'inter_round_reward': 67725},
])
def test_claim_btc_reward_correct(pledge_agent, validator_set, stake_hub, tests, set_candidate, round_count, old_claim):
    btc_value = 2000
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        tx_id = old_delegate_btc_success(btc_value, op, accounts[0])
        tx_ids.append(tx_id)
    __old_turn_round(consensuses)
    for d in tests['delegator']:
        if d == 'de':
            tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
            tx_ids.insert(0, tx_id)
        elif d == 'tr':
            old_trannsfer_btc_success(tx_ids[0], operators[2])
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    turn_round(consensuses, round_count=round_count)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    if old_claim:
        old_claim_reward_success(operators, accounts[0])
    else:
        stake_hub_claim_reward(accounts[0])
    actual_reward = tests['actual_reward']
    if round_count == 0:
        actual_reward = 0
    if round_count > 1:
        actual_reward = tests['inter_round_reward']
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("tests", [
    {'delegator': ['un', 'de'], 'btc': ['tr', 'de']},
    {'delegator': ['de', 'un'], 'btc': ['de', 'tr']},
    {'delegator': ['tr', 'un', 'de', 'un'], 'btc': ['tr']},
    {'delegator': ['de', 'tr', 'de', 'un'], 'btc': []},
    {'delegator': ['un', 'un', 'de', 'un'], 'btc': []},
    {'delegator': ['un', 'un', 'de', 'tr'], 'btc': []},
])
def test_claim_reward_after_multiple_stake_migrations(pledge_agent, validator_set, stake_hub, set_candidate, tests):
    btc_value = 1e8
    delegate_amount = 2e18
    undelegate_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    delegate_power_success(operators[0], accounts[2], 1)
    delegate_power_success(operators[1], accounts[2], 1)
    delegate_power_success(operators[2], accounts[2], 1)
    for op in operators[:2]:
        tx_id = old_delegate_btc_success(btc_value, op, accounts[0])
        tx_ids.append(tx_id)
        old_delegate_coin_success(op, accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    for d in tests['btc']:
        if d == 'de':
            tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
            tx_ids.insert(0, tx_id)
        elif d == 'tr':
            old_trannsfer_btc_success(tx_ids[0], operators[2])
    for d in tests['delegator']:
        if d == 'de':
            old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
        elif d == 'un':
            old_undelegate_coin_success(operators[0], accounts[1], undelegate_amount)
        elif d == 'tr':
            old_transfer_coin_success(operators[0], operators[2], accounts[1], undelegate_amount)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    trackers = []
    for i in range(3):
        new_reward = get_tracker(accounts[i])
        trackers.append(new_reward)
        old_reward = __get_old_reward(operators, accounts[i])
        old_claim_reward_success(operators, accounts[i])
        assert new_reward.delta() == old_reward
    turn_round(consensuses, round_count=2)


@pytest.mark.parametrize("tests", [
    {'delegator': ['tr', 'un'], 'btc': ['tr', 'de']},
    {'delegator': ['tr', 'de', 'un', 'un', 'un'], 'btc': ['tr', 'de']},
    {'delegator': ['tr', 'un', 'tr', 'un'], 'btc': []},
])
def test_cancel_claim_reward_after_transfer(pledge_agent, validator_set, stake_hub, set_candidate, tests):
    btc_value = 1e8
    delegate_amount = 2e18
    undelegate_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    delegate_power_success(operators[0], accounts[2], 1)
    delegate_power_success(operators[1], accounts[2], 1)
    delegate_power_success(operators[2], accounts[2], 1)
    for op in operators[:2]:
        tx_id = old_delegate_btc_success(btc_value, op, accounts[0])
        tx_ids.append(tx_id)
        old_delegate_coin_success(op, accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    for d in tests['btc']:
        if d == 'de':
            tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
            tx_ids.insert(0, tx_id)
        elif d == 'tr':
            old_trannsfer_btc_success(tx_ids[0], operators[2])
    for d in tests['delegator']:
        if d == 'de':
            old_delegate_coin_success(operators[2], accounts[1], delegate_amount)
        elif d == 'un':
            old_undelegate_coin_success(operators[2], accounts[1], undelegate_amount)
        elif d == 'tr':
            old_transfer_coin_success(operators[0], operators[2], accounts[1], undelegate_amount)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    trackers = []
    for i in range(3):
        new_reward = get_tracker(accounts[i])
        trackers.append(new_reward)
        old_reward = __get_old_reward(operators, accounts[i])
        old_claim_reward_success(operators, accounts[i])
        assert new_reward.delta() == old_reward
    turn_round(consensuses, round_count=2)


def test_repeat_claim_btc_reward_after_move_btc_data(pledge_agent, set_candidate):
    btc_value = 2000
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id])
    __check_old_reward(operators, accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD


def test_claim_reward_after_repeat_move_btc_data(pledge_agent, set_candidate):
    btc_value = 2000
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id])
    __move_btc_data([tx_id])
    __check_old_reward(operators, accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    __move_btc_data([tx_id])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD


def test_power_claim_reward_success(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    __old_turn_round()
    delegate_power_success(operators[0], accounts[0])
    __old_turn_round(consensuses)
    delegate_power_success(operators[0], accounts[1])
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[1])
    assert tracker.delta() == TOTAL_REWARD
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[1])
    assert tracker.delta() == 0


def test_new_validator_join_current_round(pledge_agent, set_candidate):
    operators, consensuses = __register_candidates(accounts[2:4])
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)
    __old_turn_round(consensuses)
    agent, consensus = __register_candidates(accounts[4:5])
    operators.append(agent[0])
    consensuses.append(consensus[0])
    old_delegate_coin_success(operators[-1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[0], 0)
    __check_old_reward(operators, accounts[1], 0)
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD * 2
    assert tracker1.delta() == TOTAL_REWARD * 3


def test_cancel_allowed_current_round_after_move_data(pledge_agent, set_candidate):
    operators, consensuses = __register_candidates(accounts[2:4])
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    agent, consensus = __register_candidates(accounts[4:5])
    operators.append(agent[0])
    consensuses.append(consensus[0])
    old_delegate_coin_success(operators[-1], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[0], 0)
    __check_old_reward(operators, accounts[1], 0)
    undelegate_coin_success(operators[0], accounts[1], delegate_amount)
    undelegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)
    undelegate_coin_success(operators[-1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round(consensuses)
    undelegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)
    undelegate_coin_success(operators[-1], accounts[0], MIN_INIT_DELEGATE_VALUE)


def test_claim_upgrade_current_round_stake_reward(pledge_agent, stake_hub, set_candidate):
    operators, consensuses = __register_candidates(accounts[2:4])
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD // 2
    assert tracker1.delta() == TOTAL_REWARD + TOTAL_REWARD // 2


def test_claim_new_effective_reward_after_skip_round(pledge_agent, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], TOTAL_REWARD + TOTAL_REWARD // 2)
    __check_old_reward(operators, accounts[0], TOTAL_REWARD - TOTAL_REWARD // 2)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD
    assert tracker1.delta() == TOTAL_REWARD


def test_upgrade_current_round_cancel(pledge_agent, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    old_undelegate_coin_success(operators[0], accounts[1], delegate_amount // 2)
    old_undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    assert tracker0.delta() == TOTAL_REWARD - TOTAL_REWARD // 2 + delegate_amount // 2
    assert tracker1.delta() == TOTAL_REWARD + TOTAL_REWARD // 2 + delegate_amount // 2
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD // 4 + TOTAL_REWARD // 2
    assert tracker1.delta() == TOTAL_REWARD // 4 + TOTAL_REWARD // 2


def test_upgrade_current_round_transfer(pledge_agent, btc_agent, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    old_transfer_coin_success(operators[0], operators[1], accounts[1])
    old_transfer_coin_success(operators[1], operators[2], accounts[1])
    old_transfer_coin_success(operators[0], operators[1], accounts[0])
    assert tracker0.delta() == TOTAL_REWARD - TOTAL_REWARD // 2
    assert tracker1.delta() == TOTAL_REWARD + TOTAL_REWARD // 2
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD // 2 + TOTAL_REWARD
    assert tracker1.delta() == TOTAL_REWARD // 2 + TOTAL_REWARD
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD
    assert tracker1.delta() == TOTAL_REWARD


def test_refuse_validator_data_migration(pledge_agent, btc_agent, candidate_hub, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    candidate_hub.refuseDelegate({'from': operators[0]})
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD // 2
    assert tracker1.delta() == TOTAL_REWARD // 2
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0


@pytest.mark.parametrize("round_count", [0, 1, 2])
def test_non_validator_stake_data_migration(pledge_agent, btc_agent, candidate_hub, stake_hub, set_candidate,
                                            round_count):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    candidate_hub.refuseDelegate({'from': operators[0]})
    __old_turn_round(consensuses, round_count=round_count)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    actual_reward0 = 0
    actual_reward1 = 0
    if round_count == 0:
        actual_reward0 = TOTAL_REWARD
    assert tracker0.delta() == actual_reward0
    assert tracker1.delta() == actual_reward1
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0


@pytest.mark.parametrize('round_count', [0, 1])
@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_slash_validator_during_data_migration(pledge_agent, btc_agent, slash_indicator, candidate_hub, stake_hub,
                                               set_candidate,
                                               threshold_type, round_count):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    __old_turn_round(consensuses)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses, round_count=1)
    tx = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        actual_reward = TOTAL_REWARD // 2
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        actual_reward = 0
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    __old_turn_round(consensuses, round_count=round_count)
    __init_hybrid_score_mock()
    __check_old_reward(operators, accounts[1], 0)
    __check_old_reward(operators, accounts[0], 0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == actual_reward
    assert tracker1.delta() == actual_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == actual_reward
    assert tracker1.delta() == actual_reward


def test_stake_immediately_after_upgrade(stake_hub, core_agent, set_candidate):
    btc_value = 1000
    delegate_amount = 10000
    operators, consensuses = set_candidate
    __old_turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    tx_id = old_delegate_btc_success(btc_value, operators[1], accounts[2])
    old_delegate_coin_success(operators[1], accounts[3], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id])
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 3
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[1])
    assert tracker0.delta() == TOTAL_REWARD // 2 * 2 + TOTAL_REWARD // 3


def test_btc_claim_reward_current_round_after_move_data(stake_hub, pledge_agent, core_agent, set_candidate):
    btc_value = 1e8
    delegate_amount = 10000e18
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses, round_count=1)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id])
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    tx = turn_round(consensuses, round_count=1)
    assert tx.events['roundReward'][0]['amount'][0] == TOTAL_REWARD // 3
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    old_claim_reward_success(operators, accounts[1])
    assert tracker0.delta() == TOTAL_REWARD // 3 * 2


def test_power_claim_reward_current_round_after_move_data(stake_hub, pledge_agent, core_agent, set_candidate):
    power_value = 1
    delegate_amount = 1000000e18
    operators, consensuses = set_candidate
    __old_turn_round()
    delegate_power_success(operators[0], accounts[0], power_value)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses, round_count=1)
    __init_hybrid_score_mock()
    tx = turn_round(consensuses, round_count=1)
    assert tx.events['roundReward'][0]['amount'][0] == TOTAL_REWARD // 2
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    old_claim_reward_success(operators, accounts[1])
    assert tracker0.delta() == TOTAL_REWARD // 2


def test_stake_btc_immediately_after_upgrade(stake_hub, pledge_agent, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, 0, btc_value * 10)
    __move_btc_data([tx_id])
    __check_old_reward(operators, accounts[0])
    __check_old_reward(operators, accounts[1], TOTAL_REWARD - TOTAL_REWARD // 2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[:2])
    old_claim_reward_success(operators, accounts[1])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[0], btc_value)]
    }], TOTAL_REWARD)
    assert tracker0.delta() == account_rewards[accounts[0]] + TOTAL_REWARD // 2
    assert tracker1.delta() == account_rewards[accounts[1]] + TOTAL_REWARD // 2


def test_multiple_stakes_after_upgrade(stake_hub, pledge_agent, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=1)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=2)
    __old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data([tx_id])
    __check_old_reward(operators, accounts[0])
    __check_old_reward(operators, accounts[1], TOTAL_REWARD - TOTAL_REWARD // 2)
    tracker = get_trackers(accounts[:3])
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[0])
    old_claim_reward_success(operators, accounts[1])
    stake_hub_claim_reward(accounts[2])
    for t in tracker:
        assert t.delta() == TOTAL_REWARD // 3
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[0], btc_value)]
    }], TOTAL_REWARD)
    for index, t in enumerate(tracker):
        assert t.delta() == account_rewards[accounts[index]]


def test_claim_reward_after_multiple_rounds_upgrade(stake_hub, pledge_agent, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=0)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=1)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data([tx_id])
    turn_round(consensuses, round_count=1)
    tracker = get_trackers(accounts[:3])
    old_claim_reward_success(operators, accounts[1])
    turn_round(consensuses, round_count=2)
    _, _, account_rewards0, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], TOTAL_REWARD)
    _, _, account_rewards1, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], TOTAL_REWARD)
    stake_hub_claim_reward(accounts[:3])
    for index, t in enumerate(tracker):
        round_reward0 = account_rewards0[accounts[index]]
        round_reward1 = account_rewards1.get(accounts[index], 0)
        assert t.delta() == round_reward0 + round_reward1 + TOTAL_REWARD // 3
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], TOTAL_REWARD)
    stake_hub_claim_reward(accounts[:3])
    for index, t in enumerate(tracker[:3]):
        assert t.delta() == account_rewards.get(t.address, 0)


def test_claim_old_contract_reward_after_move_data(stake_hub, pledge_agent, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=0)
    delegate_power_success(operators[0], accounts[2], power_value, stake_round=1)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data([tx_id])
    turn_round(consensuses, round_count=1)
    trackers = get_trackers(accounts[:2])
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[1])
    for tracker in trackers:
        assert tracker.delta() == TOTAL_REWARD // 3
    turn_round(consensuses, round_count=1)
    delegator0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator1 = pledge_agent.getDelegator(operators[0], accounts[1])
    assert delegator0['changeRound'] == 0
    assert delegator1['changeRound'] == 0


@pytest.mark.parametrize("tests", ['delegate', 'undelgate', 'transfer'])
def test_proxy_staking_success(stake_hub, pledge_agent, core_agent, set_candidate, tests):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data([tx_id])
    turn_round(consensuses, round_count=1)
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[1])
    if tests == 'delegate':
        tx = old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
        assert 'delegatedCoin' in tx.events
    elif tests == 'undelgate':
        tx = old_undelegate_coin_success(operators[0], accounts[1], 0, old=False)
        assert 'undelegatedCoin' in tx.events
    elif tests == 'transfer':
        tx = old_transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount, old=False)
        assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("tests", ['delegate', 'undelgate', 'transfer'])
def test_proxy_staking_success(stake_hub, pledge_agent, core_agent, set_candidate, tests):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data([tx_id])
    turn_round(consensuses, round_count=1)
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[1])
    if tests == 'delegate':
        tx = old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
        assert 'delegatedCoin' in tx.events
    elif tests == 'undelgate':
        tx = old_undelegate_coin_success(operators[0], accounts[1], 0, old=False)
        assert 'undelegatedCoin' in tx.events
    elif tests == 'transfer':
        tx = old_transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount, old=False)
        assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_unstaking_success(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    if part:
        undelegate_amount = delegate_amount // 2
        undelegate_value = undelegate_amount
        actual_reward = TOTAL_REWARD // 4
        round_reward = TOTAL_REWARD // 3 * (round_count - 1)
    else:
        undelegate_amount = 0
        actual_reward = 0
        undelegate_value = delegate_amount
        round_reward = 0
    tracker = get_tracker(accounts[0])
    tx = old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount, old=False)
    assert 'undelegatedCoin' in tx.events
    turn_round(consensuses, round_count=round_count)
    old_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward + undelegate_value
    if round_count == 0:
        actual_reward = undelegate_value
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_unstaking_after_multiple_rounds(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    turn_round(consensuses, round_count=round_count)
    accrued_reward = 6772500
    if part:
        undelegate_amount = delegate_amount // 2
        undelegate_value = undelegate_amount
        actual_reward = TOTAL_REWARD // 4
        round_reward = delegate_amount * round_count * accrued_reward // Utils.CORE_STAKE_DECIMAL
    else:
        undelegate_amount = 0
        actual_reward = 0
        undelegate_value = delegate_amount
        round_reward = delegate_amount * round_count * accrued_reward // Utils.CORE_STAKE_DECIMAL
    tracker = get_tracker(accounts[0])
    old_undelegate_coin_success(operators[0], accounts[0], undelegate_amount, old=False)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    old_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward + undelegate_value
    if round_count == 0:
        actual_reward = undelegate_value
        if part:
            actual_reward += TOTAL_REWARD // 4
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_transfer_success(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    if part:
        transfer_amount = delegate_amount // 2
        actual_reward = TOTAL_REWARD // 2
        round_reward = TOTAL_REWARD * (round_count - 1)
        old_candidate_reward = TOTAL_REWARD // 3 * (round_count - 1)
    else:
        transfer_amount = 0
        actual_reward = TOTAL_REWARD // 2
        round_reward = TOTAL_REWARD * (round_count - 1)
        old_candidate_reward = 0
    tracker = get_tracker(accounts[0])
    tx = old_transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount, old=False)
    assert 'transferredCoin' in tx.events
    turn_round(consensuses, round_count=round_count)
    old_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward + old_candidate_reward
    if round_count == 0:
        actual_reward = 0
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_transfer_after_multiple_rounds(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    turn_round(consensuses, round_count=round_count)
    accrued_reward = 6772500
    actual_reward = TOTAL_REWARD // 2
    round_reward = delegate_amount * round_count * accrued_reward // Utils.CORE_STAKE_DECIMAL
    if part:
        transfer_amount = delegate_amount // 2
    else:
        transfer_amount = delegate_amount
    tracker = get_tracker(accounts[0])
    old_transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount, old=False)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    old_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward
    if round_count == 0:
        actual_reward = TOTAL_REWARD // 2
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
def test_proxy_delegate_success(stake_hub, pledge_agent, core_agent, set_candidate, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    tracker = get_tracker(accounts[0])
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    turn_round(consensuses, round_count=round_count)
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD // 2
    actual_reward += TOTAL_REWARD * 2 // 3 * (round_count - 1)
    if round_count == 0:
        actual_reward = 0
    assert tracker.delta() == actual_reward - delegate_amount


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
def test_proxy_delegate_after_multiple_rounds(stake_hub, pledge_agent, core_agent, set_candidate, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    turn_round(consensuses, round_count=round_count)
    accrued_reward = 6772500
    actual_reward = TOTAL_REWARD // 2
    round_reward = delegate_amount * round_count * accrued_reward // Utils.CORE_STAKE_DECIMAL
    tracker = get_tracker(accounts[0])
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses, round_count=2)
    actual_reward += TOTAL_REWARD * 2 // 3
    old_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward - delegate_amount
    if round_count == 0:
        actual_reward = TOTAL_REWARD // 2 + TOTAL_REWARD * 2 // 3 - delegate_amount
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['undelgate', 'transfer'])
def test_proxy_delegate_current_round_cancel_and_transfer_allowed(stake_hub, core_agent, set_candidate, tests,
                                                                  round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    if tests == 'undelgate':
        old_undelegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    elif tests == 'transfer':
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount, old=False)
    turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    turn_round(consensuses, round_count=round_count)
    if tests == 'undelgate':
        old_undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2, old=False)
    elif tests == 'transfer':
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2, old=False)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['undelgate', 'transfer'])
def test_current_round_transfer_can_cancel_and_transfer(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
    turn_round()
    old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount, old=False)
    turn_round(consensuses, round_count=round_count)
    if tests == 'undelgate':
        old_undelegate_coin_success(operators[1], accounts[0], delegate_amount, old=False)
    elif tests == 'transfer':
        old_transfer_coin_success(operators[1], operators[2], accounts[0], delegate_amount, old=False)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['delegate', 'transfer'])
def test_proxy_undelegate_cancel_all(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    if tests == 'delegate':
        delegate_coin_success(operators[1], accounts[0], delegate_amount)
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount, old=False)
    turn_round(consensuses, round_count=round_count)
    tracker = get_tracker(accounts[0])
    old_undelegate_coin_success(operators[1], accounts[0], 0, old=False)
    actual_amount = delegate_amount * 2
    assert tracker.delta() == actual_amount
    turn_round(consensuses)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['delegate', 'transfer'])
def test_proxy_transfer_cancel_all(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    if tests == 'delegate':
        delegate_coin_success(operators[1], accounts[0], delegate_amount)
    else:
        old_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount, old=False)
    turn_round(consensuses, round_count=round_count)
    tx = old_transfer_coin_success(operators[1], operators[2], accounts[0], 0, old=False)
    actual_amount = delegate_amount * 2
    assert tx.events['transferredCoin']['amount'] == actual_amount
    assert tx.events['transferredCoin']['realtimeAmount'] == actual_amount
    turn_round(consensuses)


def test_cancel_after_all_already_cancelled(stake_hub, core_agent, set_candidate):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    old_undelegate_coin_success(operators[1], accounts[0], 0, old=False)
    turn_round(consensuses, round_count=2)
    with brownie.reverts("call CORE_AGENT_ADDR.proxyUnDelegate() failed"):
        old_undelegate_coin_success(operators[1], accounts[0], 0, old=False)
    __check_delegate_info(operators[1], accounts[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0,
        'changeRound': 0,
        'transferredAmount': 0
    })


def test_cancel_stake_with_zero_amount(stake_hub, core_agent, set_candidate):
    delegate_amount = 10000
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_transfer_coin_success(operators[0], operators[2], accounts[0], 0, False)
    with brownie.reverts("Undelegate zero coin"):
        undelegate_coin_success(operators[0], accounts[0], 0)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2
    turn_round(consensuses)


def test_claim_reward_with_both_proxy_and_regular_staking(stake_hub, btc_stake, core_agent, set_candidate):
    delegate_amount = 10000
    btc_amount = 1000
    btc_lst_amount = 200
    power_value = 5
    operators, consensuses = set_candidate
    turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_amount, LOCK_SCRIPT)
    tx_id = delegate_btc_success(operators[0], accounts[1], btc_amount, LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[0], accounts[3], power_value)
    delegate_btc_lst_success(accounts[0], btc_lst_amount, BTCLST_LOCK_SCRIPT, percentage=Utils.DENOMINATOR)
    turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, old=False)
    old_undelegate_coin_success(operators[0], accounts[0], 0, old=False)
    transfer_btc_success(tx_id, operators[2], accounts[1])
    old_transfer_coin_success(operators[0], operators[2], accounts[1], 0, old=False)
    turn_round(consensuses)
    trackers = get_trackers(accounts[:4])
    stake_hub_claim_reward(accounts[0])
    old_claim_reward_success(operators, accounts[1])
    stake_hub_claim_reward(accounts[2])
    old_claim_reward_success(operators, accounts[3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[3], power_value)],
        "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount),
                set_delegate(accounts[1], btc_amount, btc_amount)]
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    }, btc_lst_stake={accounts[0]: set_btc_lst_delegate(btc_lst_amount)})
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == account_rewards.get(tracker.address, 0)


@pytest.mark.parametrize("delegator", [True, False])
def test_claim_reward_after_multiple_delegator_operations(stake_hub, btc_stake, core_agent, set_candidate, delegator):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for account in accounts[:2]:
        tx_id = old_delegate_btc_success(btc_value, operators[0], account)
        tx_ids.append(tx_id)
        old_delegate_coin_success(operators[0], account, delegate_amount)
    for i in range(2):
        delegate_power_success(operators[0], accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data(tx_ids)
    turn_round(consensuses)
    if delegator:
        old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
        old_undelegate_coin_success(operators[0], accounts[1], delegate_amount, old=False)
        old_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 4, old=False)
        undelegate_amount = delegate_amount
        trackers = get_trackers(accounts[:3])
    else:
        undelegate_amount = 0
        trackers = get_trackers(accounts[:3])
        old_claim_reward_success(operators, accounts[0])
        old_claim_reward_success(operators, accounts[1])
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount, undelegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    for index, tracker in enumerate(trackers):
        old_reward = TOTAL_REWARD // 6 * 2
        if index == 2:
            old_reward = TOTAL_REWARD // 3
        assert tracker.delta() == account_rewards[tracker.address] + old_reward


def test_claim_reward_after_btc_stake_in_upgrade_round(stake_hub, btc_stake, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for account in accounts[:2]:
        tx_id = old_delegate_btc_success(btc_value, operators[0], account)
        tx_ids.append(tx_id)
        old_delegate_coin_success(operators[0], account, delegate_amount)
    for i in range(2):
        delegate_power_success(operators[0], accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data(tx_ids)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    trackers = get_trackers(accounts[:3])
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    for index, tracker in enumerate(trackers):
        old_reward = TOTAL_REWARD // 3
        assert tracker.delta() == account_rewards[tracker.address] + old_reward


def test_claim_reward_after_upgrade(stake_hub, btc_stake, core_agent, set_candidate):
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(2):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount, power_value * 1000, btc_value * 10)
    stake_hub.setCandidateScoresMap(operators[1], delegate_amount, power_value * 1000, btc_value * 10)
    __move_btc_data(tx_ids)
    trackers = get_trackers(accounts[:3])
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses)
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }, {
        "address": operators[1],
        "power": [set_delegate(accounts[2], power_value)],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    for index, tracker in enumerate(trackers):
        old_reward = TOTAL_REWARD // 6 * 2 * 2
        if index == 2:
            old_reward = TOTAL_REWARD // 3 * 2
        assert tracker.delta() == account_rewards[tracker.address] + old_reward


def test_candidate_data_migration(stake_hub, btc_stake, core_agent, candidate_hub, validator_set, set_candidate):
    candidate_hub.setValidatorCount(1)
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(2):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[1], delegate_amount, power_value * 1000, btc_value * 10)
    assert validator_set.getValidators()[0] == consensuses[1]
    __move_btc_data(tx_ids)
    candidate_hub.setValidatorCount(2)
    trackers = get_trackers(accounts[:3])
    turn_round(consensuses)
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        },
        {
            "address": operators[1],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    for index, tracker in enumerate(trackers):
        old_reward = TOTAL_REWARD // 6 * 2
        if index == 2:
            old_reward = TOTAL_REWARD // 3
        assert tracker.delta() == account_rewards[tracker.address] + old_reward
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }, {
        "address": operators[1],
        "coin": [set_delegate(accounts[0], delegate_amount),
                 set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_value),
                set_delegate(accounts[1], btc_value)]
    }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == account_rewards.get(tracker.address, 0)


@pytest.mark.parametrize("round_count", [0, 1])
def test_claim_reward_after_candidate_migration_skip_round(stake_hub, btc_stake, core_agent, candidate_hub,
                                                           validator_set, set_candidate, round_count):
    candidate_hub.setValidatorCount(1)
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[1], delegate_amount, power_value * 1000, btc_value * 10)
    assert validator_set.getValidators()[0] == consensuses[1]
    __move_btc_data(tx_ids)
    candidate_hub.setValidatorCount(2)
    trackers = get_trackers(accounts[:3])
    turn_round(consensuses)
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses, round_count=round_count)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        },
        {
            "address": operators[1],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    old_reward0 = TOTAL_REWARD // 6 * 2
    old_reward1 = TOTAL_REWARD // 3
    account_reward0 = account_rewards[accounts[0]] * round_count + old_reward0
    account_reward1 = account_rewards[accounts[1]] * round_count + old_reward0
    account_reward2 = account_rewards[accounts[2]] * round_count + old_reward1
    assert_trackers(trackers, [account_reward0, account_reward1, account_reward2])


def test_claim_reward_after_multiple_rounds_candidate(stake_hub, btc_stake, core_agent, candidate_hub, set_candidate,
                                                      validator_set):
    candidate_hub.setValidatorCount(1)
    btc_value = 100
    delegate_amount = 1000
    power_value = 1
    operators, consensuses = set_candidate
    __old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    __old_turn_round(consensuses)
    __init_hybrid_score_mock()
    stake_hub.setCandidateScoresMap(operators[1], delegate_amount, power_value * 1000, btc_value * 10)
    assert validator_set.getValidators()[0] == consensuses[1]
    __move_btc_data(tx_ids)
    candidate_hub.setValidatorCount(2)
    trackers = get_trackers(accounts[:3])
    turn_round(consensuses)
    assert len(validator_set.getValidators()) == 2
    old_claim_reward_success(operators, accounts[:3])
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[:3])
    turn_round(consensuses, round_count=1)
    _, _, account_rewards, asset_unit_reward_map = parse_delegation([
        {
            "address": operators[0],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        },
        {
            "address": operators[1],
            "power": [set_delegate(accounts[2], power_value)],
            "coin": [set_delegate(accounts[0], delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)]
        }], TOTAL_REWARD, state_map={
        'btc_lst_gradeActive': 0,
        'btc_gradeActive': 0
    })
    stake_hub_claim_reward(accounts[:3])
    old_reward0 = TOTAL_REWARD // 6 * 2
    old_reward1 = TOTAL_REWARD // 3
    account_reward0 = account_rewards[accounts[0]] * 2 + old_reward0
    account_reward1 = account_rewards[accounts[1]] * 2 + old_reward0
    account_reward2 = account_rewards[accounts[2]] * 2 + old_reward1
    assert_trackers(trackers, [account_reward0, account_reward1, account_reward2])


@pytest.mark.parametrize("inter_round_cancel", [True, False])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 2, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 0, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 2, 'amount': 1200, 'expect_reward': 6772 + 13545 * 800 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_reward': 6772 + 13545 * 500 // 2000},
])
def test_cancel_stake_after_transfer_with_validator(pledge_agent, validator_set, set_candidate, tests,
                                                    inter_round_cancel):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        old_delegate_coin_success(op, accounts[0], delegate_amount, False)
        old_delegate_coin_success(op, accounts[1], delegate_amount, False)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    if inter_round_cancel:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        expect_reward += TOTAL_REWARD // 2 * 3
    old_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount, False)
    tx = old_undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount, False)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + undelegate_amount


@pytest.mark.parametrize("old", [True, False])
@pytest.mark.parametrize("tests", [
    {'transfer': 4000, 'undelagate': [1, 2], 'amount': [2000, 2000], 'expect_reward': 13545 // 6},
    {'transfer': 4000, 'undelagate': [1, 2], 'amount': [0, 0], 'expect_reward': 0},
    {'transfer': 3000, 'undelagate': [0, 1], 'amount': [0, 0], 'expect_reward': 13545 // 6 + 6772},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1500, 1000], 'expect_reward': 13545 * 2500 // 6000},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [2000, 1500], 'expect_reward': 13545 * 1500 // 6000},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1000, 1000], 'expect_reward': 6772},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1000, 500], 'expect_reward': 6772 + 3386},
    {'transfer': 3000, 'undelagate': [0, 2], 'amount': [1000, 2000], 'expect_reward': 13545 // 6 + 6772},
    {'transfer': 2000, 'undelagate': [0, 2], 'amount': [500, 500], 'expect_reward': 13545 * 2500 // 6000 + 6772 + 3386},
    {'transfer': 2000, 'undelagate': [0, 1], 'amount': [2000, 2000], 'expect_reward': 6772},
    {'transfer': 3000, 'undelagate': [0, 1, 2], 'amount': [1000, 2000, 2000], 'expect_reward': 0},
    {'transfer': 3000, 'undelagate': [0, 1, 2], 'amount': [0, 2000, 0], 'expect_reward': 0},
    {'transfer': 3000, 'undelagate': [0, 1, 2], 'amount': [0, 0, 0], 'expect_reward': 0}
])
def test_cancel_stake_from_validators_after_multiple_additions(core_agent, validator_set, set_candidate, tests, old):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        if index == 0:
            delegate_value = delegate_amount * 3
        old_delegate_coin_success(op, accounts[0], delegate_value, False)
        old_delegate_coin_success(op, accounts[1], delegate_value, False)
    turn_round()
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        old_delegate_coin_success(op, accounts[0], delegate_value, False)
        if old:
            delegate_coin_success(op, accounts[1], delegate_value)
        else:
            old_delegate_coin_success(op, accounts[1], delegate_value, False)
    if old:
        old_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount, False)
    else:
        transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    for index, a in enumerate(agent_index):
        old_undelegate_coin_success(operators[a], accounts[0], undelegate_amount[index], False)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'candidate': 0, 'amount': 500, 'expect_reward': 3386, 'tow_round_reward': 13545 + 3386},
    {'transfer': 500, 'candidate': 2, 'amount': 500, 'expect_reward': 3386, 'tow_round_reward': 13545 // 3 + 3386},
    {'transfer': 500, 'candidate': 0, 'amount': 250, 'expect_reward': 13545 * 750 // 2000,
     'tow_round_reward': 13545 + 13545 * 750 // 2000 + 13545 * 250 // 1250},
    {'transfer': 500, 'candidate': 2, 'amount': 250, 'expect_reward': 13545 * 750 // 2000,
     'tow_round_reward': 13545 + 13545 * 750 // 2000 + 13545 * 500 // 1500}
])
def test_claim_reward_after_cancel_coin_transfer(core_agent, validator_set, set_candidate, tests, round_count):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['candidate']
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, False)
    turn_round()
    old_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount, False)
    tracker0 = get_tracker(accounts[0])
    old_undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount, False)
    turn_round(consensuses, round_count=round_count)
    old_claim_reward_success(operators, accounts[0])
    if round_count == 0:
        expect_reward = 0
    elif round_count > 1:
        expect_reward = tests['tow_round_reward']
    assert tracker0.delta() == expect_reward + undelegate_amount


def test_claim_rewards_after_cancel_all_in_two_rounds(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, False)
    turn_round()
    old_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2, False)
    old_undelegate_coin_success(operators[0], accounts[0], 0, False)
    old_undelegate_coin_success(operators[2], accounts[0], 0, False)
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=2)
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == 0
    turn_round(consensuses, round_count=2)
    old_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == 0


@pytest.mark.parametrize("tests", ['transfer', 'undelegate'])
def test_cancel_and_transfer_after_adding_stake(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount, False)
    turn_round()
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    old_delegate_coin_success(operators[1], accounts[0], delegate_amount, False)
    if tests == 'transfer':
        old_transfer_coin_success(operators[0], operators[1], accounts[0], 0, False)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': get_current_round(),
            'transferredAmount': delegate_amount,
        })
        __check_delegate_info(operators[1], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': delegate_amount * 3,
        })
        expect_reward = TOTAL_REWARD // 2
    else:
        old_undelegate_coin_success(operators[0], accounts[0], 0, False)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': 0,
            'transferredAmount': 0,
        })
        expect_reward = 0
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    assert tracker.delta() == expect_reward


@pytest.mark.parametrize("tests", ['transfer', 'undelegate'])
def test_cancel_all_after_transfer(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    old_delegate_coin_success(operators[1], accounts[0], delegate_amount, False)
    turn_round()
    old_transfer_coin_success(operators[1], operators[0], accounts[0], 0, False)
    if tests == 'transfer':
        old_transfer_coin_success(operators[0], operators[2], accounts[0], 0, False)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': get_current_round(),
            'transferredAmount': delegate_amount,
        })
        __check_delegate_info(operators[2], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': delegate_amount * 2,
        })
        expect_reward = TOTAL_REWARD * 2
    else:
        old_undelegate_coin_success(operators[0], accounts[0], 0, False)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': 0,
            'transferredAmount': 0,
        })
        expect_reward = 0
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    old_claim_reward_success(operators, accounts[0])
    assert tracker.delta() == expect_reward


def __init_hybrid_score_mock():
    STAKE_HUB.initHybridScoreMock()
    set_round_tag(get_current_round())


def __move_btc_data(tx_ids):
    BTC_STAKE.moveData(tx_ids)


def __old_turn_round(miners: list = None, tx_fee=100, round_count=1):
    if miners is None:
        miners = []
    tx = None
    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[-10]})
        tx = CandidateHubMock[0].turnRoundOld()
        chain.sleep(1)
    return tx


def __get_old_reward_index_info(candidate, index):
    reward_index = PLEDGE_AGENT.getReward(candidate, index)
    return reward_index


def __get_old_agent_map_info(candidate):
    agent_map = PLEDGE_AGENT.agentsMap(candidate)
    return agent_map


def __get_old_delegator_info(candidate, delegator):
    delegator_info = PLEDGE_AGENT.getDelegator(candidate, delegator)
    return delegator_info


def __get_delegator_info(candidate, delegator):
    delegator_info = CoreAgentMock[0].getDelegator(candidate, delegator)
    return delegator_info


def __get_reward_map_info(delegator):
    delegator_info = CoreAgentMock[0].rewardMap(delegator)
    return delegator_info


def __get_candidate_map_info(candidate):
    candidate_info = CoreAgentMock[0].candidateMap(candidate)
    return candidate_info


def __check_candidate_map_info(candidate, result: dict):
    old_info = __get_candidate_map_info(candidate)
    for i in result:
        assert old_info[i] == result[i]


def __get_candidate_amount_map_info(candidate):
    # The order is core, hash, btc.
    candidate_score = STAKE_HUB.getCandidateScoresMap(candidate)
    return candidate_score


def __check_old_delegate_info(candidate, delegator, result: dict):
    old_info = __get_old_delegator_info(candidate, delegator)
    for i in result:
        assert old_info[i] == result[i]


def __check_delegate_info(candidate, delegator, result: dict):
    old_info = __get_delegator_info(candidate, delegator)
    for i in result:
        assert old_info[i] == result[i]


def __check_candidate_amount_map_info(candidate, result: list):
    candidate_amounts = __get_candidate_amount_map_info(candidate)
    if candidate_amounts == ():
        candidate_amounts = [0, 0, 0, 0]
    for index, r in enumerate(result):
        assert candidate_amounts[index] == r


def __get_btc_receipt_map(tx_id):
    receipt_map = BTC_STAKE.receiptMap(tx_id)
    return receipt_map


def __check_btc_receipt_map(candidate, result: dict):
    receipt = __get_btc_receipt_map(candidate)
    for i in result:
        assert receipt[i] == result[i]


def __get_core_agent_reward_map(delegator):
    reward_map = CORE_AGENT.rewardMap(delegator)
    return reward_map


def __check_core_reward_map(delegator, result: dict):
    reward_map = __get_core_agent_reward_map(delegator)
    for i in result:
        assert reward_map[i] == result[i]


def __check_old_agent_map_info(candidate, result: dict):
    old_info = __get_old_agent_map_info(candidate)
    for i in result:
        assert old_info[i] == result[i]


def __register_candidates(agents=None):
    operators = []
    consensuses = []
    if agents is None:
        agents = accounts[2:5]
    for operator in agents:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def __get_btc_candidate_map_info(candidate):
    candidate_map = BTC_STAKE.candidateMap(candidate)
    return candidate_map


def __check_btc_candidate_map_info(candidate, result: dict):
    data = __get_btc_candidate_map_info(candidate)
    for i in result:
        assert data[i] == result[i]


def __get_old_reward(operators, delegator):
    old_reward, _ = PLEDGE_AGENT.claimRewardMock.call(operators, {'from': delegator})
    return old_reward


def __check_old_reward(operators, delegator, actual_reward=None):
    old_reward = __get_old_reward(operators, delegator)
    tracker = get_tracker(delegator)
    old_claim_reward_success(operators, delegator)
    assert tracker.delta() == old_reward
    if actual_reward:
        assert old_reward == actual_reward
