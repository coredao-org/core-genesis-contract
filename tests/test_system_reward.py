import math

import pytest
import brownie
from web3 import Web3
from brownie import *
from .utils import expect_event, get_tracker, random_address, padding_left

account_tracker = None
system_reward_tracker = None
burn_tracker = None
foundation_tracker = None


@pytest.fixture(scope="module", autouse=True)
def set_up(validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub,
           gov_hub, pledge_agent, burn, foundation):
    system_reward.updateContractAddr(
        validator_set.address,
        slash_indicator.address,
        system_reward.address,
        btc_light_client.address,
        relay_hub.address,
        candidate_hub.address,
        accounts[0],
        pledge_agent.address,
        burn.address,
        foundation.address
    )

    global account_tracker
    global system_reward_tracker
    global burn_tracker
    global foundation_tracker

    account_tracker = get_tracker(accounts[0])
    system_reward_tracker = get_tracker(system_reward)
    burn_tracker = get_tracker(burn)
    foundation_tracker = get_tracker(foundation)


@pytest.fixture(autouse=True)
def clear_tracker():
    account_tracker.balance()
    system_reward_tracker.balance()
    burn_tracker.balance()
    foundation_tracker.balance()


def __balance_check(account_delta=0, system_delta=0, burn_delta=0, foundation_delta=0):
    assert account_tracker.delta() == account_delta
    assert system_reward_tracker.delta() == system_delta
    assert burn_tracker.delta() == burn_delta
    assert foundation_tracker.delta() == foundation_delta


def test_update_param_failed_with_unknown_key(system_reward):
    with brownie.reverts("unknown param"):
        system_reward.updateParam("known", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_incentive_balance_cap_with_unmatched_length(system_reward):
    with brownie.reverts("length of incentiveBalanceCap mismatch"):
        system_reward.updateParam("incentiveBalanceCap", "0x0000000000123")


def test_update_param_incentive_balance_cap_with_value_out_of_range(system_reward):
    with brownie.reverts("the incentiveBalanceCap out of range"):
        system_reward.updateParam("incentiveBalanceCap", "0x0000000000000000000000000000000000000000000000000000000000000000")


def test_update_param_incentive_balance_cap_success(system_reward):
    tx = system_reward.updateParam("incentiveBalanceCap", "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000")
    expect_event(tx, "paramChange", {
        "key": "incentiveBalanceCap",
        "value": "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000"
    })


@pytest.mark.parametrize("value,success", [(0, True), (1, True), (2, False), (int(math.pow(2, 256))-1, False)])
def test_update_param_is_burn(system_reward, value, success):
    if success:
        system_reward.updateParam("isBurn", padding_left(Web3.toHex(value), 64))
    else:
        with brownie.reverts("the newIsBurn out of range"):
            system_reward.updateParam("isBurn", padding_left(Web3.toHex(value), 64))


def test_receive_rewards_with_value_0(system_reward):
    tx = system_reward.receiveRewards({'value': 0})
    assert len(tx.events.keys()) == 0
    __balance_check(account_delta=0, system_delta=0)


def test_receive_rewards_success_with_balance_less_than_incentive_balance_cap(system_reward):
    value = Web3.toWei(2, 'ether')
    tx = system_reward.receiveRewards({'value': value})
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": value
    })
    __balance_check(account_delta=0-value, system_delta=value)


def test_receive_rewards_success_with_balance_equal_to_incentive_balance_cap(system_reward):
    incentive_balance_cap = system_reward.incentiveBalanceCap()
    init_balance = incentive_balance_cap - Web3.toWei(1, 'ether')
    accounts[0].transfer(system_reward.address, init_balance)

    value = Web3.toWei(1, 'ether')
    tx = system_reward.receiveRewards({'value': value})
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": value
    })
    __balance_check(account_delta=(init_balance + value) * -1, system_delta=init_balance + value)


@pytest.mark.parametrize("is_burn", [False, True])
def test_receive_rewards_success_with_balance_more_than_incentive_balance_cap(system_reward, foundation, burn, is_burn):
    if is_burn:
        system_reward.updateParam("isBurn", padding_left(Web3.toHex(1), 64))

    incentive_balance_cap = system_reward.incentiveBalanceCap()
    init_balance = incentive_balance_cap - Web3.toWei(1, 'ether')
    accounts[0].transfer(system_reward.address, init_balance)

    value = Web3.toWei(2, 'ether')
    tx = system_reward.receiveRewards({'value': value})
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": value
    })
    if is_burn:
        __balance_check(
            account_delta=(init_balance + value) * -1,
            system_delta=incentive_balance_cap,
            burn_delta=init_balance + value - incentive_balance_cap,
        )
    else:
        __balance_check(
            account_delta=(init_balance + value) * -1,
            system_delta=incentive_balance_cap,
            foundation_delta=init_balance + value - incentive_balance_cap
        )


def test_claim_rewards_failed_with_address_which_is_not_operator(system_reward):
    with brownie.reverts("only operator is allowed to call the method"):
        system_reward.claimRewards(accounts[1], 1)


def test_claim_rewards_emit_empty_with_amount_0(system_reward):
    system_reward.setOperator(accounts[0])
    tx = system_reward.claimRewards(accounts[1], 0)
    expect_event(tx, "rewardEmpty")


def test_claim_rewards_success_with_amount_less_than_balance(system_reward):
    system_reward.setOperator(accounts[0])
    accounts[3].transfer(system_reward.address, Web3.toWei(3, 'ether'))
    tx = system_reward.claimRewards(accounts[0], Web3.toWei(1, 'ether'))
    expect_event(tx, "rewardTo", {
        "to": accounts[0],
        "amount": Web3.toWei(1, 'ether')
    })


def test_claim_rewards_success_with_amount_bigger_than_balance(system_reward):
    system_reward.setOperator(accounts[0])
    accounts[3].transfer(system_reward.address, Web3.toWei(1, 'ether'))
    tx = system_reward.claimRewards(accounts[0], Web3.toWei(3, 'ether'))
    expect_event(tx, "rewardTo", {
        "to": accounts[0],
        "amount": Web3.toWei(1, 'ether')
    })


def test_receive_token_success(system_reward):
    tx = accounts[0].transfer(system_reward.address, 1)
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": 1
    })
    tx = accounts[0].transfer(system_reward.address, 0)
    assert len(tx.events.keys()) == 0


def test_is_operator_works(system_reward, btc_light_client):
    for account in accounts[:5]:
        assert system_reward.isOperator(account) is False
    assert system_reward.isOperator(btc_light_client.address) is True


def test_claim_reward_success(system_reward):
    target_account = random_address()
    system_reward.setOperator(accounts[1])
    accounts[0].transfer(system_reward.address, 10)

    tx = system_reward.claimRewards(target_account, 2, {'from': accounts[1]})
    expect_event(tx, 'rewardTo', {
        'to': target_account,
        'amount': 2
    })
    assert brownie.web3.eth.get_balance(target_account) == 2
    assert brownie.web3.eth.get_balance(system_reward.address) == 8


def test_claim_reward_failed(system_reward):
    accounts[0].transfer(system_reward.address, 1)
    with brownie.reverts("only operator is allowed to call the method"):
        system_reward.claimRewards(accounts[1], 1)


def test_claim_empty_reward(system_reward):
    target_account = random_address()
    system_reward.setOperator(accounts[1])
    tx = system_reward.claimRewards(target_account, 0, {'from': accounts[1]})
    expect_event(tx, 'rewardEmpty')
    assert brownie.web3.eth.get_balance(target_account) == 0


