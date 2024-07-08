import brownie
import pytest
from brownie import *
from .calc_reward import set_delegate, parse_delegation, Discount
from .common import register_candidate, turn_round, get_current_round, claim_stake_and_relay_reward
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
BTC_VALUE = 2000
TX_FEE = 100
FEE = 0
BTC_REWARD = 0
MONTH = 30
# BTC delegation-related
PUBLIC_KEY = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
LOCK_TIME = 1736956800


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, pledge_agent):
    global BLOCK_REWARD, FEE, BTC_REWARD, COIN_REWARD
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LIGHT_CLIENT, MIN_INIT_DELEGATE_VALUE, CANDIDATE_HUB
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    total_reward = BLOCK_REWARD // 2
    BTC_REWARD = total_reward * (HardCap.BTC_HARD_CAP * Utils.DENOMINATOR // HardCap.SUM_HARD_CAP) // Utils.DENOMINATOR
    MIN_INIT_DELEGATE_VALUE = pledge_agent.requiredCoinDeposit()
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    CANDIDATE_HUB = candidate_hub
    BTC_LIGHT_CLIENT = btc_light_client
    STAKE_HUB.setBtcPoolRate(4000)
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    __set_block_time_stamp(150)
    tlp_rates, lp_rates = Discount().get_init_discount()
    btc_stake.setInitTlpRates(*tlp_rates)
    stake_hub.setInitLpRates(*lp_rates)
    btc_stake.setIsActive(1)
    stake_hub.setIsActive(4)


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


@pytest.fixture()
def delegate_btc_valid_tx():
    operator = accounts[5]
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operator, accounts[0], lock_data=lock_script)
    tx_id_list = [tx_id]
    return lock_script, btc_tx, tx_id_list


def test_delegate_btc_success_public_hash(btc_stake, set_candidate, delegate_btc_valid_tx):
    __set_lp_rates()
    __set_block_time_stamp(31)
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id_list[0],
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': BTC_VALUE
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    reward, _ = __calculate_btc_staking_duration_discount(BTC_VALUE, 31)
    assert tracker.delta() == reward


@pytest.mark.parametrize("pledge_days", [1, 2, 29, 30, 31, 149, 150, 151, 239, 240, 241, 359, 360, 361])
def test_claim_btc_rewards_for_various_stake_durations(btc_stake, set_candidate, delegate_btc_valid_tx, stake_hub,
                                                       pledge_days):
    __set_lp_rates()
    __set_block_time_stamp(pledge_days)
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    reward, unclaimed_reward = __calculate_btc_staking_duration_discount(BTC_VALUE, pledge_days)
    assert tracker.delta() == reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


def test_no_duration_discount_without_btc_rewards(btc_stake, set_candidate, delegate_btc_valid_tx):
    __set_lp_rates()
    __set_block_time_stamp(MONTH)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == 0
    assert STAKE_HUB.unclaimedReward() == 0


@pytest.mark.parametrize("is_active", [0, 1])
def test_enable_disable_duration_discount(btc_stake, set_candidate, delegate_btc_valid_tx, is_active):
    __set_lp_rates()
    __set_is_btc_stake_active(is_active)
    operators, consensuses = set_candidate
    __set_block_time_stamp(MONTH)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    stake_duration = 360
    if is_active == 1:
        stake_duration = MONTH
    reward, unclaimed_reward = __calculate_btc_staking_duration_discount(BTC_VALUE, stake_duration)
    assert tracker.delta() == reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


@pytest.mark.parametrize("is_active", [True, False])
def test_no_stake_duration_rewards(btc_stake, set_candidate, delegate_btc_valid_tx, is_active):
    __set_lp_rates()
    __set_tlp_rates()
    operators, consensuses = set_candidate
    __set_block_time_stamp(MONTH)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    reward, unclaimed_reward = __calculate_btc_staking_duration_discount(BTC_VALUE)
    assert tracker.delta() == reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


