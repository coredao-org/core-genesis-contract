import pytest
import rlp

from .calc_reward import set_delegate, parse_delegation, Discount, set_btc_lst_delegate
from .common import register_candidate, turn_round, stake_hub_claim_reward, set_round_tag, execute_proposal
from .delegate import *
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
DELEGATE_VALUE = 2000000
BLOCK_REWARD = 0
BTC_VALUE = 200
COIN_REWARD = 0
BTC_REWARD = 0
COIN_REWARD_NO_POWER = 0
BTC_REWARD_NO_POWER = 0
TX_FEE = 100
FEE = 100
MONTH = 30
YEAR = 360
ONE_ETHER = Web3.to_wei(1, 'ether')
TOTAL_REWARD = 0
# BTC delegation-related
LOCK_TIME = 1736956800
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
# BTCLST delegation-related
BTCLST_LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
BTCLST_REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"
stake_manager = StakeManager()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub, system_reward):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, pledge_agent,
                     btc_lst_stake, gov_hub, hash_power_agent, btc_agent, system_reward):
    global BLOCK_REWARD, FEE, COIN_REWARD, BTC_REWARD_NO_POWER, COIN_REWARD_NO_POWER, BTC_REWARD, TOTAL_REWARD, HASH_POWER_AGENT, BTC_AGENT, stake_manager
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LIGHT_CLIENT, MIN_INIT_DELEGATE_VALUE, CANDIDATE_HUB, BTC_LST_STAKE
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    MIN_INIT_DELEGATE_VALUE = core_agent.requiredCoinDeposit()
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    CANDIDATE_HUB = candidate_hub
    BTC_LIGHT_CLIENT = btc_light_client
    BTC_AGENT = btc_agent
    candidate_hub.setControlRoundTimeTag(True)
    COIN_REWARD = TOTAL_REWARD * HardCap.CORE_HARD_CAP // HardCap.SUM_HARD_CAP
    BTC_REWARD = TOTAL_REWARD * HardCap.BTC_HARD_CAP // HardCap.SUM_HARD_CAP
    COIN_REWARD_NO_POWER = TOTAL_REWARD * HardCap.CORE_HARD_CAP // (HardCap.SUM_HARD_CAP - HardCap.POWER_HARD_CAP)
    BTC_REWARD_NO_POWER = TOTAL_REWARD * HardCap.BTC_HARD_CAP // (HardCap.SUM_HARD_CAP - HardCap.POWER_HARD_CAP)
    # The default staking time is 150 days
    set_block_time_stamp(150, LOCK_TIME)
    tlp_rates, lp_rates = Discount().get_init_discount()
    btc_stake.setInitTlpRates(*tlp_rates)
    btc_agent.setInitLpRates(*lp_rates)
    btc_agent.setIsActive(True)
    btc_agent.setAssetWeight(1)
    system_reward.setOperator(stake_hub.address)
    BTC_LST_STAKE = btc_lst_stake
    HASH_POWER_AGENT = hash_power_agent
    btc_lst_stake.updateParam('add', BTCLST_LOCK_SCRIPT, {'from': gov_hub.address})


@pytest.fixture(scope="module", autouse=True)
def set_relayer_register(relay_hub):
    for account in accounts[:3]:
        relay_hub.setRelayerRegister(account.address, True)


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_delegate_btc_success_public_hash(btc_stake, set_candidate):
    stake_duration = 31
    stake_manager.set_lp_rates()
    set_block_time_stamp(stake_duration, LOCK_TIME)
    operators, consensuses = set_candidate
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_SCRIPT)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': get_transaction_txid(btc_tx),
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + LOCK_SCRIPT,
        'amount': BTC_VALUE
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    reward, _ = __calc_btc_deducted_stake_duration_reward(TOTAL_REWARD, stake_duration)
    assert tracker.delta() == reward


@pytest.mark.parametrize("pledge_days", [1, 2, 29, 30, 31, 149, 150, 151, 239, 240, 241, 359, 360, 361])
def test_claim_btc_rewards_for_various_stake_durations(btc_stake, set_candidate, stake_hub,
                                                       pledge_days):
    stake_manager.set_lp_rates()
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, stake_duration=pledge_days)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    reward, unclaimed_reward = __calc_btc_deducted_stake_duration_reward(TOTAL_REWARD, pledge_days)
    assert tracker.delta() == reward
    assert stake_hub.surplus() == unclaimed_reward


def test_no_duration_discount_without_btc_rewards(btc_stake, set_candidate):
    stake_manager.set_lp_rates()
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    assert STAKE_HUB.surplus() == 0


@pytest.mark.parametrize("is_active", [0, 1])
def test_enable_disable_duration_discount(btc_stake, set_candidate, is_active):
    stake_manager.set_lp_rates()
    stake_manager.set_is_btc_stake_active(is_active)
    stake_duration = MONTH
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    if is_active == 0:
        stake_duration = 360
    reward, unclaimed_reward = __calc_btc_deducted_stake_duration_reward(TOTAL_REWARD, stake_duration)
    assert tracker.delta() == reward
    assert STAKE_HUB.surplus() == unclaimed_reward


@pytest.mark.parametrize("is_active", [True, False])
def test_no_stake_duration_rewards(btc_stake, set_candidate, is_active):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD
    assert STAKE_HUB.surplus() == 0


@pytest.mark.parametrize("tlp", [[0, 3000], [2592000, 5000], [9092000, 8000]])
def test_one_level_stake_duration_reward(btc_stake, set_candidate, tlp):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates([tlp])
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    reward, unclaimed_reward = __calc_btc_deducted_stake_duration_reward(TOTAL_REWARD, MONTH,
                                                                         tlp_rates={tlp[0]: tlp[1]})
    assert tracker.delta() == reward
    assert STAKE_HUB.surplus() == unclaimed_reward


@pytest.mark.parametrize("core_rate", [0, 1989, 2001, 5000, 6000, 7000, 9000, 11000, 12001, 13000, 15000, 15001, 16000])
def test_each_bracket_discounted_rewards_accuracy(btc_stake, candidate_hub, btc_light_client, set_candidate, core_agent,
                                                  core_rate, system_reward, stake_hub):
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 2)
    turn_round(consensuses, round_count=2)
    stake_manager.set_stake_hub_delegator_map(accounts[0], 0)
    core_acc_stake_amount = __update_core_stake_amount(accounts[0], core_rate, BTC_VALUE)
    tracker = get_tracker(accounts[0])
    reward, unclaimed_reward = __calc_stake_amount_discount(BLOCK_REWARD // 2, BTC_VALUE, core_acc_stake_amount)
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == reward
    assert STAKE_HUB.surplus() == unclaimed_reward


@pytest.mark.parametrize("core_rate", [1989, 2001, 5000, 6000, 7000, 9000, 11000, 12001, 13000, 15000, 15001, 16000])
def test_btc_reward_discount_by_core_stake_amount(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                  core_agent,
                                                  core_rate, system_reward):
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    if core_rate > 0:
        delegate_coin_success(operators[1], accounts[0], BTC_VALUE * core_rate)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    core_reward = 0
    if core_rate > 0:
        core_reward = TOTAL_REWARD * Utils.CORE_STAKE_DECIMAL // (BTC_VALUE * core_rate) * (
                BTC_VALUE * core_rate) // Utils.CORE_STAKE_DECIMAL
    reward, unclaimed_reward = __calc_stake_amount_discount(TOTAL_REWARD, BTC_VALUE, BTC_VALUE * core_rate)
    tx = stake_hub_claim_reward(accounts[0])
    if core_rate >= 15000:
        assert tx.events['rewardTo']['amount'] == (reward - TOTAL_REWARD)
    assert tracker.delta() == reward + core_reward
    assert STAKE_HUB.surplus() == unclaimed_reward


@pytest.mark.parametrize("core_rate", [0, 4500, 8000, 11000, 12001, 17000])
def test_btc_lst_reward_unaffected_by_core_amount(btc_stake, set_candidate, btc_lst_stake, core_rate):
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    turn_round(consensuses, round_count=3)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    btc_reward = TOTAL_REWARD * 3
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == btc_reward // 2
    assert STAKE_HUB.surplus() == btc_reward - btc_reward // 2


@pytest.mark.parametrize("percentage", [0, 1000, 4500, 5000, 6000, 7000, 10000])
def test_update_btc_lst_percentage_and_claim(btc_stake, set_candidate, btc_lst_stake, percentage):
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT, percentage)
    turn_round(consensuses, round_count=2)
    btc_reward = TOTAL_REWARD * 3
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == btc_reward * percentage // Utils.DENOMINATOR
    assert STAKE_HUB.surplus() == btc_reward - btc_reward * percentage // Utils.DENOMINATOR


@pytest.mark.parametrize("core_rate", [0, 2001, 8000, 12000, 15000, 18000, 22001, 28000])
def test_core_hash_btc_rewards_discounted_by_core_ratio(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                        core_agent, core_rate):
    btc_value = 100
    power_value = 1
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    turn_round(consensuses)
    delegate_power_success(operators[1], accounts[0], value=power_value)
    delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round(consensuses, round_count=2)
    stake_manager.set_stake_hub_delegator_map(accounts[0], 0)
    core_acc_stake_amount = __update_core_stake_amount(accounts[0], core_rate, btc_value)
    btc_reward, btc_unclaimed_reward = __calc_stake_amount_discount(TOTAL_REWARD, btc_value, core_acc_stake_amount)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == btc_reward + TOTAL_REWARD
    assert STAKE_HUB.surplus() == btc_unclaimed_reward


def test_power_btc_discount_conversion_success(btc_stake, btc_agent,
                                               set_candidate, core_agent, stake_hub):
    stake_manager.set_lp_rates([[0, 1000], [10000, 10000], [10001, 1000]])
    btc_agent.setAssetWeight(1e10)
    delegate_amount = 1000000e18
    btc_value = 100e8
    power_value = 1
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    turn_round(consensuses)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_power_success(operators[1], accounts[0], power_value)
    turn_round(consensuses, round_count=2)
    rewards = stake_hub.claimReward.call()
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert rewards[1] == TOTAL_REWARD
    assert rewards[2] == TOTAL_REWARD * Utils.BTC_DECIMAL // btc_value * 100
    assert tracker.delta() == sum(rewards)


def test_multiple_validators_stake_ratio(btc_stake, candidate_hub, btc_light_client,
                                         set_candidate, core_agent):
    stake_manager.set_lp_rates([[0, 1000], [6000, 5000], [6001, 1000]])
    stake_manager.set_tlp_rates()
    delegate_amount = 3000
    btc_value = 1
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses)
    rewards = stake_hub_claim_reward(accounts[0]).return_value
    assert rewards[2] == TOTAL_REWARD // 2


def test_btc_and_core_stake_in_same_validator(btc_stake, candidate_hub, btc_light_client, set_candidate, core_agent):
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    for index in range(3):
        delegate_coin_success(operators[0], accounts[index], DELEGATE_VALUE)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE), set_delegate(accounts[1], DELEGATE_VALUE),
                 set_delegate(accounts[2], DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2, state_map={'core_lp': True})
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]


