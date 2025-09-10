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
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_min_init_delegate_value(min_init_delegate_value):
    global MIN_INIT_DELEGATE_VALUE
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, pledge_agent, stake_hub, core_agent, btc_stake, gov_hub, system_reward):
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
    system_reward.setOperator(stake_hub.address)


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



def test_reentry_stake_hub_claim(pledge_agent, stake_hub, set_candidate, validator_set):
    operators, consensuses = set_candidate
    reentry_ = ClaimRewardReentry.deploy(pledge_agent.address, stake_hub, {'from': accounts[0]})
    accounts[2].transfer(reentry_, ONE_ETHER)
    accounts[2].transfer(pledge_agent, ONE_ETHER)
    accounts[2].transfer(stake_hub, ONE_ETHER)
    turn_round(consensuses, round_count=2)
    delegate_coin_success(operators[0], reentry_, MIN_INIT_DELEGATE_VALUE)
    pledge_agent.setRewardMap(reentry_, TOTAL_REWARD)
    tx = reentry_.claimReward([operators[0]])
    assert tx.events['claimedReward']['amount'] == TOTAL_REWARD
    assert len(tx.events['claimedReward']) == 1



@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer'])
def test_auto_issue_historical_rewards(pledge_agent, set_candidate, core_agent, operate):
    operators, consensuses = set_candidate
    accounts[0].transfer(pledge_agent, ONE_ETHER)
    pledge_agent.setRewardMap(accounts[0], TOTAL_REWARD)
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    if operate == 'delegate':
        tx = proxy_delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    elif operate == 'undelegate':
        tx = proxy_undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    else:
        tx = proxy_transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    assert 'claimedReward' not in tx.events