@pytest.mark.parametrize("tlp", [[0, 3000], [2592000, 5000], [9092000, 8000]])
def test_one_level_stake_duration_reward(btc_stake, set_candidate, delegate_btc_valid_tx, tlp):
    __set_lp_rates()
    __set_tlp_rates([tlp])
    operators, consensuses = set_candidate
    __set_block_time_stamp(MONTH)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    reward, unclaimed_reward = __calculate_btc_staking_duration_discount(BTC_VALUE, MONTH, tlp_rates={tlp[0]: tlp[1]})
    assert tracker.delta() == reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


def test_core_rewards_discount_btc_rewards(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                           delegate_btc_valid_tx, core_agent):
    __set_tlp_rates()
    __set_is_stake_hub_active(1)
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], MIN_INIT_DELEGATE_VALUE * 800)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 1000)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    reward, unclaimed_reward = __calculate_btc_reward_with_core_discount(BLOCK_REWARD // 2, BLOCK_REWARD // 4 * 2)
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == reward + BLOCK_REWARD // 4 * 2
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


@pytest.mark.parametrize("core_rate",
                         [0, 1989, 2001, 5000, 6000, 7000, 9000, 11000, 12001, 13000])
def test_each_bracket_discounted_rewards_accuracy(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                  delegate_btc_valid_tx, core_agent, core_rate):
    __set_tlp_rates()
    __set_is_stake_hub_active(4)
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], MIN_INIT_DELEGATE_VALUE * 1000, delegate=accounts[0])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 100)
    turn_round()
    turn_round(consensuses)
    reward1 = __update_core_accured_reward(operators[1], core_rate, BLOCK_REWARD // 2, MIN_INIT_DELEGATE_VALUE * 1000)
    tracker = get_tracker(accounts[0])
    reward, unclaimed_reward = __calculate_btc_reward_with_core_discount(BLOCK_REWARD // 2, reward1)
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == reward + reward1
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


def test_core_reward_claim_discounted_by_core_ratio(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                    core_agent):
    __set_tlp_rates()
    __set_is_stake_hub_active(1)
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], MIN_INIT_DELEGATE_VALUE, delegate=accounts[0])
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    reward, unclaimed_reward = __calculate_btc_reward_with_core_discount(BLOCK_REWARD // 4, BLOCK_REWARD // 4)
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


@pytest.mark.parametrize("core_rate", [0, 4500, 5000, 6000, 7000, 11000, 12001, 13000])
def test_hash_reward_claim_discounted_by_core_ratio(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                    core_agent, core_rate):
    btc_value = 200000
    __set_tlp_rates()
    __set_is_stake_hub_active(2)
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], MIN_INIT_DELEGATE_VALUE * 1000, delegate=accounts[0])
    __delegate_power(operators[2], accounts[0])
    __delegate_btc(operators[0], accounts[1], btc_value)
    turn_round()
    turn_round(consensuses)
    reward1 = __update_core_accured_reward(operators[1], core_rate, BLOCK_REWARD // 2, MIN_INIT_DELEGATE_VALUE * 1000)
    tracker = get_tracker(accounts[0])
    reward, unclaimed_reward = __calculate_btc_reward_with_core_discount(BLOCK_REWARD // 2, reward1)
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == reward + reward1
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward


@pytest.mark.parametrize("core_rate", [0, 500, 5000, 9000, 11000, 23000])
def test_claim_core_and_btc_rewards_with_core_ratio_discount(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                             core_agent, core_rate):
    btc_value = 50
    __set_tlp_rates()
    __set_is_stake_hub_active(5)
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], MIN_INIT_DELEGATE_VALUE, delegate=accounts[0])
    __delegate_btc(operators[2], accounts[0], btc_value)
    turn_round()
    turn_round(consensuses)
    rewards, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE)],
        "btc": [],
    }, {
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], BLOCK_REWARD // 2)
    delegator_btc_reward = rewards[2][accounts[0]]
    claimed_core_reward = __update_core_accured_reward(operators[0], core_rate, delegator_btc_reward,
                                                       MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    claimed_core_reward, unclaimed_core = __calculate_btc_reward_with_core_discount(claimed_core_reward,
                                                                                    claimed_core_reward)
    claimed_btc_reward, unclaimed_btc = __calculate_btc_reward_with_core_discount(delegator_btc_reward,
                                                                                  claimed_core_reward)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == claimed_core_reward + claimed_btc_reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_core + unclaimed_btc


@pytest.mark.parametrize("core_rate", [0, 5000, 9000, 11000, 23000])
def test_claim_core_and_power_rewards_with_core_ratio_discount(btc_stake, candidate_hub, btc_light_client,
                                                               set_candidate,
                                                               core_agent, core_rate):
    power_value = 50
    __set_tlp_rates()
    __set_is_stake_hub_active(3)
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], MIN_INIT_DELEGATE_VALUE, delegate=accounts[0])
    __delegate_power(operators[2], accounts[0], power_value)
    turn_round()
    turn_round(consensuses)
    rewards, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE)],
        "btc": [],
    }, {
        "address": operators[2],
        "active": True,
        "power": [set_delegate(accounts[0], power_value)],
        "coin": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    delegator_power_reward = rewards[1][accounts[0]]
    claimed_core_reward = __update_core_accured_reward(operators[0], core_rate, delegator_power_reward,
                                                       MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    claimed_core_reward, unclaimed_core = __calculate_btc_reward_with_core_discount(claimed_core_reward,
                                                                                    claimed_core_reward)
    claimed_btc_reward, unclaimed_btc = __calculate_btc_reward_with_core_discount(delegator_power_reward,
                                                                                  claimed_core_reward)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == claimed_core_reward + claimed_btc_reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_core + unclaimed_btc


@pytest.mark.parametrize("core_rate", [0, 500, 4500, 5000, 6000, 6500, 9000, 12001, 13000])
def test_claim_hash_and_btc_rewards_with_core_ratio_discount(btc_stake, candidate_hub, btc_light_client,
                                                             core_agent, core_rate):
    btc_value = 50
    __set_tlp_rates()
    __set_is_stake_hub_active(6)
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    __delegate_coin(operators[0], MIN_INIT_DELEGATE_VALUE, delegate=accounts[0])
    __delegate_power(operators[1], accounts[0], value=1)
    __delegate_btc(operators[2], accounts[0], btc_value)
    turn_round()
    turn_round(consensuses)
    rewards, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE)],
        "btc": [],
    }, {
        "address": operators[1],
        "active": True,
        "power": [set_delegate(accounts[0], 1)],
        "coin": [],
        "btc": []
    }, {
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], BLOCK_REWARD // 2)
    delegator_power_reward = rewards[1][accounts[0]]
    delegator_btc_reward = rewards[2][accounts[0]]
    claimed_core_reward = __update_core_accured_reward(operators[0], core_rate, delegator_btc_reward,
                                                       MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    claimed_btc_reward, unclaimed_btc = __calculate_btc_reward_with_core_discount(delegator_btc_reward,
                                                                                  claimed_core_reward)
    claimed_power_reward, unclaimed_power = __calculate_btc_reward_with_core_discount(delegator_power_reward,
                                                                                      claimed_core_reward)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == claimed_btc_reward + claimed_power_reward + claimed_core_reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_btc + unclaimed_power


@pytest.mark.parametrize("core_rate", [0, 2001, 4500, 5000, 6500, 7000, 9000, 11000, 12001, 13000])
def test_core_hash_btc_rewards_discounted_by_core_ratio(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                        core_agent, core_rate):
    btc_value = 50
    __set_tlp_rates()
    __set_is_stake_hub_active(7)
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], MIN_INIT_DELEGATE_VALUE, delegate=accounts[0])
    __delegate_power(operators[1], accounts[0], value=1)
    __delegate_btc(operators[2], accounts[0], btc_value)
    turn_round()
    turn_round(consensuses)
    rewards, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE)],
        "btc": [],
    }, {
        "address": operators[1],
        "active": True,
        "power": [set_delegate(accounts[0], 1)],
        "coin": [],
        "btc": []
    }, {
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_value)]
    }], BLOCK_REWARD // 2)
    delegator_power_reward = rewards[1][accounts[0]]
    delegator_btc_reward = rewards[2][accounts[0]]
    claimed_core_reward = __update_core_accured_reward(operators[0], core_rate, delegator_btc_reward,
                                                       MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    claimed_core_reward, unclaimed_core = __calculate_btc_reward_with_core_discount(claimed_core_reward,
                                                                                    claimed_core_reward)
    claimed_btc_reward, unclaimed_btc = __calculate_btc_reward_with_core_discount(delegator_btc_reward,
                                                                                  claimed_core_reward)
    claimed_power_reward, unclaimed_power = __calculate_btc_reward_with_core_discount(delegator_power_reward,
                                                                                      claimed_core_reward)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == claimed_btc_reward + claimed_power_reward + claimed_core_reward
    assert STAKE_HUB.unclaimedReward() == unclaimed_core + unclaimed_btc + unclaimed_power


def test_discount_applied_to_core_total_rewards(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                delegate_btc_valid_tx, core_agent):
    __set_tlp_rates()
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    __set_is_stake_hub_active(4)
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[1])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": []
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward[0][accounts[0]] > 0