def test_success_with_over_100_percent_discount(btc_stake, btc_agent, set_candidate):
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_lp_rates([[0, 12000]])
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    for index in range(3):
        delegate_coin_success(operators[0], accounts[index], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' in tx.events


def test_normal_duration_and_reward_discounts(btc_stake, set_candidate, candidate_hub, btc_light_client):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 200
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            stake_amount = delegate_amount
            if i == 0:
                stake_amount = DELEGATE_VALUE
            delegate_coin_success(op, accounts[i], stake_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[1], [accounts[1]] * 10)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE), set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[1],
        "power": [set_delegate(accounts[1], 10)],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE), set_delegate(accounts[1], delegate_amount)],
    }], BLOCK_REWARD // 2, state_map={'core_lp': True})
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.surplus() == unclaimed_reward['total_bonus'] > 0


def test_multiple_btc_stakes_and_reward_claim(btc_stake, set_candidate, candidate_hub, btc_light_client):
    operators, consensuses = set_candidate
    for i in range(2):
        for index, op in enumerate(operators):
            stake_amount = DELEGATE_VALUE
            if index == 2:
                stake_amount = DELEGATE_VALUE // 2
            delegate_coin_success(op, accounts[i], stake_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 100)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE), set_delegate(accounts[1], DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[1],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE), set_delegate(accounts[1], DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[2],
        "power": [set_delegate(accounts[2], 100)],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE // 2), set_delegate(accounts[1], DELEGATE_VALUE // 2)],
    }], BLOCK_REWARD // 2, state_map={'core_lp': True})
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.surplus() == unclaimed_reward['total_bonus'] > 0


def test_deducted_rewards_added_to_next_round_btc(btc_stake, set_candidate, candidate_hub):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], DELEGATE_VALUE)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], DELEGATE_VALUE)
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, round_reward = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE)],
    }, {
        "address": operators[1],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }], BLOCK_REWARD // 2, state_map={'core_lp': True})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)
    assert STAKE_HUB.surplus() == unclaimed_reward['btc']
    _, unclaimed_reward1, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], DELEGATE_VALUE * 2)]
    }, {
        "address": operators[1],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }
    ], BLOCK_REWARD // 2, state_map={'core_lp': True}, compensation_reward=unclaimed_reward)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.surplus() == unclaimed_reward1['btc']


def test_multiple_users_rewards_deducted(btc_stake, set_candidate, candidate_hub, btc_light_client):
    set_block_time_stamp(MONTH, LOCK_TIME)
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[2], DELEGATE_VALUE)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[0], accounts[1], BTC_VALUE // 4, LOCK_SCRIPT, stake_duration=150)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_rewards, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[2], DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH),
                set_delegate(accounts[1], BTC_VALUE // 4, stake_duration=150)]
    }], BLOCK_REWARD // 2, state_map={'core_lp': True})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    unclaimed_reward = STAKE_HUB.surplus()
    assert tracker.delta() == account_rewards[accounts[0]]
    assert unclaimed_reward == unclaimed_rewards['total_bonus']


def test_btc_stake_without_coin_stake(set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_rewards, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }], BLOCK_REWARD // 2, state_map={'core_lp': 4})
    stake_hub_claim_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.surplus()
    turn_round(consensuses)
    assert unclaimed_reward == unclaimed_rewards['total_bonus']


def __calc_unclaimed_reward(reward, discount):
    unclaimed_reward = reward - (reward * discount // Utils.DENOMINATOR)
    return unclaimed_reward


def test_turn_round_btc_rewards_without_btc_stake(stake_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    delegate_coin_success(operators[1], accounts[2], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    unclaimed_reward = stake_hub.surplus()
    tx = turn_round(consensuses)
    assert 'roundReward' in tx.events
    discount = 1000
    assert __calc_unclaimed_reward(TOTAL_REWARD, discount) == unclaimed_reward


def test_turn_round_core_rewards_without_core_stake(btc_stake, stake_hub, set_candidate, candidate_hub,
                                                    btc_light_client):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    delegate_coin_success(operators[1], accounts[2], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    unclaimed_reward = stake_hub.surplus()
    tx = turn_round(consensuses)
    discount = 1000
    assert 'roundReward' in tx.events
    assert __calc_unclaimed_reward(TOTAL_REWARD, discount) * 2 == unclaimed_reward


@pytest.mark.parametrize("percentage", [400, 1000, 8800, 10000])
def test_btc_lst_discount_by_percentage(btc_stake, set_candidate, btc_agent, percentage):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(percentage)), 64)
    btc_agent.updateParam('lstGradePercentage', hex_value, {'from': accounts[0]})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    btc_reward = TOTAL_REWARD * 3
    actual_reward = TOTAL_REWARD * 3 * percentage // Utils.DENOMINATOR
    bonus = btc_reward - actual_reward
    assert tracker.delta() == actual_reward
    assert STAKE_HUB.surplus() == bonus
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert STAKE_HUB.surplus() == bonus * 2


@pytest.mark.parametrize("percentage", [[12000, 8127], [20000, 40635]])
def test_btc_lst_claim_extra_reward(btc_stake, set_candidate, btc_agent, percentage):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(percentage[0])), 64)
    btc_agent.updateParam('lstGradePercentage', hex_value, {'from': accounts[0]})
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['rewardTo']['amount'] == percentage[1]
    actual_reward = TOTAL_REWARD * 3 * percentage[0] // Utils.DENOMINATOR
    assert tracker.delta() == actual_reward
    assert STAKE_HUB.surplus() == 0
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == actual_reward
    assert STAKE_HUB.surplus() == 0