def test_claim_reward_success(btc_agent, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    actual_reward = TOTAL_REWARD
    pledge_agent.claimReward(operators)
    assert tracker.delta() == actual_reward - FEE


def test_claim_reward_validator_address_empty(btc_agent, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[2], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    actual_reward = TOTAL_REWARD * 3
    pledge_agent.claimReward([])
    assert tracker.delta() == actual_reward


def test_claim_validator_reward_individually(btc_agent, pledge_agent, set_candidate):
    accounts[0].transfer(pledge_agent, ONE_ETHER)
    operators, consensuses = set_candidate
    pledge_agent.setRewardMap(accounts[0], TOTAL_REWARD // 2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    proxy_claim_reward_success(operators[:1], accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2

# getDelegator
def test_query_data_in_new_contract(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 3)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    delegator0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert delegator0 == [MIN_INIT_DELEGATE_VALUE * 2,
                          MIN_INIT_DELEGATE_VALUE * 2, get_current_round(), 0,
                          MIN_INIT_DELEGATE_VALUE, 0]
    delegator1 = pledge_agent.getDelegator(operators[1], accounts[0])
    assert delegator1 == [0, MIN_INIT_DELEGATE_VALUE, get_current_round(), 0, 0, 0]


def test_query_no_data_found(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegator0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert sum(delegator0) == 0




def test_query_info_after_reoffender_verifier(pledge_agent, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 3)
    change_round = get_current_round()
    turn_round(consensuses)
    slash_threshold = slash_indicator.felonyThreshold()
    event_name = 'validatorFelony'
    tx = None
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    turn_round(consensuses)
    delegator0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert delegator0 == [0, MIN_INIT_DELEGATE_VALUE * 3, change_round, 0, 0, 0]
    undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    delegator0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert delegator0 == [MIN_INIT_DELEGATE_VALUE, MIN_INIT_DELEGATE_VALUE, get_current_round(), 0, 0, 0]


@pytest.mark.parametrize("tests", ['delegate', 'undelgate', 'transfer'])
def test_proxy_staking_success(stake_hub, pledge_agent, core_agent, set_candidate, tests):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=1)
    if tests == 'delegate':
        tx = proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
        assert 'delegatedCoin' in tx.events
    elif tests == 'undelgate':
        tx = proxy_undelegate_coin_success(operators[0], accounts[1], 0)
        assert 'undelegatedCoin' in tx.events
    elif tests == 'transfer':
        tx = proxy_transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount)
        assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_unstaking_success(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
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
    tx = proxy_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    assert 'undelegatedCoin' in tx.events
    turn_round(consensuses, round_count=round_count)
    proxy_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward + undelegate_value
    if round_count == 0:
        actual_reward = undelegate_value
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_unstaking_after_multiple_rounds(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
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
    proxy_undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    proxy_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    proxy_claim_reward_success(operators, accounts[0])
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
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
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
    tx = proxy_transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    assert 'transferredCoin' in tx.events
    turn_round(consensuses, round_count=round_count)
    proxy_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward + old_candidate_reward
    if round_count == 0:
        actual_reward = 0
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
@pytest.mark.parametrize("part", [True, False])
def test_proxy_transfer_after_multiple_rounds(stake_hub, pledge_agent, core_agent, set_candidate, part, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
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
    proxy_transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    proxy_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    proxy_claim_reward_success(operators, accounts[0])
    actual_reward = actual_reward + round_reward
    if round_count == 0:
        actual_reward = TOTAL_REWARD // 2
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [0, 1, 2, 3])
def test_proxy_delegate_success(stake_hub, pledge_agent, core_agent, set_candidate, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    tracker = get_tracker(accounts[0])
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
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
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    turn_round(consensuses, round_count=round_count)
    accrued_reward = 6772500
    actual_reward = TOTAL_REWARD // 2
    round_reward = delegate_amount * round_count * accrued_reward // Utils.CORE_STAKE_DECIMAL
    tracker = get_tracker(accounts[0])
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_claim_reward_success(operators, accounts[0])
    turn_round(consensuses, round_count=2)
    actual_reward += TOTAL_REWARD * 2 // 3
    proxy_claim_reward_success(operators, accounts[0])
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
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    if tests == 'undelgate':
        proxy_undelegate_coin_success(operators[0], accounts[0], delegate_amount)
    elif tests == 'transfer':
        proxy_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    turn_round()
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=round_count)
    if tests == 'undelgate':
        proxy_undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    elif tests == 'transfer':
        proxy_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['undelgate', 'transfer'])
def test_current_round_transfer_can_cancel_and_transfer(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    proxy_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=round_count)
    if tests == 'undelgate':
        proxy_undelegate_coin_success(operators[1], accounts[0], delegate_amount)
    elif tests == 'transfer':
        proxy_transfer_coin_success(operators[1], operators[2], accounts[0], delegate_amount)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['delegate', 'transfer'])
def test_proxy_undelegate_cancel_all(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    if tests == 'delegate':
        delegate_coin_success(operators[1], accounts[0], delegate_amount)
    else:
        proxy_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=round_count)
    tracker = get_tracker(accounts[0])
    proxy_undelegate_coin_success(operators[1], accounts[0], 0)
    actual_amount = delegate_amount * 2
    assert tracker.delta() == actual_amount
    turn_round(consensuses)


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", ['delegate', 'transfer'])
def test_proxy_transfer_cancel_all(stake_hub, core_agent, set_candidate, tests, round_count):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    if tests == 'delegate':
        delegate_coin_success(operators[1], accounts[0], delegate_amount)
    else:
        proxy_transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=round_count)
    tx = proxy_transfer_coin_success(operators[1], operators[2], accounts[0], 0)
    actual_amount = delegate_amount * 2
    assert tx.events['transferredCoin']['amount'] == actual_amount
    assert tx.events['transferredCoin']['realtimeAmount'] == actual_amount
    turn_round(consensuses)


def test_cancel_after_all_already_cancelled(stake_hub, core_agent, set_candidate):
    delegate_amount = 1000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    proxy_undelegate_coin_success(operators[1], accounts[0], 0)
    turn_round(consensuses, round_count=2)
    with brownie.reverts("Undelegate zero coin"):
        proxy_undelegate_coin_success(operators[1], accounts[0], 0)
    __check_delegate_info(operators[1], accounts[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0,
        'changeRound': 0,
        'transferredAmount': 0
    })


def test_cancel_stake_with_zero_amount(stake_hub, core_agent, set_candidate):
    delegate_amount = 10000
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_transfer_coin_success(operators[0], operators[2], accounts[0], 0)
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
    power_value = 5
    operators, consensuses = set_candidate
    turn_round()
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_amount, LOCK_SCRIPT)
    tx_id = delegate_btc_success(operators[0], accounts[1], btc_amount, LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[0], accounts[3], power_value)
    turn_round()
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_undelegate_coin_success(operators[0], accounts[0], 0)
    transfer_btc_success(tx_id, operators[2], accounts[1])
    proxy_transfer_coin_success(operators[0], operators[2], accounts[1], 0)
    turn_round(consensuses)
    trackers = get_trackers(accounts[:4])
    stake_hub_claim_reward(accounts[0])
    proxy_claim_reward_success(operators, accounts[1])
    stake_hub_claim_reward(accounts[2])
    proxy_claim_reward_success(operators, accounts[3])
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
    })
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == account_rewards.get(tracker.address, 0)


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
        proxy_delegate_coin_success(op, accounts[0], delegate_amount)
        proxy_delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    if inter_round_cancel:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        expect_reward += TOTAL_REWARD // 2 * 3
    proxy_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    tx = proxy_undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
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
        proxy_delegate_coin_success(op, accounts[0], delegate_value)
        proxy_delegate_coin_success(op, accounts[1], delegate_value)
    turn_round()
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        proxy_delegate_coin_success(op, accounts[0], delegate_value)
        if old:
            delegate_coin_success(op, accounts[1], delegate_value)
        else:
            proxy_delegate_coin_success(op, accounts[1], delegate_value)
    if old:
        proxy_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    else:
        transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    for index, a in enumerate(agent_index):
        proxy_undelegate_coin_success(operators[a], accounts[0], undelegate_amount[index])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    proxy_claim_reward_success(operators, accounts[0])
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
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    proxy_transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    tracker0 = get_tracker(accounts[0])
    proxy_undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses, round_count=round_count)
    proxy_claim_reward_success(operators, accounts[0])
    if round_count == 0:
        expect_reward = 0
    elif round_count > 1:
        expect_reward = tests['tow_round_reward']
    assert tracker0.delta() == expect_reward + undelegate_amount