def test_same_candidate_rewards_with_discounts(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                               delegate_btc_valid_tx, core_agent):
    __set_tlp_rates()
    __set_is_stake_hub_active(4)
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount),
                 set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward[0][accounts[0]] > 0


def test_revert_on_discount_exceeding_100_percent(btc_stake, set_candidate,
                                                  delegate_btc_valid_tx):
    __set_tlp_rates()
    __set_is_stake_hub_active(1)
    __set_lp_rates([[0, 12000]])
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount),
                 set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2, core_lp=True)
    with brownie.reverts("Integer overflow"):
        claim_stake_and_relay_reward(accounts[0])


def test_normal_duration_and_reward_discounts(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                              delegate_btc_valid_tx):
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[1])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[1], [accounts[1]] * 100)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [set_delegate(accounts[1], 100)],
        "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
        "btc": []
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward[0][accounts[0]] > 0


def test_multiple_btc_stakes_and_reward_claim(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                              delegate_btc_valid_tx):
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[1])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    __delegate_btc(operators[1], accounts[0])
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 100)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
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
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }, {
        "address": operators[2],
        "active": True,
        "power": [set_delegate(accounts[2], 100)],
        "coin": [],
        "btc": []
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    tx = claim_stake_and_relay_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == account_rewards[accounts[0]]
    assert STAKE_HUB.unclaimedReward() == unclaimed_reward[0][accounts[0]] > 0
    assert unclaimed_reward[1]['duration'] > unclaimed_reward[1]['core'] > 0


def test_deducted_rewards_added_to_next_round_btc(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                                  delegate_btc_valid_tx):
    __set_btc_pool_rate(Utils.DENOMINATOR)
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[1])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    __delegate_btc(operators[1], accounts[0], BTC_VALUE // 4)
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[2], [accounts[2]] * 100)
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
        "btc": [set_delegate(accounts[0], BTC_VALUE // 4, stake_duration=MONTH)]
    }, {
        "address": operators[2],
        "active": True,
        "power": [set_delegate(accounts[2], 100)],
        "coin": [],
        "btc": []
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    candidates_reward, _ = __distribute_next_round_rewards(operators, unclaimed_reward, round_reward)
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    assert bonus['btc'][operators[0]] == candidates_reward['btc'][operators[0]]
    assert bonus['btc'][operators[1]] == candidates_reward['btc'][operators[1]]
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
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
        "btc": [set_delegate(accounts[0], BTC_VALUE // 4, stake_duration=MONTH)]
    }], BLOCK_REWARD // 2, core_lp=True, compensation_reward=candidates_reward)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]


def test_deducted_rewards_added_to_next_round_core(btc_stake, set_candidate, candidate_hub, btc_light_client):
    __set_btc_pool_rate(0)
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    unclaimed_reward = __calculate_compensation_reward_for_staking(operators, consensuses)
    candidates_reward, _ = __distribute_next_round_rewards(operators, unclaimed_reward[0], unclaimed_reward[1], 0)
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    assert bonus['coin']['bonus'] == unclaimed_reward[0][0][accounts[0]]
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
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
    }], BLOCK_REWARD // 2, core_lp=True, compensation_reward=candidates_reward)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert account_rewards[accounts[0]] == tracker.delta()


