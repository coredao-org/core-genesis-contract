import math

import pytest
import brownie
import rlp
from eth_abi import encode
from eth_utils import to_bytes
from web3 import Web3
from brownie import *

from .common import execute_proposal, turn_round, register_candidate
from .constant import Utils
from .utils import expect_event, get_tracker, random_address, padding_left, encode_args_with_signature, \
    update_system_contract_address

account_tracker = None
system_reward_tracker = None
burn_tracker = None
foundation_tracker = None


@pytest.fixture(scope="module", autouse=True)
def set_up(system_reward, burn, foundation):
    update_system_contract_address(system_reward, gov_hub=accounts[0])
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


@pytest.fixture()
def init_system_reward_balance(system_reward):
    incentive_balance = 10000000e18
    system_reward.receiveRewards({'value': incentive_balance, 'from': accounts[97]})
    assert system_reward.balance() == incentive_balance


def __balance_check(account_delta=0, system_delta=0, burn_delta=0, foundation_delta=0):
    assert account_tracker.delta() == account_delta
    assert system_reward_tracker.delta() == system_delta
    assert burn_tracker.delta() == burn_delta
    assert foundation_tracker.delta() == foundation_delta


def test_update_param_failed_with_unknown_key(system_reward):
    with brownie.reverts("UnsupportedGovParam: known"):
        system_reward.updateParam("known", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_incentive_balance_cap_with_unmatched_length(system_reward):
    with brownie.reverts("MismatchParamLength: incentiveBalanceCap"):
        system_reward.updateParam("incentiveBalanceCap", "0x0000000000123")


def test_update_param_incentive_balance_cap_with_value_out_of_range(system_reward):
    uint256_max = 2 ** 256 - 1
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ['incentiveBalanceCap', 0, 1, uint256_max]
    )
    with brownie.reverts(error_msg):
        system_reward.updateParam("incentiveBalanceCap",
                                  "0x0000000000000000000000000000000000000000000000000000000000000000")


def test_update_param_incentive_balance_cap_success(system_reward):
    tx = system_reward.updateParam("incentiveBalanceCap",
                                   "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000")
    expect_event(tx, "paramChange", {
        "key": "incentiveBalanceCap",
        "value": "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000"
    })


@pytest.mark.parametrize("value,success", [(0, True), (1, True), (2, False), (6, False),
                                           (int(math.pow(2, 256)) - 1, False)])
def test_update_param_is_burn(system_reward, value, success):
    if success:
        system_reward.updateParam("isBurn", value)
        assert system_reward.isBurn() == value
    else:
        if len(str(value)) > 1:
            with brownie.reverts("MismatchParamLength: isBurn"):
                system_reward.updateParam("isBurn", value)
        else:
            if value > 1:
                with brownie.reverts(f"OutOfBounds: isBurn, {value}, 0, 1"):
                    system_reward.updateParam("isBurn", value)


def test_receive_rewards_with_value_0(system_reward):
    tx = system_reward.receiveRewards({'value': 0})
    assert len(tx.events.keys()) == 0
    __balance_check(account_delta=0, system_delta=0)


def test_receive_rewards_success_with_balance_less_than_incentive_balance_cap(system_reward):
    value = Web3.to_wei(2, 'ether')
    tx = system_reward.receiveRewards({'value': value})
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": value
    })
    __balance_check(account_delta=0 - value, system_delta=value)


def test_receive_rewards_success_with_balance_equal_to_incentive_balance_cap(system_reward):
    incentive_balance_cap = system_reward.incentiveBalanceCap()
    init_balance = incentive_balance_cap - Web3.to_wei(1, 'ether')
    accounts[0].transfer(system_reward.address, init_balance)

    value = Web3.to_wei(1, 'ether')
    tx = system_reward.receiveRewards({'value': value})
    expect_event(tx, "receiveDeposit", {
        'from': accounts[0],
        "amount": value
    })
    __balance_check(account_delta=(init_balance + value) * -1, system_delta=init_balance + value)