def test_claim_rewards_after_cancel_all_in_two_rounds(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    proxy_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    proxy_undelegate_coin_success(operators[0], accounts[0], 0)
    proxy_undelegate_coin_success(operators[2], accounts[0], 0)
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=2)
    proxy_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == 0
    turn_round(consensuses, round_count=2)
    proxy_claim_reward_success(operators, accounts[0])
    assert tracker0.delta() == 0


@pytest.mark.parametrize("tests", ['transfer', 'undelegate'])
def test_cancel_and_transfer_after_adding_stake(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[1], accounts[0], delegate_amount)
    if tests == 'transfer':
        proxy_transfer_coin_success(operators[0], operators[1], accounts[0], 0)
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
        proxy_undelegate_coin_success(operators[0], accounts[0], 0)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': 0,
            'transferredAmount': 0,
        })
        expect_reward = 0
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    proxy_claim_reward_success(operators, accounts[0])
    assert tracker.delta() == expect_reward


@pytest.mark.parametrize("tests", ['transfer', 'undelegate'])
def test_cancel_all_after_transfer(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    proxy_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    proxy_delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round()
    proxy_transfer_coin_success(operators[1], operators[0], accounts[0], 0)
    if tests == 'transfer':
        proxy_transfer_coin_success(operators[0], operators[2], accounts[0], 0)
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
        proxy_undelegate_coin_success(operators[0], accounts[0], 0)
        __check_delegate_info(operators[0], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': 0,
            'changeRound': 0,
            'transferredAmount': 0,
        })
        expect_reward = 0
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    proxy_claim_reward_success(operators, accounts[0])
    assert tracker.delta() == expect_reward


def __register_candidates(agents=None):
    operators = []
    consensuses = []
    if agents is None:
        agents = accounts[2:5]
    for operator in agents:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def __get_delegator_info(candidate, delegator):
    delegator_info = CoreAgentMock[0].getDelegator(candidate, delegator)
    return delegator_info


def __check_delegate_info(candidate, delegator, result: dict):
    new_info = __get_delegator_info(candidate, delegator)
    for i in result:
        assert new_info[i] == result[i]

