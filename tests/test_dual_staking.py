import pytest
from .calc_reward import set_delegate, parse_delegation, Discount
from .common import register_candidate, turn_round, stake_hub_claim_reward, set_round_tag
from .delegate import *
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
DELEGATE_VALUE = 2000000
BLOCK_REWARD = 0
BTC_VALUE = 200
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
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, pledge_agent,
                     btc_lst_stake, gov_hub, hash_power_agent, btc_agent, system_reward):
    global BLOCK_REWARD, FEE, COIN_REWARD, TOTAL_REWAR, TOTAL_REWARD, HASH_POWER_AGENT, BTC_AGENT, stake_manager
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LIGHT_CLIENT, MIN_INIT_DELEGATE_VALUE, CANDIDATE_HUB, BTC_LST_STAKE
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    MIN_INIT_DELEGATE_VALUE = pledge_agent.requiredCoinDeposit()
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    CANDIDATE_HUB = candidate_hub
    BTC_LIGHT_CLIENT = btc_light_client
    BTC_AGENT = btc_agent
    candidate_hub.setControlRoundTimeTag(True)
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
                                                  core_rate, system_reward):
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 2)
    turn_round(consensuses, round_count=2)
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
        assert tx.events['rewardTo']['amount'] == (reward - TOTAL_REWARD) * 10
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


@pytest.mark.parametrize("percentage", [[12000, 73143], [20000, 365715]])
def test_btc_lst_claim_extra_reward(btc_stake, set_candidate, btc_agent, percentage):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(percentage[0])), 64)
    btc_agent.updateParam('lstGradePercentage', hex_value, {'from': accounts[0]})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 3 * percentage[0] // Utils.DENOMINATOR
    assert tracker.delta() == actual_reward
    bonus = percentage[1]
    assert STAKE_HUB.surplus() == bonus
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    bonus -= (actual_reward - TOTAL_REWARD * 3)
    assert STAKE_HUB.surplus() == bonus


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
    assert stake_hub.surplus() == TOTAL_REWARD * 10 - TOTAL_REWARD


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
    [([0, 1000], [5000, 5000], [10000, 10000], [10001, 3000]), 10000000, 10, 2000],
    [([0, 1000], [5000, 5000], [10000, 10000], [10001, 3000]), 1000000, 1, 200],
    [([0, 1000], [5000, 10000], [10000, 5000], [10001, 3000]), 10000000, 20, 1000]]
                         )
def test_calc_stake_after_coin_unstake(btc_stake, set_candidate, btc_lst_stake, stake_amounts):
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