@pytest.mark.parametrize("is_burn", [False, True])
def test_receive_rewards_success_with_balance_more_than_incentive_balance_cap(system_reward, foundation, burn, is_burn):
    if is_burn:
        system_reward.updateParam("isBurn", 1)

    incentive_balance_cap = system_reward.incentiveBalanceCap()
    init_balance = incentive_balance_cap - Web3.to_wei(1, 'ether')
    accounts[0].transfer(system_reward.address, init_balance)

    value = Web3.to_wei(2, 'ether')
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
    accounts[3].transfer(system_reward.address, Web3.to_wei(3, 'ether'))
    tx = system_reward.claimRewards(accounts[0], Web3.to_wei(1, 'ether'))
    expect_event(tx, "rewardTo", {
        "to": accounts[0],
        "amount": Web3.to_wei(1, 'ether')
    })


def test_claim_rewards_success_with_amount_bigger_than_balance(system_reward):
    system_reward.setOperator(accounts[0])
    accounts[3].transfer(system_reward.address, Web3.to_wei(1, 'ether'))
    tx = system_reward.claimRewards(accounts[0], Web3.to_wei(3, 'ether'))
    expect_event(tx, "rewardTo", {
        "to": accounts[0],
        "amount": Web3.to_wei(1, 'ether')
    })


def test_single_whitelist_address_receive_rewards_success(system_reward, stake_hub, init_system_reward_balance):
    percentage = 5000
    burn_reward = 100e18
    __add_whitelist(stake_hub, percentage)
    tracker = get_tracker(stake_hub)
    tx = system_reward.receiveRewards({'value': burn_reward})
    assert tx.events['whitelistTransferSuccess'] == [stake_hub.address, burn_reward // 2]
    assert tracker.delta() == burn_reward // 2


def test_multiple_whitelist_addresses_receive_rewards_success(system_reward, stake_hub, init_system_reward_balance):
    percentage = 2000
    burn_reward = 100e18
    __add_whitelist(stake_hub, percentage * 2)
    __add_whitelist(accounts[1], percentage)
    __add_whitelist(accounts[2], percentage // 2)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == burn_reward * (percentage * 2) // Utils.DENOMINATOR
    assert tracker1.delta() == burn_reward * percentage // Utils.DENOMINATOR
    assert tracker2.delta() == burn_reward * (percentage // 2) // Utils.DENOMINATOR


@pytest.mark.parametrize("is_receive_all", [True, False])
def test_whitelist_receive_all_rewards(system_reward, stake_hub, init_system_reward_balance, is_receive_all):
    percentage = 2000
    burn_reward = 100e18
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], percentage)
    new_percentage = percentage
    if is_receive_all:
        new_percentage = Utils.DENOMINATOR - percentage * 2
    __add_whitelist(accounts[2], new_percentage)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    system_reward.receiveRewards({'value': burn_reward})
    receive_amount0 = burn_reward * percentage // Utils.DENOMINATOR
    receive_amount1 = burn_reward * new_percentage // Utils.DENOMINATOR
    assert tracker0.delta() == receive_amount0
    assert tracker1.delta() == receive_amount0
    assert tracker2.delta() == receive_amount1


@pytest.mark.parametrize("is_burn_limit", [True, False])
def test_whitelist_incomplete_rewards_with_burn_enabled(system_reward, burn, stake_hub, init_system_reward_balance,
                                                        is_burn_limit):
    percentage = 2000
    burn_reward = 100e18
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], percentage)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    system_reward.updateParam("isBurn", 1)
    assert system_reward.isBurn() is True
    receive_amount0 = burn_reward * percentage // Utils.DENOMINATOR
    burn_balance = burn_reward - receive_amount0 * 2
    refund_partial_amount = 0
    if is_burn_limit:
        new_cap = int(25e18)
        hex_value = padding_left(Web3.to_hex(new_cap), 64)
        execute_proposal(
            burn.address,
            0,
            "updateParam(string,bytes)",
            encode(['string', 'bytes'], ['burnCap', Web3.to_bytes(hexstr=hex_value)]),
            "update burn cap"
        )
        burn_balance = new_cap
        refund_partial_amount = burn_reward - receive_amount0 * 2 - new_cap
    tracker2 = get_tracker(burn)
    tracker3 = get_tracker(system_reward)
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == receive_amount0
    assert tracker1.delta() == receive_amount0
    assert tracker2.delta() == burn_balance
    assert tracker3.delta() == refund_partial_amount