@pytest.mark.parametrize("pool_rate", [1000, 4000, 5000, 6000, 7500, 9500])
def test_next_round_successfully_includes_deducted_rewards(btc_stake, set_candidate, pool_rate):
    __set_btc_pool_rate(pool_rate)
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    unclaimed_reward = __calculate_compensation_reward_for_staking(operators, consensuses)
    candidates_reward, bonus = __distribute_next_round_rewards(operators, unclaimed_reward[0], unclaimed_reward[1],
                                                               pool_rate)
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    unclaimed_reward = unclaimed_reward[0][0][accounts[0]]
    assert bonus['btc']['bonus'] == unclaimed_reward * pool_rate // Utils.DENOMINATOR
    assert bonus['coin']['bonus'] == unclaimed_reward * (Utils.DENOMINATOR - pool_rate) // Utils.DENOMINATOR
    _, unclaimed_reward, account_rewards, _, _ = parse_delegation([{
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
    }], BLOCK_REWARD // 2, core_lp=True, compensation_reward=candidates_reward)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert account_rewards[accounts[0]] == tracker.delta()


def test_non_validators_cannot_receive_deducted_rewards(btc_stake, set_candidate):
    __set_btc_pool_rate(5000)
    __set_block_time_stamp(MONTH)
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_btc(operators[0], accounts[0])
    turn_round()
    CANDIDATE_HUB.refuseDelegate({'from': operators[2]})
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward() // 2
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    actual_core_bonus = bonus['coin']['bonus']
    actual_btc_bonus = bonus['btc']['bonus']
    assert actual_core_bonus == actual_btc_bonus == unclaimed_reward


def test_no_stake_still_gets_deducted_rewards(btc_stake, set_candidate, stake_hub, delegate_btc_valid_tx):
    __set_btc_pool_rate(5000)
    __set_block_time_stamp(MONTH)
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    lock_script, btc_tx, _ = delegate_btc_valid_tx
    BTC_STAKE.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    actual_core_bonus = bonus['coin']['bonus']
    actual_btc_bonus = bonus['btc']['bonus']
    assert len(bonus) == 3
    assert actual_core_bonus == actual_btc_bonus == unclaimed_reward // 2


def test_multiple_users_rewards_deducted(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                         delegate_btc_valid_tx):
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    __delegate_btc(operators[0], accounts[1], BTC_VALUE // 4, stake_duration=150)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_rewards, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH),
                set_delegate(accounts[1], BTC_VALUE // 4, stake_duration=150)]
    }], BLOCK_REWARD // 2, core_lp=True)
    claim_stake_and_relay_reward(accounts[0])
    claim_stake_and_relay_reward(accounts[1])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    assert unclaimed_reward == unclaimed_rewards[0][accounts[0]] + unclaimed_rewards[0][accounts[1]]


def test_no_coin_rewards_for_btc_stake(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                       delegate_btc_valid_tx):
    pool_rate = 4000
    __set_btc_pool_rate(pool_rate)
    __set_block_time_stamp(MONTH)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    _, unclaimed_rewards, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE, stake_duration=MONTH)]
    }], BLOCK_REWARD // 2, core_lp=True)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    actual_core_bonus = bonus['coin']['bonus']
    assert len(bonus) == 3
    assert unclaimed_reward == unclaimed_rewards[0][accounts[0]]
    assert unclaimed_reward * (Utils.DENOMINATOR - pool_rate) // Utils.DENOMINATOR == actual_core_bonus