def test_bonus_exclusive_to_btc_stake(btc_stake, btc_agent, set_candidate, stake_hub):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_lp_rates([[0, 20000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_power_success(operators[0], accounts[0])
    delegate_coin_success(operators[1], accounts[1], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_success(operators[2], accounts[2], 10, LOCK_SCRIPT, stake_duration=YEAR, relay=accounts[2])
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    stake_hub_claim_reward(accounts[:3])
    assert tracker0.delta() == TOTAL_REWARD
    assert tracker1.delta() == TOTAL_REWARD
    assert tracker2.delta() == TOTAL_REWARD * 2
    assert stake_hub.surplus() == 0


def test_no_extra_bonus_for_btc_lst_state(btc_stake, btc_agent, set_candidate, stake_hub):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_lp_rates([[0, 20000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT, percentage=Utils.DENOMINATOR)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[:3])
    assert tracker0.delta() == TOTAL_REWARD * 3
    assert stake_hub.surplus() == 0


def test_btc_staking_reward_depleted(btc_stake, set_candidate, btc_lst_stake, stake_hub):
    stake_manager.set_is_btc_stake_active(True)
    stake_manager.set_tlp_rates([[0, 0]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT, 0)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    turn_round(consensuses)


def test_btc_expired_excluded_from_stake(btc_stake, set_candidate, btc_lst_stake):
    delegate_amount = 10000
    btc_amount = 1
    stake_manager.set_lp_rates([[10000, 5000], [30000, 2000], [40000, 10000], [40001, 3000]])
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    # endRound = 20103
    # current_round = 20100
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    # current_round = 20101
    delegate_btc_success(operators[1], accounts[0], btc_amount, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round(consensuses, round_count=5)
    # current_round = 20106
    # the effective staking duration of BTC is only 1 round, and Coin has 4 rounds, so the acc_stake_amount ratio is 1:40000
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 5


@pytest.mark.parametrize("round", [0, 1, 2, 3])
def test_acc_stake_amount_after_btc_transfer(btc_stake, set_candidate, btc_lst_stake, round):
    delegate_amount = 10000
    btc_amount = 1
    stake_manager.set_lp_rates([[10000, 5000], [30000, 2000], [40000, 10000], [40001, 3000]])
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id = delegate_btc_success(operators[1], accounts[0], btc_amount, LOCK_SCRIPT, stake_duration=YEAR)
    transfer_btc_success(tx_id, operators[2], accounts[0])
    turn_round(consensuses, round_count=round)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    btc_round = 0
    core_round = 0
    if round > 1:
        btc_round = 1
        core_round = round - 1
    btc_reward = TOTAL_REWARD * btc_round // 2
    core_reward = TOTAL_REWARD * core_round
    assert tracker.delta() == core_reward + btc_reward


@pytest.mark.parametrize("stake_amounts", [
    [([0, 1000], [2500, 5000], [10000, 10000], [10001, 3000]), 10000000, 10, 2000],
    [([0, 1000], [2500, 5000], [10000, 10000], [10001, 3000]), 1000000, 1, 200],
    [([0, 1000], [2500, 10000], [5000, 5000], [10001, 3000]), 10000000, 20, 1000]]
                         )
def test_calc_stake_after_coin_unstake(btc_stake, stake_hub, set_candidate, btc_lst_stake, stake_amounts):
    delegate_amount = stake_amounts[1]
    power_value = stake_amounts[2]
    btc_value = stake_amounts[3]
    rates = stake_amounts[0]
    stake_manager.set_lp_rates(rates)
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_power_success(operators[2], accounts[0], power_value)
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round(consensuses)
    undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    power_reward = TOTAL_REWARD // power_value * power_value
    btc_reward = TOTAL_REWARD // 2
    coin_reward = TOTAL_REWARD + TOTAL_REWARD * Utils.CORE_STAKE_DECIMAL // delegate_amount * (
            delegate_amount // 2) // Utils.CORE_STAKE_DECIMAL
    assert tracker.delta() == power_reward + btc_reward + coin_reward


@pytest.mark.parametrize('round_count', [0, 1])
@pytest.mark.parametrize("tests", [
    {'coinAmount': 10000e18, 'btcAmount': 1e8, 'delegateBtc': 100, 'transferBtc': 0, 'duration': 150,
     'expect_reward_pool': 4.5e17,
     'expect_btc_reward': 1.35e18},
    {'coinAmount': 10000e18, 'btcAmount': 1e8, 'transferBtc': 0, 'duration': 360, 'expect_reward_pool': 0,
     'expect_btc_reward': 0},
    {'coinAmount': 12000e18, 'btcAmount': 2e8, 'duration': 30, 'expect_reward_pool': 1.44e18,
     'expect_btc_reward': 3.6e17},
    {'coinAmount': 18000e18, 'btcAmount': 1e8, 'duration': 360, 'expect_reward_pool': 0, 'claim_rewards': 9e17,
     'expect_btc_reward': 2.7e18},
    {'coinAmount': 0, 'btcAmount': 10e8, 'duration': 1, 'expect_reward_pool': 1.764e18,
     'expect_btc_reward': 3.6e16},
])
def test_dual_staking_reward_in_current_round(btc_stake, btc_agent, stake_hub, validator_set, btc_lst_stake,
                                              set_candidate, tests, round_count):
    btc_agent.setAssetWeight(1e10)
    tx_fee = ONE_ETHER
    validator_set.updateBlockReward(ONE_ETHER * 3)
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + tx_fee
    block_reward = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    total_reward = 0
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates([[0, 2000], [5 * Utils.MONTH_TIMESTAMP, 5000], [12 * Utils.MONTH_TIMESTAMP, 10000]])
    stake_manager.set_lp_rates([[0, 1000], [5000, 10000], [10000, 15000]])
    operators, consensuses = set_candidate
    coin_amount = tests['coinAmount']
    if coin_amount > 0:
        delegate_coin_success(operators[1], accounts[0], coin_amount)
        total_reward = block_reward // 2
    tx_id = delegate_btc_success(operators[0], accounts[0], tests['btcAmount'], LOCK_SCRIPT,
                                 stake_duration=tests['duration'])
    turn_round()
    for t in tests:
        value = tests[t]
        if t == 'delegateBtc':
            tx_id = delegate_btc_success(operators[0], accounts[0], value, LOCK_SCRIPT)
        elif t == 'transferBtc':
            transfer_btc_success(tx_id, operators[1], accounts[0])
    turn_round(consensuses, round_count=round_count, tx_fee=tx_fee)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    if round_count == 0:
        assert tracker.delta() == 0
        assert stake_hub.surplus() == 0
        return
    if tests['expect_btc_reward'] == 0:
        assert tracker.delta() == total_reward
        assert stake_hub.surplus() == 0
    else:
        assert tracker.delta() == tests['expect_btc_reward'] + total_reward
        if tests.get('claim_rewards'):
            assert tx.events['rewardTo']['amount'] == tests['claim_rewards']
        assert stake_hub.surplus() == tests['expect_reward_pool']
    turn_round(consensuses, tx_fee=tx_fee)


@pytest.mark.parametrize("tests", [
    {'delegator': ['delegateBtc', 'transferBtc'], 'expect_claim_reward': 1.35e18, 'expect_btc_reward': 6.75e18},
    {'delegator': ['transferBtc', 'delegateBtc'], 'expect_claim_reward': 4.5e17, 'expect_btc_reward': 4.05e18},
])
def test_dual_staking_reward_after_rounds(btc_stake, btc_agent, stake_hub, validator_set, btc_lst_stake,
                                          set_candidate, tests):
    btc_agent.setAssetWeight(1e10)
    tx_fee = ONE_ETHER
    validator_set.updateBlockReward(ONE_ETHER * 3)
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + tx_fee
    block_reward = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates([[0, 5000], [2 * Utils.MONTH_TIMESTAMP, 10000]])
    stake_manager.set_lp_rates([[0, 15000]])
    operators, consensuses = set_candidate
    delegate_coin_success(operators[1], accounts[0], 12000e18)
    tx_id = delegate_btc_success(operators[0], accounts[0], 10e8, LOCK_SCRIPT, stake_duration=YEAR)
    total_reward = block_reward // 2
    turn_round()
    for t in tests['delegator']:
        if t == 'delegateBtc':
            tx_id = delegate_btc_success(operators[0], accounts[0], 1e8, LOCK_SCRIPT)
        elif t == 'transferBtc':
            transfer_btc_success(tx_id, operators[2], accounts[0])
    turn_round(consensuses, round_count=2, tx_fee=tx_fee)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['rewardTo']['amount'] == tests['expect_claim_reward']
    coin_reward = total_reward * 2
    btc_reward = tests['expect_btc_reward']
    assert tracker.delta() == btc_reward + coin_reward
    assert stake_hub.surplus() == 0

    turn_round(consensuses, tx_fee=tx_fee)


def test_dual_staking_claim_success_after_btc_expiration(btc_stake, btc_agent, stake_hub, validator_set, btc_lst_stake,
                                                         set_candidate):
    btc_value = 100
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 5000], [1, 15000], [10001, 1000]])
    operators, consensuses = set_candidate
    set_last_round_tag(3)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses, round_count=5)
    tx = delegate_coin_success(operators[1], accounts[0], 3000000)
    assert tx.events['storedBtcReward'][1]['accStakedAmount'] == btc_value * 3
    assert tx.events['storedBtcReward'][1]['dualStakingRate'] == Utils.DENOMINATOR // 2
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD + TOTAL_REWARD * 3 // 2


@pytest.mark.parametrize("asset_weight", [1, 100, 1000, 1e7, 1e10, 1e18])
def test_claim_reward_after_modify_asset_weight(btc_stake, btc_agent,
                                                set_candidate, core_agent, stake_hub, asset_weight):
    btc_agent.setAssetWeight(asset_weight)
    stake_manager.set_lp_rates([[0, 1000], [10000, 10000], [10001, 1000]])
    delegate_amount = 100 * 10000 * asset_weight
    btc_value = 100
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    turn_round(consensuses)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    rewards = stake_hub.claimReward().return_value
    assert rewards[-1] == TOTAL_REWARD


@pytest.mark.parametrize("tests", [
    {'rate': [[0, 1000], [2500, 10000], [10000, 1000], [10001, 3000]], 'coin': 10000, 'btc': 2,
     'expect_reward': 6772 + 13545},
    {'rate': [[0, 5000], [2500, 10000], [10000, 1000], [10001, 3000]], 'coin': 10000, 'btc': 3,
     'expect_reward': 6772 + 6772},
])
def test_cancel_immediately_after_transfer(btc_stake, stake_hub, set_candidate, btc_lst_stake, tests):
    delegate_amount = tests['coin']
    btc_value = tests['btc']
    rates = tests['rate']
    stake_manager.set_lp_rates(rates)
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount // 2)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests['expect_reward']


@pytest.mark.parametrize("tests", [
    ['delegate', 13545 + 13545 // 2, 13545 * 8],
    ['undelegate', 13545 // 2 + 13545 // 4, 13545 * 2 + 13545 * 2 // 4],
    ['transfer', 13545 + 13545 // 2, 13545 * 4 + 13545 // 2 * 2],
    ['delegate_btc', 13545 + 13545 // 2, 13545 * 2 + 13545 // 4 * 2 * 2],
    ['transfer_btc', 13545, 13545 * 2 + 13545 // 2 * 2],
    ['claim', 13545 + 13545 // 2, 13545 * 2 + 13545 // 2 * 2]
])
def test_dual_staking_without_duration_discount_success(btc_stake, stake_hub, core_agent, set_candidate, btc_lst_stake,
                                                        tests):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    current_round = get_current_round()
    if tests[0] in ['undelegate', 'transfer']:
        run_stake_operation(tests[0], operators[0], accounts[0], delegate_amount // 2, operators[2])
    if tests[0] == 'delegate':
        delegate_coin_success(operators[2], accounts[0], delegate_amount)
    elif tests[0] == 'delegate_btc':
        delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT)
    elif tests[0] == 'transfer_btc':
        transfer_btc_success(tx_id, operators[2], accounts[0])
    elif tests[0] == 'claim':
        tracker0 = get_tracker(accounts[0])
        stake_hub_claim_reward(accounts[0])
        assert tracker0.delta() == TOTAL_REWARD * 4
    assert stake_hub.getDelegatorMap(accounts[0])[0] == current_round
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 4
    if tests[0] == 'claim':
        actual_reward = 0
    assert tracker0.delta() == actual_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == tests[1]
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == tests[2]


def test_staking_with_duration_discount_claim_reward_success(btc_stake, stake_hub, core_agent, set_candidate,
                                                             btc_lst_stake):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates([[0, 5000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    stake_duration = 30
    set_block_time_stamp(stake_duration, LOCK_TIME)
    time_stamp = LOCK_TIME - stake_duration * Utils.ROUND_INTERVAL
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value, block_timestamp=time_stamp)
    turn_round(consensuses, round_count=2)
    tx = delegate_coin_success(operators[2], accounts[0], delegate_amount)
    float_reward = TOTAL_REWARD // 2 - (TOTAL_REWARD - TOTAL_REWARD // 2)
    assert tx.events['storedBtcReward']['unclaimedAmount'] == TOTAL_REWARD - TOTAL_REWARD // 2
    assert tx.events['storedBtcReward']['floatReward'] == float_reward
    assert tx.events['storedBtcReward']['dualStakingRate'] == Utils.DENOMINATOR * 2
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 2 + TOTAL_REWARD // 2 * 2
    assert tracker0.delta() == actual_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD + TOTAL_REWARD // 2 // 2


@pytest.mark.parametrize("tests", [
    ['de', 13545 + 13545 // 2, 13545 * 8],
    ['un', 13545 // 2 + 13545 // 4, 13545 * 2 + 13545 * 2 // 4],
    ['tr', 13545 + 13545 // 2, 13545 * 4 + 13545 // 2 * 2],
    ['deb', 13545 + 13545 // 2, 13545 * 2 + 13545 // 4 * 4],
    ['trb', 13545, 13545 * 2 + 13545 // 2 * 2],
    ['cl', 13545 + 13545 // 2, 13545 * 2 + 13545 // 2 * 2]
])
def test_dual_staking_claim_then_operate_success(btc_stake, stake_hub, core_agent, set_candidate, btc_lst_stake, tests):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 4
    turn_round(consensuses, round_count=2)
    if tests[0] == 'de':
        delegate_coin_success(operators[2], accounts[0], delegate_amount)
    elif tests[0] == 'un':
        undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    elif tests[0] == 'tr':
        transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    elif tests[0] == 'deb':
        delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT)
    elif tests[0] == 'trb':
        transfer_btc_success(tx_id, operators[2], accounts[0])
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 2 + TOTAL_REWARD // 2 * 2
    assert tracker0.delta() == actual_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == tests[1]
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == tests[2]


def test_dual_staking_multiple_rounds_operations_success(btc_stake, stake_hub, core_agent, btc_lst_stake):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators = []
    consensuses = []
    for operator in accounts[5:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 4
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    turn_round(consensuses, round_count=2)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    assert stake_hub.getDelegatorMap(accounts[0]) == [get_current_round(), [TOTAL_REWARD * 3, 0, TOTAL_REWARD // 2 * 2]]
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[3], accounts[0], delegate_amount)
    assert stake_hub.getDelegatorMap(accounts[0]) == [get_current_round(),
                                                      [TOTAL_REWARD * 5, 0, TOTAL_REWARD // 2 * 3]]
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 5 + TOTAL_REWARD // 2 * 3


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'transfer', 'delegate_btc', 'transfer_btc', 'claim'])
def test_dual_staking_uneven_with_transfer_and_cancel_rewards(btc_stake, stake_hub, core_agent, btc_lst_stake, tests):
    stake_manager.set_lp_rates([[0, 1000], [3750, 2500], [3751, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators = []
    consensuses = []
    for operator in accounts[5:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 4 * 3)
    mock_undelegate_coin_success(operators[2], accounts[0], delegate_amount // 4 * 2)
    turn_round(consensuses, round_count=3)
    actual_reward = TOTAL_REWARD // 2 + TOTAL_REWARD * 4 + TOTAL_REWARD // 4 * 2
    event_name = ['storedBtcReward', 'storedCoinReward']
    if tests == 'delegate':
        tx = delegate_coin_success(operators[2], accounts[0], delegate_amount)
    elif tests == 'undelegate':
        tx = undelegate_coin_success(operators[0], accounts[0], delegate_amount // 4)
    elif tests == 'transfer':
        tx = transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 4)
    elif tests == 'delegate_btc':
        tx = delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT, events=True)
    elif tests == 'transfer_btc':
        tx = transfer_btc_success(tx_id, operators[2], accounts[0])
    else:
        tracker = get_tracker(accounts[0])
        tx = stake_hub_claim_reward(accounts[0])
        event_name = ['claimedBtcReward', 'claimedCoinReward']
        assert tracker.delta() == actual_reward
        actual_reward = 0
    assert tx.events[event_name[0]]['dualStakingRate'] == Utils.DENOMINATOR // 4
    assert tx.events[event_name[0]]['accStakedAmount'] == btc_value * 2
    assert tx.events[event_name[1]]['accStakedAmount'] == delegate_amount // 2 * 3
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == actual_reward
    turn_round(consensuses)


def test_calculate_reward_success(btc_stake, stake_hub, core_agent, btc_lst_stake):
    stake_manager.set_lp_rates([[0, 1000], [3750, 2500], [3751, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators = []
    consensuses = []
    for operator in accounts[5:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 4 * 3)
    mock_undelegate_coin_success(operators[2], accounts[0], delegate_amount // 4 * 2)
    turn_round(consensuses, round_count=3)
    actual_reward = TOTAL_REWARD // 2 + TOTAL_REWARD * 4 + TOTAL_REWARD // 4 * 2
    event_name = ['storedBtcReward', 'storedCoinReward']
    tx = stake_hub.calculateReward(accounts[0])
    assert tx.events[event_name[0]]['dualStakingRate'] == Utils.DENOMINATOR // 4
    assert tx.events[event_name[0]]['accStakedAmount'] == btc_value * 2
    assert tx.events[event_name[1]]['accStakedAmount'] == delegate_amount // 2 * 3
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == actual_reward
    turn_round(consensuses)


def test_claim_reward_clears_change_round(btc_stake, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [3750, 2500], [3751, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=3)
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_undelegate_coin_success(operators[0], accounts[0], delegate_amount // 4)
    turn_round(consensuses)
    tx = undelegate_coin_success(operators[0], accounts[0], delegate_amount // 4)
    assert tx.events['storedCoinReward']['accStakedAmount'] == delegate_amount * 2 + (
            delegate_amount - delegate_amount // 4)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 2 + TOTAL_REWARD // 4 * 3
    assert stake_hub.getDelegatorMap(accounts[0])[0] == get_current_round()


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'transfer', 'delegate_btc', 'transfer_btc', 'claim'])
def test_btc_transfer_triggers_dual_staking(btc_stake, stake_hub, core_agent, set_candidate, tests):
    stake_manager.set_lp_rates([[0, 1000], [3750, 2500], [3751, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=2)
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_transfer_btc_success(tx_id, operators[0])
    turn_round(consensuses)
    tx = run_stake_operation(tests, operators[0], accounts[0], delegate_amount, operators[2], tx_id, LOCK_SCRIPT,
                             btc_value=btc_value)
    event_name = 'storedCoinReward'
    if tests == 'claim':
        event_name = 'claimedCoinReward'
        assert tx.events['claimedReward']['amount'] == TOTAL_REWARD * 2
    assert tx.events[event_name]['accStakedAmount'] == delegate_amount * 2
    tracker = get_tracker(accounts[0])
    if tests != 'claim':
        stake_hub_claim_reward(accounts[0])
        assert tracker.delta() == TOTAL_REWARD * 2
    assert stake_hub.getDelegatorMap(accounts[0])[0] == get_current_round()


@pytest.mark.parametrize("round_count", [[0, 0], [1, 1000], [2, 10000], [3, 7500], [4, 10000]])
def test_claim_dual_staking_reward_after_btc_expiration(btc_stake, stake_hub, core_agent, system_reward, set_candidate,
                                                        round_count):
    rate = round_count[1]
    stake_manager.set_lp_rates([[1, 1000], [rate, 10000], [rate + 1, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(3)
    get_current_round()
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=round_count[0])
    get_current_round()
    tx = delegate_coin_success(operators[0], accounts[0], delegate_amount)
    assert tx.events['storedBtcReward']['dualStakingRate'] == Utils.DENOMINATOR
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD
    if round_count[0] in [1, 2]:
        actual_reward += TOTAL_REWARD // 10
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("round_count", [
    [0, 0],
    [1, 0],
    [2, 200],
    [3, 400],
    [4, 600],
    [5, 700],
    [6, 800],
    [7, 900],
    [8, 900],
    [10, 900]
])
def test_multiple_btc_stakes_including_expired(btc_stake, stake_hub, core_agent, system_reward, set_candidate,
                                               round_count):
    stake_manager.set_lp_rates([[0, 10000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(4)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    get_current_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_delegate_btc_success(operators[2], accounts[0], btc_value, lock_time=LOCK_TIME + Utils.ROUND_INTERVAL * 3)
    turn_round(consensuses, round_count=round_count[0])
    get_current_round()
    tx = delegate_coin_success(operators[0], accounts[0], delegate_amount)
    assert tx.events['storedCoinReward']['accStakedAmount'] == delegate_amount * round_count[0]
    assert tx.events['storedBtcReward']['accStakedAmount'] == round_count[1]
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    get_current_round()
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 3
    if round_count[0] == 0:
        actual_reward = TOTAL_REWARD
    if round_count[0] > 3:
        actual_reward = TOTAL_REWARD * 2
    if round_count[0] > 6:
        actual_reward = TOTAL_REWARD
    assert tracker.delta() == actual_reward


def test_btc_expiration_previous_round_operation(btc_stake, stake_hub, core_agent, system_reward, set_candidate):
    stake_manager.set_lp_rates([[2499, 1000], [2500, 10000], [2501, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(4)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=3)
    mock_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    # hardfork
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=3)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedCoinReward']['accStakedAmount'] == delegate_amount
    assert tx.events['claimedBtcReward']['accStakedAmount'] == btc_value * 2
    assert tx.events['claimedBtcReward']['dualStakingRate'] == Utils.DENOMINATOR
    assert tracker.delta() == TOTAL_REWARD // 2 * 2 + TOTAL_REWARD * 2 // 10 + TOTAL_REWARD * 8


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'transfer', 'delegate_btc', 'transfer_btc', 'claim'])
def test_concurrent_stakes_data_settlement_reward(btc_stake, stake_hub, core_agent, system_reward, set_candidate,
                                                  tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(10)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses, round_count=3)
    mock_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    # hardfork
    tx = run_stake_operation(tests, operators[0], accounts[0], delegate_amount // 2, operators[2], tx_id, LOCK_SCRIPT,
                             btc_value=btc_value)
    events_name = ['storedCoinReward', 'storedBtcReward']
    if tests == 'claim':
        events_name = ['claimedCoinReward', 'claimedBtcReward']
    assert tx.events[events_name[0]]['accStakedAmount'] == delegate_amount * 2
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 2


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'transfer', 'delegate_btc', 'transfer_btc', 'claim'])
def test_upgrade_after_intermediate_reward_claim(btc_stake, stake_hub, core_agent, system_reward, set_candidate,
                                                 tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    stake_hub_claim_reward(accounts[0])
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value * 2)
    turn_round(consensuses, round_count=3)
    mock_transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    # hardfork
    tx = run_stake_operation(tests, operators[0], accounts[0], delegate_amount // 2, operators[2], tx_id, LOCK_SCRIPT,
                             btc_value=btc_value)
    events_name = ['storedCoinReward', 'storedBtcReward']
    if tests == 'claim':
        events_name = ['claimedCoinReward', 'claimedBtcReward']
    assert tx.events[events_name[0]][0]['accStakedAmount'] == delegate_amount * 5
    assert tx.events[events_name[1]][0]['accStakedAmount'] == btc_value * 2
    assert tx.events[events_name[1]][1]['accStakedAmount'] == btc_value * 8


def test_concurrent_stakes_with_btc_transfer(btc_stake, stake_hub, core_agent, system_reward, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    mock_transfer_btc_success(tx_id, operators[2])
    turn_round(consensuses, round_count=3)
    tx = delegate_coin_success(operators[1], accounts[0], delegate_amount)
    events_name = ['storedCoinReward', 'storedBtcReward']
    assert tx.events[events_name[0]]['accStakedAmount'] == delegate_amount * 3
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 2


def test_concurrent_stakes_with_expired_btc(btc_stake, stake_hub, core_agent, system_reward, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(3)
    get_current_round()
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    mock_delegate_coin_success(operators[2], accounts[0], delegate_amount)
    mock_delegate_btc_success(operators[2], accounts[0], btc_value, lock_time=LOCK_TIME + Utils.ROUND_INTERVAL * 7)
    turn_round(consensuses)
    turn_round(consensuses, round_count=5)
    tx = delegate_coin_success(operators[1], accounts[0], delegate_amount)
    assert btc_stake.receiptMap(tx_id)['round'] == 0
    events_name = ['storedCoinReward', 'storedBtcReward']
    assert tx.events[events_name[0]]['accStakedAmount'] == delegate_amount * 2 * 5
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 8


@pytest.mark.parametrize("tests", ['delegate', 'delegate_btc'])
def test_settlement_reward_for_staking_other_validators(set_candidate, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses)
    mock_delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=3)
    # hardfork
    tx = run_stake_operation(tests, operators[2], accounts[0], delegate_amount // 2, operators[2], tx_id,
                             LOCK_SCRIPT,
                             btc_value=btc_value)
    events_name = ['storedCoinReward', 'storedBtcReward']
    assert tx.events[events_name[0]]['accStakedAmount'] == delegate_amount * 7
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 7


@pytest.mark.parametrize("tests", ['proxy_delegate', 'proxy_undelegate', 'proxy_transfer', 'proxy_claim'])
def test_proxy_staking_settlement_reward(set_candidate, pledge_agent, stake_hub, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    mock_delegate_coin_success(operators[1], accounts[0], delegate_amount)
    turn_round(consensuses)
    turn_round(consensuses, round_count=3)
    # hardfork
    tx = run_proxy_stake_operation(tests, operators[1], accounts[0], delegate_amount // 2, operators[2], operators)
    change_round = get_current_round()
    events_name = ['storedCoinReward', 'storedBtcReward']
    if tests == 'proxy_claim':
        events_name = ['claimedCoinReward', 'claimedBtcReward']
    assert tx.events[events_name[0]]['accStakedAmount'] == delegate_amount * 8
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 7
    assert stake_hub.getDelegatorMap(accounts[0])[0] == change_round
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(accounts[0])
    acc_stake_amount0 = delegate_amount * 2
    acc_stake_amount1 = delegate_amount * 2
    if tests == 'proxy_undelegate':
        acc_stake_amount0 = delegate_amount * 2 - delegate_amount // 2
        acc_stake_amount1 = acc_stake_amount0
    if tests == 'proxy_delegate':
        acc_stake_amount1 = acc_stake_amount0 + delegate_amount // 2
    assert tx.events['claimedCoinReward'][0]['accStakedAmount'] == acc_stake_amount0
    assert tx.events['claimedBtcReward'][0]['accStakedAmount'] == btc_value * 2
    assert tx.events['claimedCoinReward'][1]['accStakedAmount'] == acc_stake_amount1
    assert tx.events['claimedBtcReward'][1]['accStakedAmount'] == btc_value * 2


@pytest.mark.parametrize("tests", ['delegate', 'delegate_btc', 'transfer_btc', 'claim'])
def test_btc_staking_reward_settlement(set_candidate, pledge_agent, stake_hub, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses)
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=3)
    # hardfork
    tx = run_stake_operation(tests, operators[0], accounts[0], delegate_amount // 2, operators[2], tx_id, LOCK_SCRIPT,
                             btc_value=btc_value)
    change_round = get_current_round()
    events_name = ['storedCoinReward', 'storedBtcReward']
    if tests == 'claim':
        events_name = ['claimedCoinReward', 'claimedBtcReward']
    assert tx.events[events_name[1]]['accStakedAmount'] == btc_value * 9
    assert stake_hub.getDelegatorMap(accounts[0])[0] == change_round
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(accounts[0])
    acc_stake_amount0 = btc_value * 3
    acc_stake_amount1 = btc_value * 3
    if tests == 'delegate_btc':
        acc_stake_amount1 += btc_value
    elif tests == 'transfer_btc':
        acc_stake_amount0 -= btc_value
    assert tx.events['claimedBtcReward'][0]['accStakedAmount'] == acc_stake_amount0
    assert tx.events['claimedBtcReward'][1]['accStakedAmount'] == acc_stake_amount1


def test_coin_staking_reward_settlement(set_candidate, pledge_agent, stake_hub):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=3)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() * TOTAL_REWARD // 2 * 4
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() * TOTAL_REWARD // 2 * 2


def test_btclst_staking_reward_settlement(set_candidate, pledge_agent, stake_hub):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    delegate_btc_lst_success(accounts[0], delegate_amount, BTCLST_LOCK_SCRIPT)
    delegate_btc_lst_success(accounts[1], delegate_amount, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    delegate_btc_lst_success(accounts[0], delegate_amount, BTCLST_LOCK_SCRIPT)
    delegate_btc_lst_success(accounts[1], delegate_amount, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    delegate_btc_lst_success(accounts[0], delegate_amount, BTCLST_LOCK_SCRIPT)
    delegate_btc_lst_success(accounts[1], delegate_amount, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=3)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() * TOTAL_REWARD // 2 * 4
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() * TOTAL_REWARD // 2 * 2


def test_unified_reward_settlement_for_different_validators(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_delegate_coin_success(operators[1], accounts[1], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    mock_delegate_btc_success(operators[1], accounts[1], btc_value)
    turn_round(consensuses)
    turn_round(consensuses, round_count=1)
    tx = delegate_coin_success(operators[2], accounts[0], delegate_amount)
    assert stake_hub.getDelegatorMap(accounts[0])[0] == get_current_round()
    assert tx.events['storedCoinReward']['accStakedAmount'] == delegate_amount * 2
    assert tx.events['storedBtcReward']['accStakedAmount'] == btc_value


@pytest.mark.parametrize("tests", ['proxy_delegate', 'proxy_undelegate', 'proxy_transfer'])
def test_reward_settlement_after_data_migration(stake_hub, set_candidate, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [1, 10000]])
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100000
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_ids = []
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    tx_ids.append(tx_id0)
    tx_ids.append(tx_id1)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    turn_round(consensuses, round_count=3)
    tx = run_proxy_stake_operation(tests, operators[0], accounts[0], delegate_amount // 2, operators[2], operators)
    assert tx.events['claimedReward']['amount'] == TOTAL_REWARD // 2 * 2 - 1
    tracker = get_tracker(accounts[0])
    assert sum(stake_hub.getDelegatorMap(accounts[0])[1]) == TOTAL_REWARD // 2 * 3
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2 * 3
    turn_round(consensuses)


@pytest.mark.parametrize("tests", [
    'proxy_delegate', 'proxy_undelegate', 'proxy_transfer']
                         )
def test_check_acc_stake_amount_after_data_migration(stake_hub, btc_stake, core_agent, set_candidate, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [1, 10000]])
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100000
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_ids = []
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    tx_ids.append(tx_id0)
    tx_ids.append(tx_id1)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    turn_round(consensuses, round_count=3)
    tx = run_proxy_stake_operation(tests, operators[0], accounts[0], delegate_amount // 2, operators[2], operators)
    assert btc_stake.receiptMap(tx_id0)['round'] == get_current_round() - 1
    assert core_agent.getDelegator(operators[0], accounts[0])['changeRound'] == get_current_round()
    assert tx.events['storedCoinReward']['accStakedAmount'] == delegate_amount * 3
    assert tx.events['storedBtcReward']['accStakedAmount'] == btc_value * 3
    turn_round(consensuses, round_count=2)


@pytest.mark.parametrize("tests", [
    ['proxy_delegate', 500000, 750000, 5000, 7500],
    ['proxy_undelegate', 250000, 250000, 2500, 2500],
    ['proxy_transfer', 500000, 500000, 5000, 5000]
])
def test_delegate_current_round_calculation(stake_hub, set_candidate, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_ids = []
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    tx_ids.append(tx_id0)
    tx_ids.append(tx_id1)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    lp_list = [[tests[3] - 1, 1000], [tests[3], 20000], [tests[3] + 1, 1000], [tests[4] - 1, 1000], [tests[4], 40000],
               [tests[4] + 1, 1000]]
    stake_manager.set_lp_rates(lp_list)
    turn_round(consensuses)
    run_proxy_stake_operation(tests[0], operators[0], accounts[0], delegate_amount // 2, operators[2], operators)
    turn_round(consensuses, round_count=2)
    tx = old_claim_reward_success(operators, accounts[0])
    expect_event(tx, 'claimedCoinReward', {
        'accStakedAmount': tests[1]
    })
    expect_event(tx, 'claimedCoinReward', {
        'accStakedAmount': tests[2]
    }, idx=1)
    dualStakingRate = Utils.DENOMINATOR * 2
    if tests[3] == tests[4]:
        dualStakingRate = Utils.DENOMINATOR * 4
    expect_event(tx, 'claimedBtcReward', {
        'accStakedAmount': btc_value,
        'dualStakingRate': dualStakingRate
    })
    expect_event(tx, 'claimedBtcReward', {
        'accStakedAmount': btc_value,
        'dualStakingRate': Utils.DENOMINATOR * 4
    }, idx=1)


def test_btc_transfer_sets_acc_to_zero(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_ids = []
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_ids.append(tx_id0)
    tx_ids.append(tx_id1)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    turn_round(consensuses, round_count=2)
    transfer_btc_success(tx_id0, operators[1], accounts[0])
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(accounts[0])
    expect_event(tx, 'claimedBtcReward', {
        'accStakedAmount': btc_value
    })
    expect_event(tx, 'claimedBtcReward', {
        'accStakedAmount': btc_value * 2
    }, idx=1)
    expect_event(tx, 'claimedRewardPerTx', {
        'txid': tx_id0,
        'accStakedAmount': 0
    }, idx=1)


def test_dual_staking_after_expired_btc(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    set_last_round_tag(3)
    delegate_amount = 500000
    btc_value = 100
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=6)
    tx = stake_hub_claim_reward(accounts[0])
    expect_event(tx, 'claimedCoinReward', {
        'accStakedAmount': delegate_amount * 5
    }, idx=1)
    expect_event(tx, 'claimedBtcReward', {
        'accStakedAmount': btc_value * 3
    }, idx=1)


def test_check_acc_stake_amount_after_expired_btc_stake(stake_hub, btc_stake, core_agent, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [1, 10000]])
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100000
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_ids = []
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 4)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0], LOCK_TIME)
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1], LOCK_TIME)
    tx_ids.append(tx_id0)
    tx_ids.append(tx_id1)
    old_turn_round(consensuses, round_count=6)
    __init_hybrid_score_mock()
    __move_btc_data(tx_ids)
    turn_round(consensuses, round_count=3)
    tx = old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    assert tx.events['storedCoinReward']['accStakedAmount'] == delegate_amount * 3
    assert tx.events['storedBtcReward']['accStakedAmount'] == 0
    turn_round(consensuses, round_count=2)


def test_stake_btc_then_move_data(stake_hub, btc_stake, core_agent, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [1, 10000]])
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100000
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    old_turn_round(consensuses, round_count=6)
    __init_hybrid_score_mock()
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    tx = delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT, events=True)
    assert tx.events['storedCoinReward']['accStakedAmount'] == 0
    assert tx.events['storedBtcReward']['accStakedAmount'] == btc_value
    turn_round(consensuses, round_count=2)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses, round_count=2)
    tx = delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT, events=True)
    assert tx.events['storedCoinReward'][0]['accStakedAmount'] == delegate_amount
    assert tx.events['storedBtcReward'][0]['accStakedAmount'] == btc_value * 2
    assert tx.events['storedCoinReward'][1]['accStakedAmount'] == delegate_amount
    assert tx.events['storedBtcReward'][1]['accStakedAmount'] == btc_value * 2


def test_reward_with_duration_discount_on_current_round(stake_hub, btc_stake, core_agent, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_lp_rates([[0, 5000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses)
    btc_stake_duration = 30
    mock_delegate_btc_success(operators[0], accounts[0], btc_value,
                              block_timestamp=LOCK_TIME - btc_stake_duration * Utils.ROUND_INTERVAL)
    turn_round(consensuses, round_count=2)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    stake_manager.set_tlp_rates([[0, 5000]])
    turn_round(consensuses, round_count=2)
    tx = delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT, events=True)
    btc_reward = TOTAL_REWARD * 2 // 5
    assert tx.events['storedBtcReward']['unclaimedAmount'] == btc_reward // 2
    assert tx.events['storedBtcReward']['floatReward'] == -(btc_reward // 2 // 2) - btc_reward // 2


def test_unmigrated_stake_coin(stake_hub, btc_stake, core_agent, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [1, 10000]])
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_turn_round(consensuses)
    __init_hybrid_score_mock()
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    tx = delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT, events=True)
    assert tx.events['storedCoinReward']['accStakedAmount'] == 0
    assert tx.events['storedBtcReward']['accStakedAmount'] == btc_value
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    btc_reward = TOTAL_REWARD * 2 // 5
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == btc_reward // 10 + TOTAL_REWARD * 2 + TOTAL_REWARD - btc_reward
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedCoinReward'][0]['accStakedAmount'] == delegate_amount
    assert tx.events['claimedBtcReward'][0]['accStakedAmount'] == btc_value
    assert tx.events['claimedCoinReward'][1]['accStakedAmount'] == delegate_amount * 2
    assert tx.events['claimedBtcReward'][1]['accStakedAmount'] == btc_value * 2


@pytest.mark.parametrize("tests", [
    ['delegate', 'transfer', 4063 + 5416 * 2 // 3 // 2],
    ['transfer', 'undelegate', 4063 // 2 + 5416 * 2 // 3 // 10],
    ['undelegate', 'delegate', 4063 // 2 + 5416 * 2 // 3 // 10],
    ['delegate_btc', 'transfer_btc', 4063 + 0],
    ['transfer', 'undelegate', 'transfer_btc', 4063 // 2 + 0],
])
def test_reconcile_diff_operations_in_current_round(stake_hub, btc_stake, core_agent, set_candidate, tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 1000], [2500, 5000], [2501, 10000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    for account in accounts[:2]:
        mock_delegate_coin_success(operators[0], account, delegate_amount)
    turn_round(consensuses)
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value * 2)
    mock_delegate_btc_success(operators[0], accounts[1], btc_value)
    turn_round(consensuses, round_count=3)
    for test in tests:
        run_stake_operation(test, operators[0], accounts[0], delegate_amount // 2, operators[2], tx_id,
                            LOCK_SCRIPT,
                            btc_value=btc_value)
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests[-1]
    turn_round(consensuses)


@pytest.mark.parametrize("tests", [
    {'validator_state': 'minor', 'coin_acc_amount': 500000 * 3, 'btc_acc_amount': 400,
     'account_reward': [6772 + 13545 * 6 // 10, (5418 - 1) * 2 // 3 * 2],
     'coin_acc_amount1': 500000 * 2,
     'btc_acc_amount1': 200 * 2,
     'account_reward1': [13545 * 6 // 10 // 2 * 2, 5417 * 2 // 3 * 2]
     },
    {'validator_state': 'major', 'coin_acc_amount': 500000 * 3, 'btc_acc_amount': 400,
     'coin_acc_amount1': 500000 * 2,
     'btc_acc_amount1': 200 * 2,
     'account_reward': [6772, 0],
     'account_reward1': [13545 * 6 // 10 // 2, (5418 - 1) * 2 // 3]
     }
])
def test_operations_on_different_validator_states(stake_hub, btc_stake, candidate_hub, slash_indicator, core_agent,
                                                  set_candidate,
                                                  tests):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 10000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[0], accounts[0], btc_value * 2)
    mock_delegate_btc_success(operators[0], accounts[1], btc_value)
    turn_round(consensuses)
    tx0 = None
    if tests['validator_state'] == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    turn_round(consensuses, round_count=2)
    tx = delegate_coin_success(operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount)
    assert tx.events['storedCoinReward']['accStakedAmount'] == tests['coin_acc_amount']
    assert tx.events['storedBtcReward']['accStakedAmount'] == tests['btc_acc_amount']
    assert tx.events['storedCoinReward']['amount'] == tests['account_reward'][0]
    assert tx.events['storedBtcReward']['amount'] == tests['account_reward'][1]
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == sum(tests['account_reward'])
    required_margin = candidate_hub.requiredMargin()
    candidate_hub.addMargin({'value': required_margin, 'from': operators[0]})
    turn_round(consensuses, round_count=2)
    tx = delegate_coin_success(operators[2], accounts[0], delegate_amount)
    assert tx.events['storedCoinReward'][0]['accStakedAmount'] == tests['coin_acc_amount1'] // 2
    assert tx.events['storedBtcReward'][0]['accStakedAmount'] == tests['btc_acc_amount1'] // 2
    assert tx.events['storedCoinReward'][1]['accStakedAmount'] == tests['coin_acc_amount1'] // 2
    assert tx.events['storedBtcReward'][1]['accStakedAmount'] == tests['btc_acc_amount1'] // 2
    tracker.update_height()
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == sum(tests['account_reward1'])


@pytest.mark.parametrize("round_reward",
                         [[0, 13544], [1, 27090],
                          [2, (13545 + 6772 * 2 + 8127) + 5417 * 2 // 3 * 2],
                          [3, (13545 + 6772 * 2 + 8127) + (
                                  5417 * 2 // 3 * 2) + 13545 * 6 // 10 // 2 * 2 + 5418 * 2 // 3 * 2]])
def test_claim_reward_across_different_changeRound(stake_hub, set_candidate, round_reward):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 10000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_coin_success(op, account, delegate_amount)
    turn_round(consensuses, round_count=2)
    for index, account in enumerate(accounts[:2]):
        for op in operators[:2]:
            delegate_btc_value = btc_value
            if index == 0:
                delegate_btc_value = btc_value * 2
            mock_delegate_btc_success(op, account, delegate_btc_value)
    turn_round(consensuses, round_count=round_reward[0])
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == round_reward[1]
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    account_reward = COIN_REWARD_NO_POWER // 2 * 2 + (BTC_REWARD_NO_POWER - 1) * 4 // 6 * 2
    if round_reward[0] == 0:
        account_reward = TOTAL_REWARD // 2 * 2
    assert tracker.delta() == account_reward


def test_change_round_diff_with_power_stake(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 10000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_coin_success(op, account, delegate_amount)
    turn_round(consensuses, round_count=2)
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_btc_success(op, account, btc_value)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount)
    trackers = get_trackers(accounts[:3])
    stake_hub_claim_reward(accounts[:3])
    account_reward = TOTAL_REWARD * 2 + TOTAL_REWARD // 2 + (TOTAL_REWARD // 6 * 2)
    assert trackers[0].delta() == account_reward
    assert trackers[1].delta() == account_reward
    assert trackers[2].delta() == TOTAL_REWARD // 6 * 2
    stake_manager.set_lp_rates([[1, 1000], [5000, 10000], [5001, 1000]])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    account_reward = TOTAL_REWARD // 2 + (TOTAL_REWARD // 6 * 2)
    assert trackers[0].delta() == account_reward


def test_change_round_diff_with_btcLst_stake(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 10000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    btc_lst_value = 1000
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_coin_success(op, account, delegate_amount)
    turn_round(consensuses, round_count=2)
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_btc_success(op, account, btc_value)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    trackers = get_trackers(accounts[:3])
    account_reward = TOTAL_REWARD * 2 + TOTAL_REWARD // 2 + (TOTAL_REWARD // 6 * 2)
    turn_round(consensuses)
    account_reward += TOTAL_REWARD // 2 + (TOTAL_REWARD // 6 * 2)
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedBtcReward']['accStakedAmount'] == btc_value * 2 * 3
    assert tx.events['claimedCoinReward']['accStakedAmount'] == delegate_amount * 2 * 5
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], delegate_amount), set_delegate(accounts[0], delegate_amount)],
        "btc": [set_delegate(accounts[1], btc_value), set_delegate(accounts[0], btc_value)]
    }, {
        "address": operators[1],
        "coin": [set_delegate(accounts[1], delegate_amount), set_delegate(accounts[0], delegate_amount)],
        "btc": [set_delegate(accounts[1], btc_value), set_delegate(accounts[0], btc_value)]
    }, {
        "address": operators[2]
    }
    ], TOTAL_REWARD, {accounts[0]: set_btc_lst_delegate(btc_lst_value)})
    assert trackers[0].delta() == account_rewards[accounts[0]] + account_reward
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedBtcReward']['accStakedAmount'] == btc_value * 2
    assert tx.events['claimedCoinReward']['accStakedAmount'] == delegate_amount * 2


def test_change_round_same_add_btcLst_stake(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    btc_lst_value = 1000
    for account in accounts[:2]:
        delegate_coin_success(operators[0], account, delegate_amount)
    turn_round(consensuses, round_count=2)
    tx = delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    assert stake_hub.getDelegatorMap(accounts[0])[1][0] == TOTAL_REWARD // 2
    delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_power_success(operators[0], accounts[2])
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)

    turn_round(consensuses)
    stake_manager.set_lp_rates([[4999, 1000], [5000, 10000], [5001, 1000]])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], delegate_amount), set_delegate(accounts[0], delegate_amount)],
        "power": [set_delegate(accounts[2], 1)],
        "btc": [set_delegate(accounts[1], btc_value), set_delegate(accounts[0], btc_value)]
    }, {
        "address": operators[1],
    }, {
        "address": operators[2]
    }
    ], TOTAL_REWARD, {accounts[0]: set_btc_lst_delegate(btc_lst_value)})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]] + TOTAL_REWARD // 2 * 2


def test_all_stakes_operation_and_reward_claim(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    for account in accounts[:2]:
        for op in operators[:2]:
            delegate_coin_success(op, account, delegate_amount)
    turn_round(consensuses, round_count=3)
    for account in accounts[:2]:
        for op in operators[:2]:
            delegate_btc_success(op, account, btc_value, LOCK_SCRIPT)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 2
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    stake_manager.set_lp_rates([[4999, 1000], [5000, 10000], [5001, 1000]])
    turn_round(consensuses, round_count=2)
    get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedCoinReward'][0]['accStakedAmount'] == delegate_amount * 2
    assert tx.events['claimedCoinReward'][1]['accStakedAmount'] == delegate_amount * 2
    assert tx.events['claimedBtcReward'][0]['accStakedAmount'] == 0
    assert tx.events['claimedBtcReward'][1]['accStakedAmount'] == btc_value * 2


def test_validator_power_reward_on_upgrade(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_coin_success(op, account, delegate_amount)
    turn_round(consensuses, round_count=3)
    for account in accounts[:2]:
        for op in operators[:2]:
            mock_delegate_btc_success(op, account, btc_value)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_power_success(operators[0], accounts[2])
    delegate_power_success(operators[1], accounts[2])
    turn_round(consensuses)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    tracker = get_tracker(accounts[2])
    stake_hub_claim_reward(accounts[2])
    assert tracker.delta() == TOTAL_REWARD // 6 * 2


def test_claim_reward_after_current_round_operation(stake_hub, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=3)
    stake_manager.set_lp_rates([[2500, 20000], [4999, 1000], [5000, 10000], [7500, 20000]])
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=2)
    tx = undelegate_coin_success(operators[0], accounts[0], delegate_amount)
    assert tx.events['storedBtcReward'][0]['accStakedAmount'] == btc_value
    assert tx.events['storedCoinReward'][0]['accStakedAmount'] == delegate_amount
    assert tx.events['storedBtcReward'][1]['accStakedAmount'] == btc_value * 2
    assert tx.events['storedBtcReward'][1]['dualStakingRate'] == Utils.DENOMINATOR * 2
    assert tx.events['storedCoinReward'][1]['accStakedAmount'] == delegate_amount
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    btc_reward = BTC_REWARD_NO_POWER - 1
    coin_reward = COIN_REWARD_NO_POWER - 1
    assert tracker.delta() == (COIN_REWARD_NO_POWER + coin_reward) + btc_reward + btc_reward * 2


@pytest.mark.parametrize("claim", [True, False])
def test_proxy_claim_reward_after_current_round_operation(stake_hub, set_candidate, claim):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    old_claim_reward_success(operators, accounts[0])
    if claim:
        old_claim_reward_success(operators, accounts[0])
    else:
        stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_manager.set_lp_rates([[4999, 1000], [5000, 20000], [5001, 1000]])
    if claim:
        tx = old_claim_reward_success(operators, accounts[0])
    else:
        tx = stake_hub_claim_reward(accounts[0])
    event_name = ['claimedCoinReward', 'claimedBtcReward']
    expect_event(tx, event_name[0], {
        'amount': TOTAL_REWARD,
        'accStakedAmount': delegate_amount
    })
    expect_event(tx, event_name[1], {
        'amount': 0,
        'accStakedAmount': 0
    })
    expect_event(tx, event_name[0], {
        'amount': COIN_REWARD_NO_POWER,
        'accStakedAmount': delegate_amount
    }, idx=1)
    expect_event(tx, event_name[1], {
        'amount': (BTC_REWARD_NO_POWER - 1) * 2,
        'accStakedAmount': btc_value,
        'dualStakingRate': Utils.DENOMINATOR * 2,
    }, idx=1)

    assert tracker.delta() == TOTAL_REWARD + COIN_REWARD_NO_POWER + (BTC_REWARD_NO_POWER - 1) * 2


def test_claim_reward_after_refund_surplus(stake_hub, system_reward, set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 20000]])
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT)
    surplus = 50000
    accounts[3].transfer(stake_hub.address, surplus)
    stake_hub.setSurplus(surplus)
    assert stake_hub.balance() == surplus
    system_reward_tracker = get_tracker(system_reward)
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(surplus), 64)
    stake_hub.updateParam('surplus', hex_value)
    assert system_reward_tracker.delta() == surplus
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    system_reward_tracker.update_height()
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['rewardTo']['amount'] == TOTAL_REWARD
    assert system_reward_tracker.delta() == -TOTAL_REWARD
    assert stake_hub.balance() == 0
    assert tracker.delta() == TOTAL_REWARD * 3


def test_calculateReward_success(btc_stake, stake_hub, core_agent, set_candidate,
                                 btc_lst_stake, ):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [5001, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    current_round = get_current_round()
    stake_hub.calculateReward(accounts[0])
    assert stake_hub.getDelegatorMap(accounts[0])[0] == current_round
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 4
    assert tracker0.delta() == actual_reward
    turn_round(consensuses)
    stake_hub.calculateReward(accounts[0])
    stake_manager.set_lp_rates([[0, 20000]])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD + TOTAL_REWARD // 2


def test_calculateReward_repeated(btc_stake, stake_hub, core_agent, set_candidate,
                                  btc_lst_stake, ):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [5001, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    mock_delegate_btc_success(operators[1], accounts[0], btc_value)
    turn_round(consensuses, round_count=2)
    current_round = get_current_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    stake_hub.calculateReward(accounts[0])
    stake_hub.calculateReward(accounts[0])
    assert stake_hub.getDelegatorMap(accounts[0])[0] == current_round
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 4
    stake_hub.calculateReward(accounts[0])
    assert tracker0.delta() == actual_reward
    turn_round(consensuses)
    stake_hub.calculateReward(accounts[0])
    stake_hub.calculateReward(accounts[0])
    stake_manager.set_lp_rates([[0, 20000]])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD + TOTAL_REWARD // 2


def test_calculateReward_with_latest_stake(btc_stake, stake_hub, core_agent, set_candidate,
                                           btc_lst_stake, ):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [5001, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tx = stake_hub.calculateReward(accounts[0], {'from': accounts[1]})
    assert tx.events['storedCoinReward'][0]['accStakedAmount'] == delegate_amount
    assert tx.events['storedCoinReward'][1]['accStakedAmount'] == delegate_amount
    assert tx.events['storedBtcReward'][0]['accStakedAmount'] == 0
    assert tx.events['storedBtcReward'][1]['accStakedAmount'] == btc_value
    assert tx.events['storedBtcReward'][1]['dualStakingRate'] == Utils.DENOMINATOR // 2
    assert tx.events['storedBtcReward'][0]['delegator'] == accounts[0]
    assert tx.events['storedBtcReward'][1]['delegator'] == accounts[0]
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 2 + TOTAL_REWARD // 2


@pytest.mark.parametrize("onStakeChange", [True, False])
def test_calculateReward_after_current_round_claim(btc_stake, stake_hub, core_agent, set_candidate,
                                                   btc_lst_stake, onStakeChange):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [5000, 5000], [10000, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 2 + TOTAL_REWARD // 2
    if onStakeChange:
        stake_hub.onStakeChange(accounts[0], {'from': accounts[1]})
    else:
        stake_hub.calculateReward(accounts[0], {'from': accounts[1]})
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    turn_round(consensuses)
    if onStakeChange:
        stake_hub.onStakeChange(accounts[0], {'from': accounts[1]})
    else:
        stake_hub.calculateReward(accounts[0], {'from': accounts[1]})
    assert stake_hub.getDelegatorMap(accounts[0])[1] == [TOTAL_REWARD, 0, TOTAL_REWARD // 2]
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD + TOTAL_REWARD // 2


@pytest.mark.parametrize("round_count",
                         [[2, 13545 // 2 * 2, 1693], [3, 13545 + 6772, 6772 // 2], [4, 13545 * 2 - 1, 6772]])
def test_calculateReward_with_expired_btc(btc_stake, stake_hub, core_agent, set_candidate,
                                          btc_lst_stake, round_count):
    stake_manager.set_lp_rates([[0, 1000], [2500, 2500], [7500, 5000], [7501, 20000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    set_last_round_tag(3)
    turn_round()
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[1], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=round_count[0])
    tracker0 = get_tracker(accounts[0])
    stake_hub_calculate_reward(accounts[0])
    rewards = [round_count[1], 0,
               round_count[2]]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == sum(rewards)


@pytest.mark.parametrize("percentage", [True, False])
def test_calculateReward_after_percentage_update(btc_stake, btc_agent, stake_hub, core_agent, set_candidate,
                                                 percentage):
    stake_manager.set_lp_rates([[0, 10000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    get_current_round()
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[1], btc_value, LOCK_SCRIPT)
    turn_round(consensuses, round_count=4)
    tracker0 = get_tracker(accounts[0])
    rewards = [TOTAL_REWARD * 2 - 1, 0, TOTAL_REWARD + TOTAL_REWARD // 2]
    if percentage:
        stake_hub_calculate_reward(accounts[0])
    grades = [[0, 1000], [5000, 5000], [5001, 30000]]
    grades_encode = rlp.encode(grades)
    execute_proposal(
        btc_agent.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['grades', grades_encode]),
        "update grades"
    )
    if percentage is False:
        stake_hub_calculate_reward(accounts[0])
        rewards = [TOTAL_REWARD * 2 - 1, 0, (TOTAL_REWARD + TOTAL_REWARD // 2) // 2]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == sum(rewards)


@pytest.mark.parametrize("onStakeChange", [True, False])
def test_calculateReward_with_all_stakes(btc_stake, btc_agent, stake_hub, core_agent, set_candidate, onStakeChange):
    stake_manager.set_lp_rates([[0, 10000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    btc_lst_value = 1000
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_power_success(operators[0], accounts[2])
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "power": [set_delegate(accounts[2], 1)],
        "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)]
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], BLOCK_REWARD // 2, {accounts[0]: set_btc_lst_delegate(btc_lst_value)})
    stake_hub_calculate_reward(accounts[0])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


def test_calculateReward_with_core_only(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 10000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=2)
    trackers = get_trackers(accounts[:2])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[:2])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == TOTAL_REWARD + TOTAL_REWARD // 2
    assert trackers[1].delta() == TOTAL_REWARD // 2
    stake_hub_calculate_reward(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == 0
    assert trackers[1].delta() == 0


def test_calculateReward_with_btc_only(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 10000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round()
    delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=2)
    trackers = get_trackers(accounts[:2])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[:2])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == (TOTAL_REWARD - 1) + (COIN_REWARD_NO_POWER // 2 + (BTC_REWARD_NO_POWER - 1) // 2)
    assert trackers[1].delta() == TOTAL_REWARD // 2 - 1
    stake_hub_calculate_reward(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == 0
    assert trackers[1].delta() == 0


def test_calculateReward_after_operation(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[2499, 1000], [2500, 10000], [4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    tx_id = delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=2)
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)
    undelegate_coin_success(operators[1], accounts[0], delegate_amount // 2)
    transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount // 2)
    transfer_btc_success(tx_id, operators[1], accounts[1])
    trackers = get_trackers(accounts[:2])
    stake_hub_claim_reward(accounts[1])
    assert trackers[0].delta() == 0
    assert trackers[1].delta() == TOTAL_REWARD // 2 - 1
    turn_round(consensuses)
    stake_hub_calculate_reward(accounts[0])
    stake_hub_calculate_reward(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == COIN_REWARD_NO_POWER // 2 + COIN_REWARD_NO_POWER // 4 + (
            BTC_REWARD_NO_POWER - 1) // 2 * 2
    assert trackers[1].delta() == COIN_REWARD_NO_POWER // 2


def test_calculateReward_without_data_migration(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 10000], [1, 1000], [2500, 1000], [4999, 1000], [5000, 1000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses, round_count=2)
    tx = __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    turn_round(consensuses, round_count=2)
    # delegate_coin_success(operators[0], accounts[0], delegate_amount)
    stake_hub_calculate_reward(accounts[0])
    stake_hub_calculate_reward(accounts[1])
    btc_reward = TOTAL_REWARD // 4 + (BTC_REWARD_NO_POWER - 1) // 2
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': [0, 0, btc_reward]})
    __check_stake_hub_delegator_map(accounts[1], {'changeRound': get_current_round(),
                                                  'rewards': [0, 0, btc_reward]})
    trackers = get_trackers(accounts[:2])
    assert trackers[0].delta() == 0
    assert trackers[1].delta() == 0
    turn_round(consensuses)


def test_calculateReward_after_data_migration(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [2500, 1000], [4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses, round_count=2)
    stake_hub_calculate_reward(accounts[0])
    coin_reward = COIN_REWARD_NO_POWER // 2 + TOTAL_REWARD // 2 // 2
    btc_reward = TOTAL_REWARD // 4 + (BTC_REWARD_NO_POWER - 1) // 2
    rewards = [coin_reward, 0, btc_reward]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == sum(rewards)
    turn_round(consensuses)


def test_calculateReward_after_operation_before_upgrade(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)
    undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    turn_round(consensuses)
    stake_hub_calculate_reward(accounts[0])
    coin_reward = COIN_REWARD_NO_POWER // 4
    btc_reward = (BTC_REWARD_NO_POWER - 1) // 2
    rewards = [coin_reward + TOTAL_REWARD // 4, 0, btc_reward + TOTAL_REWARD // 4]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == sum(rewards)
    turn_round(consensuses)


def test_calculateReward_after_claim(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=2)
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)
    stake_hub_claim_reward(accounts[0])
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [4999, 1000], [5001, 1000]])
    undelegate_coin_success(operators[1], accounts[0], delegate_amount // 2)
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [2501, 1000]])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_calculate_reward(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == COIN_REWARD_NO_POWER // 4 + (BTC_REWARD_NO_POWER - 1) // 2


@pytest.mark.parametrize("calculate", [True, False])
def test_calculateReward_with_no_operation_on_expired_btc(btc_stake, btc_agent, stake_hub, core_agent, set_candidate,
                                                          calculate):
    stake_manager.set_lp_rates([[0, 1000], [10000, 5000], [10001, 8000], [12500, 10000], [12511, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(3)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    mock_delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_TIME)
    turn_round(consensuses, round_count=4)
    actual_reward = TOTAL_REWARD * 5 + TOTAL_REWARD * 2
    dual_staking_rate = Utils.DENOMINATOR
    if calculate:
        tx = stake_hub_calculate_reward(accounts[0], accounts[3])
        actual_reward = TOTAL_REWARD * 5 + TOTAL_REWARD * 2 // 2
        rate = Utils.DENOMINATOR // 2
        assert tx.events['storedBtcReward']['dualStakingRate'] == rate

    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tx.events['claimedBtcReward']['dualStakingRate'] == dual_staking_rate
    assert tracker.delta() == actual_reward


def test_delete_data_for_expired_btc_in_operation_round(btc_stake, btc_agent, stake_hub, core_agent, set_candidate, ):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    set_last_round_tag(3)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round(consensuses)
    tx_id = mock_delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_TIME)
    turn_round(consensuses, round_count=4)
    stake_hub_calculate_reward(accounts[0], accounts[3])
    assert btc_stake.receiptMap(tx_id)['round'] == 0


def test_calculateReward_generates_rewards(btc_stake, btc_agent, stake_hub, core_agent, set_candidate, ):
    stake_manager.set_is_stake_hub_active()
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_amount = 1000
    set_last_round_tag(3)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_power_success(operators[1], accounts[0])
    mock_delegate_btc_success(operators[2], accounts[0], btc_amount)
    delegator_map = stake_hub.getDelegatorMap(accounts[0])
    assert delegator_map == [0, []]
    stake_hub_calculate_reward(accounts[0], accounts[3])
    delegator_map = stake_hub.getDelegatorMap(accounts[0])
    assert delegator_map == [get_current_round(), [0, 0, 0]]
    turn_round(consensuses, round_count=2)
    stake_hub_calculate_reward(accounts[0], accounts[3])
    delegator_map = stake_hub.getDelegatorMap(accounts[0])
    assert delegator_map == [get_current_round(), [TOTAL_REWARD, TOTAL_REWARD, TOTAL_REWARD]]


def test_help_call_calculateReward(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses, round_count=2)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[1])
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)
    transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount // 2)
    undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    undelegate_coin_success(operators[0], accounts[1], delegate_amount // 2)
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [2501, 1000]])

    turn_round(consensuses)
    stake_hub_calculate_reward(accounts[0], accounts[1])
    stake_hub_calculate_reward(accounts[1], accounts[2])
    coin_reward = COIN_REWARD_NO_POWER // 4
    btc_reward = (BTC_REWARD_NO_POWER - 1) // 2
    rewards = [coin_reward + TOTAL_REWARD // 4, 0, btc_reward + TOTAL_REWARD // 4]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_trackers(accounts[:3])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    stake_hub_claim_reward(accounts[2])
    assert trackers[0].delta() == sum(rewards)
    assert trackers[1].delta() == sum(rewards)
    assert trackers[2].delta() == 0
    turn_round(consensuses)


def test_calculateReward_after_current_round_operation(btc_stake, btc_agent, stake_hub, core_agent, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_btc_success(operators[0], accounts[1], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round(consensuses, round_count=2)
    stake_hub_calculate_reward(accounts[0])
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_amount // 2)
    transfer_coin_success(operators[0], operators[1], accounts[1], delegate_amount // 2)
    undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    undelegate_coin_success(operators[0], accounts[1], delegate_amount // 2)
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [2501, 1000]])
    turn_round(consensuses)
    stake_hub_calculate_reward(accounts[0], accounts[2])
    coin_reward = COIN_REWARD_NO_POWER // 4 + COIN_REWARD_NO_POWER // 2
    btc_reward = (BTC_REWARD_NO_POWER - 1) // 2 * 2
    rewards = [coin_reward, 0, btc_reward]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_trackers(accounts[:3])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert trackers[0].delta() == sum(rewards)
    assert trackers[1].delta() == sum(rewards)
    assert trackers[2].delta() == 0
    turn_round(consensuses)


def test_manual_moveCoreData(pledge_agent, stake_hub, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [4999, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    old_turn_round(consensuses)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    pledge_agent.moveCOREData(operators[0], accounts[0], {'from': accounts[1]})
    pledge_agent.moveCOREData(operators[0], accounts[1], {'from': accounts[2]})
    turn_round(consensuses, round_count=2)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    coin_reward = COIN_REWARD_NO_POWER // 2 + TOTAL_REWARD // 2 // 2
    btc_reward = TOTAL_REWARD // 4 + (BTC_REWARD_NO_POWER - 1) // 2
    rewards = [coin_reward, 0, btc_reward]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == sum(rewards)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == COIN_REWARD_NO_POWER // 2 + (BTC_REWARD_NO_POWER - 1) // 2
    turn_round(consensuses)


def test_manual_moveCoreData_after_adding_stake(pledge_agent, stake_hub, set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [2500, 10000], [4999, 1000], [5000, 1000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    old_turn_round()
    delegate_amount = 500000
    btc_value = 100
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[0], accounts[1], delegate_amount)
    old_delegate_coin_success(operators[1], accounts[0], delegate_amount)
    old_delegate_coin_success(operators[1], accounts[1], delegate_amount)
    old_turn_round(consensuses)
    tx_id0 = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    tx_id1 = old_delegate_btc_success(btc_value, operators[0], accounts[1])
    tx_id2 = old_delegate_btc_success(btc_value, operators[1], accounts[0])
    tx_id3 = old_delegate_btc_success(btc_value, operators[1], accounts[1])
    old_turn_round(consensuses)
    __init_hybrid_score_mock()
    __move_btc_data([tx_id0, tx_id1, tx_id2, tx_id3])
    stake_hub.setCandidateScoresMap(operators[0], delegate_amount * 2, 0, btc_value * 2 * 5000)
    stake_hub.setCandidateScoresMap(operators[1], delegate_amount * 2, 0, btc_value * 2 * 5000)
    pledge_agent.moveCOREData(operators[0], accounts[0], {'from': accounts[1]})
    turn_round(consensuses, round_count=2)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    coin_reward = COIN_REWARD_NO_POWER // 2 + TOTAL_REWARD // 2 // 2
    btc_reward = TOTAL_REWARD // 4 * 2 + (BTC_REWARD_NO_POWER - 1) // 2 * 2
    rewards = [coin_reward, 0, btc_reward]
    __check_stake_hub_delegator_map(accounts[0], {'changeRound': get_current_round(),
                                                  'rewards': rewards})
    trackers = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == sum(rewards)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert trackers.delta() == COIN_REWARD_NO_POWER // 2 + (BTC_REWARD_NO_POWER - 1) // 2 * 2
    turn_round(consensuses)


def test_rewardMap_with_historical_rewards(btc_stake, core_agent, hash_power_agent, stake_hub,
                                           set_candidate):
    stake_manager.set_lp_rates([[0, 1000], [5000, 10000], [5001, 1000]])
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 500000
    btc_value = 100
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    tx_id = mock_delegate_btc_success(operators[0], accounts[0], btc_value)
    delegate_power_success(operators[1], accounts[0])
    turn_round(consensuses, round_count=2)
    mock_delegate_coin_success(operators[0], accounts[0], delegate_amount)
    mock_transfer_btc_success(tx_id, operators[2])
    assert core_agent.rewardMap(accounts[0]) == [COIN_REWARD_NO_POWER, delegate_amount]
    assert btc_stake.rewardMap(accounts[0]) == [BTC_REWARD_NO_POWER - 1, 0, btc_value]
    assert hash_power_agent.rewardMap(accounts[0]) == [TOTAL_REWARD, 1]
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    assert stake_hub.getDelegatorMap(accounts[0])[1] == [COIN_REWARD_NO_POWER, TOTAL_REWARD, BTC_REWARD_NO_POWER - 1]
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2 * 2 + TOTAL_REWARD


def __move_btc_data(tx_ids):
    return BTC_STAKE.moveDataMock(tx_ids)


def __init_hybrid_score_mock():
    tx = STAKE_HUB.initHybridScoreMock()
    set_round_tag(get_current_round())
    return tx


def __get_candidate_list_by_delegator(delegator):
    candidate_info = CORE_AGENT.getCandidateListByDelegator(delegator)
    return candidate_info


def __get_stake_hub_delegator_map(delegator):
    delegator_map = STAKE_HUB.getDelegatorMap(delegator)
    return delegator_map


def __check_stake_hub_delegator_map(delegator, result):
    delegator_map = STAKE_HUB.getDelegatorMap(delegator)
    assert delegator_map[0] == result['changeRound']
    assert delegator_map[1] == result['rewards']
    return delegator_map


def __get_reward_map_info(delegate):
    rewards, unclaimed_reward = BTC_STAKE.getRewardMap(delegate)
    return rewards, unclaimed_reward


def __get_receipt_map_info(tx_id):
    receipt_map = BTC_STAKE.receiptMap(tx_id)
    return receipt_map


def __calc_stake_amount_discount(asset_reward, asset_stake_amount, coin_stake_amount, reward_pool=0,
                                 system_reward=100000000,
                                 asset_weight=1):
    lp_rates = Discount.lp_rates
    discount = Utils.DENOMINATOR
    stake_rate = int(coin_stake_amount / (asset_stake_amount / asset_weight))
    for i in lp_rates:
        if stake_rate >= i:
            discount = lp_rates[i]
            break
    actual_account_btc_reward = asset_reward * discount // Utils.DENOMINATOR
    if discount > Utils.DENOMINATOR:
        actual_bonus = actual_account_btc_reward - asset_reward
        if actual_bonus > reward_pool:
            system_reward -= actual_bonus
            reward_pool += actual_bonus
        reward_pool -= actual_bonus
    if asset_reward > actual_account_btc_reward:
        reward_pool += asset_reward - actual_account_btc_reward
    return actual_account_btc_reward, reward_pool


def __update_core_stake_amount(delegator, core_rate, asset_stake_amount):
    core_acc_stake_amount = asset_stake_amount * core_rate
    CORE_AGENT.setCoreRewardMap(delegator, 0, core_acc_stake_amount)
    return core_acc_stake_amount


def __calc_btc_deducted_stake_duration_reward(validator_reward, duration, tlp_rates=None):
    duration = duration * Utils.ROUND_INTERVAL
    if tlp_rates is None:
        tlp_rates = Discount.tlp_rates
    stake_duration = Utils.DENOMINATOR
    if len(tlp_rates) == 1:
        for t in tlp_rates:
            stake_duration = tlp_rates[t]
    for i in tlp_rates:
        time_stamp = i * Utils.MONTH_TIMESTAMP
        if duration >= time_stamp:
            stake_duration = tlp_rates[i]
            break
    if validator_reward is None:
        validator_reward = BLOCK_REWARD // 2
    btc_reward_claimed = validator_reward * stake_duration // Utils.DENOMINATOR
    unclaim_amount = validator_reward - btc_reward_claimed
    return btc_reward_claimed, unclaim_amount


def stake_hub_calculate_reward(account, sender=None):
    if sender is None:
        sender = accounts[0]
    tx = STAKE_HUB.calculateReward(account, {'from': sender})
    return tx