def test_whitelist_incomplete_rewards_with_burn_disabled(system_reward, burn, stake_hub, init_system_reward_balance,
                                                         foundation):
    percentage = 2000
    burn_reward = 200e18
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], percentage)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    system_reward.updateParam("isBurn", 0)
    assert system_reward.isBurn() is False
    receive_amount0 = burn_reward * percentage // Utils.DENOMINATOR
    tracker2 = get_tracker(burn)
    tracker3 = get_tracker(system_reward)
    tracker4 = get_tracker(foundation)
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == tracker1.delta() == receive_amount0
    assert tracker2.delta() == 0
    assert tracker3.delta() == 0
    assert tracker4.delta() == burn_reward - receive_amount0 * 2


def test_whitelist_empty(system_reward, burn, stake_hub, init_system_reward_balance,
                         foundation):
    percentage = 2000
    burn_reward = 200e18
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], percentage)
    __remove_whitelist(accounts[1])
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(foundation)
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == burn_reward * percentage // Utils.DENOMINATOR
    assert tracker1.delta() == 0
    assert tracker2.delta() == burn_reward - burn_reward * percentage // Utils.DENOMINATOR
    __remove_whitelist(stake_hub)
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == tracker1.delta() == 0
    assert tracker2.delta() == burn_reward


def test_successful_percentage_based_distribution(system_reward, burn, stake_hub,
                                                  init_system_reward_balance,
                                                  foundation):
    percentage = 2000
    burn_reward = 200e18
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], percentage)
    __modify_whitelist(stake_hub, percentage * 4)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(foundation)
    system_reward.receiveRewards({'value': burn_reward})
    assert tracker0.delta() == burn_reward - burn_reward * percentage // Utils.DENOMINATOR
    assert tracker1.delta() == burn_reward * percentage // Utils.DENOMINATOR
    assert tracker2.delta() == 0


def test_no_rewards_check_burn_amount(stake_hub, validator_set, init_system_reward_balance):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    percentage = 4000
    __add_whitelist(stake_hub, percentage)
    __add_whitelist(accounts[1], Utils.DENOMINATOR - percentage)
    tracker0 = get_tracker(stake_hub)
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses)
    tx_fee = 100
    block_reward = validator_set.blockReward()
    total_block_reward = block_reward + tx_fee
    burn_amount = total_block_reward // 10
    assert tracker0.delta() == burn_amount * 3 * percentage // Utils.DENOMINATOR
    assert tracker1.delta() == burn_amount * 3 - burn_amount * 3 * percentage // Utils.DENOMINATOR


def test_whitelist_address_forbidden_to_receive_funds(stake_hub, burn, validator_set, init_system_reward_balance):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    percentage = 4000
    __add_whitelist(burn, percentage)
    __add_whitelist(accounts[1], Utils.DENOMINATOR - percentage)
    tracker0 = get_tracker(burn)
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses)
    tx_fee = 100
    block_reward = validator_set.blockReward()
    total_block_reward = block_reward + tx_fee
    burn_amount = total_block_reward // 10
    assert tracker0.delta() == 0
    assert tracker1.delta() == burn_amount * 3 - burn_amount * 3 * percentage // Utils.DENOMINATOR