def test_turn_round_btc_rewards_without_btc_stake(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                                  delegate_btc_valid_tx):
    __set_btc_pool_rate(Utils.DENOMINATOR)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    tx = turn_round(consensuses)
    assert 'roundReward' in tx.events
    bonus = __get_candidate_bonus(tx)
    assert bonus['coin']['bonus'] == 0
    assert bonus['btc']['bonus'] == unclaimed_reward


def test_turn_round_core_rewards_without_core_stake(btc_stake, stake_hub, set_candidate, candidate_hub,
                                                    btc_light_client,
                                                    delegate_btc_valid_tx):
    __set_btc_pool_rate(0)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    tx = turn_round(consensuses)
    assert 'roundReward' in tx.events
    bonus = __get_candidate_bonus(tx)
    assert bonus['coin']['bonus'] == unclaimed_reward
    assert bonus['btc']['bonus'] == 0


def test_turn_round_rewards_with_single_stake(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                              delegate_btc_valid_tx):
    __set_btc_pool_rate(5000)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    operators, consensuses = set_candidate
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    tx = turn_round(consensuses)
    assert 'roundReward' in tx.events
    bonus = __get_candidate_bonus(tx)
    assert bonus['coin']['bonus'] == unclaimed_reward // 2
    assert bonus['btc']['bonus'] == unclaimed_reward // 2