def test_calc_stake_after_coin_transfer(btc_stake, btc_lst_stake):
    delegate_amount = 1000000
    power_value = 1
    btc_value = 100
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_lp_rates([[0, 1000], [20000, 10000], [20001, 1000]])
    operators = []
    consensuses = []
    for operator in accounts[5:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    set_round_tag(LOCK_TIME // Utils.ROUND_INTERVAL - 3)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_power_success(operators[2], accounts[0], power_value)
    delegate_btc_success(operators[1], accounts[0], btc_value, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[3], accounts[0], delegate_amount)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    power_reward = TOTAL_REWARD
    btc_reward = TOTAL_REWARD * Utils.BTC_DECIMAL // btc_value * btc_value // Utils.BTC_DECIMAL
    coin_reward = TOTAL_REWARD * 2
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
    {'coinAmount': 18000e18, 'btcAmount': 1e8, 'duration': 360, 'expect_reward_pool': 9e18 - 9e17,
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
    stake_hub_claim_reward(accounts[0])
    if round_count == 0:
        assert tracker.delta() == 0
        assert stake_hub.surplus() == 0
        return
    if tests['expect_btc_reward'] == 0:
        assert tracker.delta() == total_reward
        assert stake_hub.surplus() == 0
    else:
        assert tracker.delta() == tests['expect_btc_reward'] + total_reward
        assert stake_hub.surplus() == tests['expect_reward_pool']
    turn_round(consensuses, tx_fee=tx_fee)


@pytest.mark.parametrize("tests", [
    {'delegator': ['delegateBtc', 'transferBtc'], 'expect_reward_pool': 1.215e19, 'expect_btc_reward': 6.75e18},
    {'delegator': ['transferBtc', 'delegateBtc'], 'expect_reward_pool': 4.05e18, 'expect_btc_reward': 4.05e18},
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
    stake_hub_claim_reward(accounts[0])
    coin_reward = total_reward * 2
    btc_reward = tests['expect_btc_reward']
    assert tracker.delta() == btc_reward + coin_reward
    assert stake_hub.surplus() == tests['expect_reward_pool']
    turn_round(consensuses, tx_fee=tx_fee)


def test_dual_staking_claim_success_after_btc_expiration(btc_stake, btc_agent, stake_hub, validator_set, btc_lst_stake,
                                                         set_candidate):
    stake_manager.set_is_stake_hub_active(True)
    stake_manager.set_tlp_rates()
    stake_manager.set_lp_rates([[0, 5000], [10000, 15000], [10001, 1000]])
    operators, consensuses = set_candidate
    set_last_round_tag(3)
    delegate_btc_success(operators[0], accounts[0], 100, LOCK_SCRIPT, stake_duration=YEAR)
    turn_round()
    turn_round(consensuses, round_count=4)
    delegate_coin_success(operators[1], accounts[0], 3000000)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD + TOTAL_REWARD * 3 * 15000 // Utils.DENOMINATOR


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


@pytest.mark.parametrize("tesets", [
    {'rate': [[0, 1000], [2500, 10000], [10000, 1000], [10001, 3000]], 'coin': 10000, 'btc': 2,
     'expect_reward': 6772 + 13545},
    {'rate': [[0, 5000], [2500, 10000], [10000, 1000], [10001, 3000]], 'coin': 10000, 'btc': 3,
     'expect_reward': 6772 + 6772},
])
def test_cancel_immediately_after_transfer(btc_stake, stake_hub, set_candidate, btc_lst_stake, tesets):
    delegate_amount = tesets['coin']
    btc_value = tesets['btc']
    rates = tesets['rate']
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
    assert tracker.delta() == tesets['expect_reward']


def __get_candidate_list_by_delegator(delegator):
    candidate_info = CORE_AGENT.getCandidateListByDelegator(delegator)
    return candidate_info


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
            system_reward -= actual_bonus * 10
            reward_pool += actual_bonus * 10
        reward_pool -= actual_bonus
    if asset_reward > actual_account_btc_reward:
        reward_pool += asset_reward - actual_account_btc_reward
    return actual_account_btc_reward, reward_pool


def __distribute_next_round_rewards(candidates, unclaimed, round_reward, btc_pool_rate=None):
    candidates_reward = {
        'coin': {},
        'power': {},
        'btc': {}
    }
    bonuses = [0, 0, 0]
    if btc_pool_rate is None:
        btc_pool_rate = Utils.DENOMINATOR
    unclaimed_reward = 0
    for u in unclaimed:
        unclaimed_reward += unclaimed[u]
    bonuses[2] = unclaimed_reward * btc_pool_rate // Utils.DENOMINATOR
    bonuses[0] = unclaimed_reward * (Utils.DENOMINATOR - btc_pool_rate) // Utils.DENOMINATOR
    for c in candidates_reward:
        total_reward = 0
        collateral_reward = round_reward[1][c]
        for i in collateral_reward:
            total_reward += collateral_reward[i]
        for i in collateral_reward:
            reward = collateral_reward[i]
            if c == 'coin':
                asset_bonus = bonuses[0]
            elif c == 'btc':
                asset_bonus = bonuses[2]
            else:
                asset_bonus = 0
            bonus = reward * asset_bonus // total_reward
            candidates_reward[c][i] = bonus

    return candidates_reward, bonuses


def __update_core_stake_amount(delegator, core_rate, asset_stake_amount):
    core_acc_stake_amount = asset_stake_amount * core_rate
    CORE_AGENT.setCoreRewardMap(delegator, 0, core_acc_stake_amount)
    return core_acc_stake_amount


def __calculate_compensation_reward_for_staking(operators, consensuses):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    delegate_coin_success(operators[0], delegate_amount, accounts[0])
    delegate_coin_success(operators[1], delegate_amount, accounts[0])
    delegate_coin_success(operators[0], delegate_amount, accounts[1])
    delegate_coin_success(operators[1], delegate_amount, accounts[1])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE * 2, LOCK_SCRIPT, stake_duration=150)
    round_time_tag = CANDIDATE_HUB.roundTag() - 6
    BTC_LIGHT_CLIENT.setMiners(round_time_tag, operators[2], [accounts[2]] * 100)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, round_reward, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE * 2, stake_duration=150)]
    }, {
        "address": operators[2],
        "active": True,
        "power": [set_delegate(accounts[2], 100)],
        "coin": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    return unclaimed_reward, round_reward


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