@pytest.mark.parametrize("is_burn", [True, False])
def test_funds_forbidden_are_burned(system_reward, burn, foundation, validator_set, init_system_reward_balance,
                                    is_burn):
    burn_reward = 200e18
    percentage0 = 2000
    __add_whitelist(burn, percentage0)
    __add_whitelist(accounts[1], Utils.DENOMINATOR - percentage0 * 2)
    foundation_tracker = get_tracker(foundation)
    if is_burn:
        system_reward.updateParam("isBurn", 1)
    else:
        system_reward.updateParam("isBurn", 0)
    tx = system_reward.receiveRewards({'value': burn_reward})
    assert tx.events['whitelistTransferFailed']['value'] == burn_reward * percentage0 // Utils.DENOMINATOR
    if is_burn:
        assert tx.events['burned']['amount'] == burn_reward * (percentage0 * 2) // Utils.DENOMINATOR
        assert foundation_tracker.delta() == 0
    else:
        assert foundation_tracker.delta() == burn_reward * (percentage0 * 2) // Utils.DENOMINATOR
        assert 'burned' not in tx.events


def test_whitelist_forbidden_funds_after_round_switch(stake_hub, burn, validator_set, init_system_reward_balance):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    percentage = 4000
    __add_whitelist(burn, percentage)
    __add_whitelist(accounts[1], Utils.DENOMINATOR - percentage)
    tracker0 = get_tracker(burn)
    turn_round(consensuses)
    assert tracker0.delta() == 0
    turn_round(consensuses)