def test_turn_round_rewards_without_staking(btc_stake, set_candidate, candidate_hub, btc_light_client,
                                            delegate_btc_valid_tx):
    __set_btc_pool_rate(5000)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 200
    operators, consensuses = set_candidate
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[2])
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    round_time_tag = CANDIDATE_HUB.roundTag() - 6
    BTC_LIGHT_CLIENT.setMiners(round_time_tag, operators[1], [accounts[1]] * 100)
    turn_round()
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    claim_stake_and_relay_reward(accounts[2])
    unclaimed_reward = STAKE_HUB.unclaimedReward()
    assert unclaimed_reward > 0
    tx = turn_round(consensuses)
    bonus = __get_candidate_bonus(tx)
    assert len(bonus) == 3
    assert bonus['coin']['bonus'] == unclaimed_reward // 2
    assert bonus['btc']['bonus'] == unclaimed_reward // 2
    __set_is_btc_stake_active(0)
    __set_is_stake_hub_active(0)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[0])
    claim_stake_and_relay_reward(accounts[2])
    assert tracker0.delta() == BTC_REWARD + unclaimed_reward // 2
    assert tracker1.delta() == BLOCK_REWARD // 4 + unclaimed_reward // 2


def __delegate_btc(operator, delegator, btc_amount=None, lock_script=None, lock_time=None, stake_duration=None):
    if stake_duration is None:
        stake_duration = MONTH
    if lock_time is None:
        lock_time = LOCK_TIME
    if lock_script is None:
        lock_script = get_lock_script(lock_time, PUBLIC_KEY)
    if btc_amount is None:
        btc_amount = BTC_VALUE
    __set_block_time_stamp(stake_duration)
    btc_tx, tx_id = get_btc_tx(btc_amount, Utils.CHAIN_ID, operator, delegator, lock_data=lock_time)
    BTC_STAKE.delegate(btc_tx, 0, [], 0, lock_script)
    return lock_script, btc_tx, tx_id


def __delegate_power(candidate, delegator, value=1, stake_round=0):
    stake_round = get_current_round() - 6 + stake_round
    BTC_LIGHT_CLIENT.setMiners(stake_round, candidate, [delegator] * value)


def __delegate_coin(candidate, value=None, delegate=None):
    if value is None:
        value = MIN_INIT_DELEGATE_VALUE
    if delegate is None:
        delegate = accounts[0]
    CORE_AGENT.delegateCoin(candidate, {"value": value, "from": delegate})


def __set_is_btc_stake_active(value=0):
    BTC_STAKE.setIsActive(value)


def __set_is_stake_hub_active(value):
    STAKE_HUB.setIsActive(value)


def __set_block_time_stamp(timestamp, stake_lock_time=None, time_type='day'):
    if stake_lock_time is None:
        stake_lock_time = LOCK_TIME
    # the default timestamp is days
    if time_type == 'day':
        timestamp = timestamp * Utils.ROUND_INTERVAL
        time1 = stake_lock_time - timestamp
    else:
        timestamp = timestamp * Utils.MONTH_TIMESTAMP
        time1 = stake_lock_time - timestamp
    BTC_LIGHT_CLIENT.setCheckResult(True, time1)


def __set_btc_pool_rate(value):
    STAKE_HUB.setBtcPoolRate(value)


def __set_tlp_rates(rates=None):
    BTC_STAKE.popTtlpRates()
    if rates:
        for r in rates:
            tl = r[0]
            tp = r[1]
            BTC_STAKE.setTlpRates(tl, tp)


def __set_lp_rates(rates=None):
    STAKE_HUB.popLpRates()
    if rates:
        for r in rates:
            tl = r[0]
            tp = r[1]
            STAKE_HUB.setLpRates(tl, tp)