def test_revert_when_whitelist_address_receives_funds(btc_lst_stake, system_reward, stake_hub, lst_token):
    incentive_balance_cap = system_reward.incentiveBalanceCap()
    accounts[0].transfer(system_reward.address, incentive_balance_cap)
    turn_round()
    burn_reward = 10000000
    btc_lst_stake = delegateBtcLstProxy.deploy(btc_lst_stake.address, stake_hub.address, lst_token,
                                               {'from': accounts[0]})
    __add_whitelist(btc_lst_stake, Utils.DENOMINATOR // 4)
    __add_whitelist(accounts[2], Utils.DENOMINATOR // 4)
    __add_whitelist(stake_hub, Utils.DENOMINATOR // 2)
    tx = system_reward.receiveRewards({'value': burn_reward})
    assert tx.events['whitelistTransferFailed'] == [btc_lst_stake.address, burn_reward // 4]
    actual_reward = [[accounts[2], burn_reward // 4], [stake_hub, burn_reward // 2]]
    for index, t in enumerate(tx.events['whitelistTransferSuccess']):
        assert t['member'] == actual_reward[index][0]
        assert t['value'] == actual_reward[index][1]


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


def test_add_whitelist(system_reward):
    percentage = 1000
    white_list0 = [to_bytes(hexstr=accounts[0].address), percentage]
    white_list_encode = rlp.encode(white_list0)
    system_reward.updateParam("addWhiteList", white_list_encode, {'from': accounts[0]})
    white_list_set = system_reward.getWhiteListSet(0)
    assert white_list_set == [accounts[0], percentage]
    assert system_reward.whiteLists(accounts[0]) == 1
    white_list1 = [to_bytes(hexstr=accounts[1].address), percentage * 2]
    white_list_encode = rlp.encode(white_list1)
    system_reward.updateParam("addWhiteList", white_list_encode)
    white_list_set = system_reward.getWhiteListSet(1)
    assert white_list_set == [accounts[1], percentage * 2]
    assert system_reward.whiteLists(accounts[1]) == 2


def test_add_duplicate_whitelist(system_reward):
    percentage = 1000
    white_list0 = [to_bytes(hexstr=accounts[0].address), percentage]
    white_list_encode = rlp.encode(white_list0)
    system_reward.updateParam("addWhiteList", white_list_encode)
    with brownie.reverts("whitelist member already exists"):
        system_reward.updateParam("addWhiteList", white_list_encode)


def test_add_whitelist_exceeds_percentage_limit(system_reward):
    percentage = 1000
    max_percentage = 10000
    white_list0 = [to_bytes(hexstr=accounts[0].address), max_percentage + 1]
    white_list_encode = rlp.encode(white_list0)
    with brownie.reverts(f"OutOfBounds: addWhiteList, {max_percentage + 1}, 1, 10000"):
        system_reward.updateParam("addWhiteList", white_list_encode, {'from': accounts[0]})
    white_list1 = [to_bytes(hexstr=accounts[1].address), percentage * 2]
    white_list_encode = rlp.encode(white_list1)
    system_reward.updateParam("addWhiteList", white_list_encode)
    white_list1 = [to_bytes(hexstr=accounts[2].address), max_percentage + 1 - percentage * 2]
    white_list_encode = rlp.encode(white_list1)
    with brownie.reverts("total precentage exceeds the upper limit"):
        system_reward.updateParam("addWhiteList", white_list_encode)


def test_add_whitelist_with_zero_percentage(system_reward):
    white_list0 = [to_bytes(hexstr=accounts[0].address), 0]
    white_list_encode = rlp.encode(white_list0)
    with brownie.reverts(f"OutOfBounds: addWhiteList, 0, 1, 10000"):
        system_reward.updateParam("addWhiteList", white_list_encode, {'from': accounts[0]})


def test_delete_whitelist_success(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    assert system_reward.whiteLists(accounts[1]) == 1
    __remove_whitelist(accounts[1])
    assert system_reward.getWhiteListSetLength() == system_reward.whiteLists(accounts[1]) == 0
    for i in range(4):
        __add_whitelist(accounts[i], percentage + i, i)
    __remove_whitelist(accounts[1])
    expect_list = [[accounts[0], percentage], [accounts[3], percentage + 3], [accounts[2], percentage + 2]]
    expect_index = [1, 0, 3, 2]
    for i in range(3):
        assert system_reward.getWhiteListSet(i) == expect_list[i]
    for index, account in enumerate(accounts[:4]):
        assert system_reward.whiteLists(account) == expect_index[index]
    __remove_whitelist(accounts[2])
    assert system_reward.getWhiteListSet(1) == expect_list[1]


def test_delete_nonexistent_whitelist(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    with brownie.reverts(f"whitelist member does not exist"):
        __remove_whitelist(accounts[2])


def test_remove_all_whitelist(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    __add_whitelist(accounts[2], percentage, 1)
    __remove_whitelist(accounts[1])
    __remove_whitelist(accounts[2])
    assert system_reward.getWhiteListSetLength() == 0
    __add_whitelist(accounts[1], percentage, 0)
    assert system_reward.getWhiteListSetLength() == 1
    assert system_reward.getWhiteListSet(0) == [accounts[1], percentage]


def test_update_whitelist_success(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    __modify_whitelist(accounts[1], percentage * 2, 0)
    __modify_whitelist(accounts[1], percentage * 3, 0)
    __add_whitelist(accounts[2], percentage + 1, 1)
    __add_whitelist(accounts[3], percentage + 2, 2)
    __modify_whitelist(accounts[2], percentage * 3, 1)
    assert system_reward.getWhiteListSet(1) == [accounts[2], percentage * 3]


def test_update_nonexistent_whitelist(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    with brownie.reverts(f"whitelist member does not exist"):
        __modify_whitelist(accounts[2], percentage * 2, 0)


def test_update_whitelist_exceed_max_percentage(system_reward):
    percentage = 10000
    __add_whitelist(accounts[1], percentage // 2, 0)
    with brownie.reverts(f"OutOfBounds: modifyWhiteList, 10001, 1, 10000"):
        __modify_whitelist(accounts[1], percentage + 1, 0)
    __add_whitelist(accounts[2], percentage // 2, 1)
    with brownie.reverts(f"total precentage exceeds the upper limit"):
        __modify_whitelist(accounts[1], percentage // 2 + 1, 0)


def test_update_whitelist_with_zero_percentage(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    with brownie.reverts(f"whitelist member does not exist"):
        __modify_whitelist(accounts[2], percentage * 2, 0)


def test_only_gov_can_manage_whitelist(system_reward):
    percentage = 1000
    white_list0 = [to_bytes(hexstr=accounts[0].address), percentage]
    white_list_encode = rlp.encode(white_list0)
    with brownie.reverts(f"the msg sender must be governance contract"):
        system_reward.updateParam("addWhiteList", white_list_encode, {'from': accounts[1]})
    with brownie.reverts(f"the msg sender must be governance contract"):
        system_reward.updateParam("removeWhiteList", white_list_encode, {'from': accounts[1]})
    with brownie.reverts(f"the msg sender must be governance contract"):
        system_reward.updateParam("modifyWhiteList", white_list_encode, {'from': accounts[1]})


def test_add_then_update_and_delete_whitelist(system_reward):
    percentage = 1000
    for index, account in enumerate(accounts[:5]):
        __add_whitelist(account, percentage + index, index)
    __modify_whitelist(accounts[2], percentage * 3, 2)
    __modify_whitelist(accounts[3], percentage * 2, 3)
    __remove_whitelist(accounts[2])
    __modify_whitelist(accounts[4], percentage * 3, 2)
    __remove_whitelist(accounts[0])
    assert system_reward.getWhiteListSetLength() == 3
    expect_list = [accounts[3], accounts[1], accounts[4]]
    percentage_list = [percentage * 2, percentage + 1, percentage * 3]
    for index, address in enumerate(expect_list):
        assert system_reward.whiteLists(address) == index + 1
        assert system_reward.getWhiteListSet(index) == [address, percentage_list[index]]


def test_invalid_address_format_on_white_list(system_reward):
    white_list0 = [accounts[0].address, 1000]
    white_list_encode = rlp.encode(white_list0)
    with brownie.reverts():
        system_reward.updateParam("addWhiteList", white_list_encode, {'from': accounts[0]})
    with brownie.reverts():
        system_reward.updateParam("removeWhiteList", accounts[3].address, {'from': accounts[0]})
    with brownie.reverts():
        system_reward.updateParam("__modify_whitelist", white_list_encode, {'from': accounts[0]})


@pytest.mark.parametrize("percentage", [1000, 2000, 3000, 6000, 9999, 10000])
def test_gov_whitelist_success(system_reward, percentage):
    white_list1 = [to_bytes(hexstr=accounts[0].address), percentage]
    white_list_encode1 = rlp.encode(white_list1)
    system_reward.updateParam("addWhiteList", white_list_encode1.hex())
    assert system_reward.getWhiteListSet(0) == [accounts[0].address, percentage]


@pytest.mark.parametrize("percentage", [100000, 100001, 100002])
def test_whitelist_length_error(system_reward, percentage):
    white_list1 = [to_bytes(hexstr=accounts[0].address), percentage]
    white_list_encode1 = rlp.encode(white_list1)
    with brownie.reverts(f"MismatchParamLength: addWhiteList"):
        system_reward.updateParam("addWhiteList", white_list_encode1.hex())


def test_get_white_list_set_success(system_reward):
    percentage = 1000
    __add_whitelist(accounts[1], percentage, 0)
    __add_whitelist(accounts[2], percentage, 1)
    __remove_whitelist(accounts[1])
    __remove_whitelist(accounts[2])
    assert system_reward.getWhiteListSetLength() == 0
    __add_whitelist(accounts[3], percentage, 0)
    __add_whitelist(accounts[4], percentage, 1)
    __add_whitelist(accounts[5], percentage * 2, 2)
    assert system_reward.getWhiteListSet() == [[accounts[3], percentage], [accounts[4], percentage],
                                               [accounts[5], percentage * 2]]


def __add_whitelist(account, percentage, index=None):
    white_list0 = [to_bytes(hexstr=account.address), percentage]
    white_list_encode = rlp.encode(white_list0)
    SystemRewardMock[0].updateParam("addWhiteList", white_list_encode, {'from': accounts[0]})
    if index is not None:
        assert SystemRewardMock[0].getWhiteListSet(index) == [account, percentage]


def __remove_whitelist(remove_address):
    remove_address = to_bytes(hexstr=remove_address.address)
    SystemRewardMock[0].updateParam("removeWhiteList", remove_address, {'from': accounts[0]})


def __modify_whitelist(account, percentage, index=None):
    white_list0 = [to_bytes(hexstr=account.address), percentage]
    white_list_encode = rlp.encode(white_list0)
    SystemRewardMock[0].updateParam("modifyWhiteList", white_list_encode, {'from': accounts[0]})
    if index:
        assert SystemRewardMock[0].getWhiteListSet(index) == [account, percentage]