def __get_candidate_bonus(tx):
    bonus = {
        'coin': {},
        'power': {},
        'btc': {}
    }
    for t in tx.events['roundReward']:
        # core
        if t['name'] == Web3.keccak(text='CORE').hex():
            for index, v in enumerate(t['validator']):
                bonus['coin'][v] = t['amount'][index]
            bonus['coin']['bonus'] = t['bonus']
        # power
        elif t['name'] == Web3.keccak(text='HASHPOWER').hex():
            for index, v in enumerate(t['validator']):
                bonus['power'][v] = t['amount'][index]
            bonus['power']['bonus'] = t['bonus']

        # btc
        elif t['name'] == Web3.keccak(text='BTC').hex():
            for index, v in enumerate(t['validator']):
                bonus['btc'][v] = t['amount'][index]
            bonus['btc']['bonus'] = t['bonus']

    return bonus


def __get_candidate_list_by_delegator(delegator):
    candidate_info = CORE_AGENT.getCandidateListByDelegator(delegator)
    return candidate_info


def __get_reward_map_info(delegate):
    rewards, unclaimed_reward = BTC_STAKE.getRewardMap(delegate)
    return rewards, unclaimed_reward


def __get_receipt_map_info(tx_id):
    receipt_map = BTC_STAKE.receiptMap(tx_id)
    return receipt_map


def __calculate_btc_reward_with_core_discount(btc_reward, coin_reward, unclaimed_reward=0):
    lp_rates = Discount.lp_rates
    if btc_reward == 0:
        return 0, 0
    stake_duration = Utils.DENOMINATOR
    core_reward_rate = coin_reward * Utils.DENOMINATOR // btc_reward
    for i in lp_rates:
        if core_reward_rate >= i:
            stake_duration = lp_rates[i]
            break
    actual_account_btc_reward = btc_reward * stake_duration // Utils.DENOMINATOR
    unclaimed_reward += btc_reward - actual_account_btc_reward
    return actual_account_btc_reward, unclaimed_reward


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
    unclaimed_rewards = unclaimed[0]
    for u in unclaimed_rewards:
        unclaimed_reward += unclaimed_rewards[u]
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


def __update_core_accured_reward(candidate, core_rate, claimed_reward, stake_amount):
    """
    Increase BTC staking amount to avoid hard caps on coin and power rewards. Then,
    adjust data in AccruedRewardMap to control the distributable Core reward and the ratio between Core reward and hash reward.
    """
    core_value = 1e6
    reward = core_rate * claimed_reward // Utils.DENOMINATOR
    accured_reward = reward * core_value // stake_amount
    CORE_AGENT.setAccuredRewardMap(candidate, get_current_round() - 1, accured_reward)
    return reward


def __calculate_compensation_reward_for_staking(operators, consensuses):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 50
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[0])
    __delegate_coin(operators[0], delegate_amount, delegate=accounts[1])
    __delegate_coin(operators[1], delegate_amount, delegate=accounts[1])
    __delegate_btc(operators[0], accounts[0])
    __delegate_btc(operators[1], accounts[0], BTC_VALUE * 2, stake_duration=150)
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
    }], BLOCK_REWARD // 2, core_lp=True)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    return (unclaimed_reward, round_reward)


def __calculate_btc_staking_duration_discount(total_btc, duration=360, claim_btc=None, validator_score=None,
                                              btc_factor=10,
                                              total_reward=None, tlp_rates=None):
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
    collateral_state_btc = HardCap.BTC_HARD_CAP * Utils.DENOMINATOR // HardCap.SUM_HARD_CAP
    if total_reward is None:
        total_reward = BLOCK_REWARD // 2
    if validator_score is None:
        validator_score = total_btc
    if claim_btc is None:
        claim_btc = total_btc
    reward = total_reward * (total_btc * btc_factor) // (
            validator_score * btc_factor) * collateral_state_btc // Utils.DENOMINATOR
    btc_reward = reward * Utils.BTC_DECIMAL // total_btc * claim_btc // Utils.BTC_DECIMAL
    btc_reward_claimed = btc_reward * stake_duration // Utils.DENOMINATOR
    unclaim_amount = btc_reward - btc_reward_claimed
    return btc_reward_claimed, unclaim_amount
