import pytest
from .calc_reward import set_delegate, parse_delegation, Discount, set_btc_lst_delegate
from .common import register_candidate, turn_round, stake_hub_claim_reward, set_round_tag, claim_stake_and_relay_reward
from .delegate import *
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
DELEGATE_VALUE = 0
BLOCK_REWARD = 0
COIN_VALUE = 10000
BTC_VALUE = 200
POWER_VALUE = 20
BTC_LST_VALUE = 600
TX_FEE = 100
FEE = 0
MONTH = 30
TOTAL_REWARD = 0
# BTC delegation-related
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
LOCK_TIME = 1736956800
# BTCLST delegation-related
BTCLST_LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
BTCLST_REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"
stake_manager = StakeManager()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_stake, stake_hub, pledge_agent,
                     btc_lst_stake, gov_hub, btc_agent, system_reward):
    global BLOCK_REWARD, FEE, DELEGATE_VALUE, TOTAL_REWARD, MIN_INIT_DELEGATE_VALUE
    global BTC_STAKE, STAKE_HUB, CANDIDATE_HUB, BTC_LST_STAKE, PLEDGE_AGENT
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    MIN_INIT_DELEGATE_VALUE = pledge_agent.requiredCoinDeposit()
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 1000
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CANDIDATE_HUB = candidate_hub
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    set_block_time_stamp(150, LOCK_TIME)
    tlp_rates, lp_rates = Discount().get_init_discount()
    btc_agent.setAssetWeight(1)
    btc_stake.setInitTlpRates(*tlp_rates)
    btc_agent.setInitLpRates(*lp_rates)
    btc_stake.setIsActive(True)
    btc_agent.setIsActive(True)
    BTC_LST_STAKE = btc_lst_stake
    PLEDGE_AGENT = pledge_agent
    system_reward.setOperator(stake_hub.address)
    btc_lst_stake.updateParam('add', BTCLST_LOCK_SCRIPT, {'from': gov_hub.address})


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def add_candidates(count=25):
    start_count = 10
    operators = []
    consensuses = []
    for operator in accounts[start_count:start_count + count]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def mock_current_round():
    current_round = 19998
    timestamp = current_round * Utils.ROUND_INTERVAL
    return current_round, timestamp


def mock_btc_stake_lock_time(timestamp, stake_round=None):
    if stake_round is None:
        stake_round = random.randint(1, 10)
    timestamp = timestamp + (Utils.ROUND_INTERVAL * stake_round)
    end_round = timestamp // Utils.ROUND_INTERVAL
    return timestamp, end_round


def test_successful_upgrade_after_round_switch(pledge_agent, candidate_hub):
    init_round_tag, timestamp = mock_current_round()
    mock_btc_stake_lock_time(timestamp)
    old_turn_round()
    set_round_tag(init_round_tag)
    operators, consensuses = add_candidates()
    candidate_hub.setValidatorCount(21)
    old_turn_round()
    tx_ids = []
    lock_time, end_round = mock_btc_stake_lock_time(timestamp, 5)
    for index, op in enumerate(operators):
        old_delegate_coin_success(op, accounts[0], DELEGATE_VALUE + index)
    for index, op in enumerate(operators[0:10]):
        tx_id = old_delegate_btc_success(BTC_VALUE + index, op, accounts[0], lock_time)
        tx_ids.append(tx_id)
    lock_time, end_round = mock_btc_stake_lock_time(timestamp, 3)
    delegate_coin_success(operators[0], accounts[0], DELEGATE_VALUE)
    delegate_coin_success(operators[7], accounts[0], DELEGATE_VALUE)
    for index, op in enumerate(operators[10:12]):
        btc_amount = BTC_VALUE + (index + 10)
        tx_id = old_delegate_btc_success(btc_amount, op, accounts[1], lock_time)
        tx_ids.append(tx_id)
    old_delegate_coin_success(operators[8], accounts[0], DELEGATE_VALUE)
    old_delegate_coin_success(operators[12], accounts[1], DELEGATE_VALUE)
    delegate_power_success(operators[0], accounts[2], 1)
    old_turn_round(consensuses)
    delegate_power_success(operators[0], accounts[2], 1)
    old_turn_round(consensuses)
    delegate_power_success(operators[0], accounts[2], 1)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    delegate_coin_success(operators[0], accounts[0], DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[0], BTC_LST_VALUE, BTCLST_LOCK_SCRIPT)
    delegate_power_success(operators[0], accounts[0], 1)
    delegate_btc_success(operators[2], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    delegate_btc_lst_success(accounts[0], BTC_LST_VALUE, BTCLST_LOCK_SCRIPT)
    old_claim_reward_success(operators, accounts[0])
    old_claim_reward_success(operators, accounts[2])
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' in tx.events


def test_multiple_stakes_after_upgrade(set_candidate):
    btc_value = 100
    btc_lst_value = 1000
    delegate_amount = 600000
    power_value = 1
    operators, consensuses = set_candidate
    old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    old_claim_reward_success(operators, accounts[0])
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[0], btc_lst_value // 2, BTCLST_LOCK_SCRIPT)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount // 2)
    transfer_btc_success(tx_ids[0], operators[1], accounts[0])
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)],
        }, {
            "address": operators[2],
        }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(btc_lst_value, btc_lst_value // 2)}, state_map={'core_lp': 4})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


def test_cancel_and_transfer_stakes_after_upgrade(set_candidate, slash_indicator):
    btc_value = 100
    btc_lst_value = 1000
    delegate_amount = 600000
    power_value = 1
    operators, consensuses = set_candidate
    old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    old_claim_reward_success(operators, accounts[0])
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[0], btc_lst_value // 2, BTCLST_LOCK_SCRIPT)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount)
    transfer_btc_success(tx_ids[0], operators[1], accounts[0])
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2, delegate_amount),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)],
        }, {
            "address": operators[2],
        }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(btc_lst_value, btc_lst_value // 2)}, state_map={'core_lp': 4})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    slash_threshold = slash_indicator.felonyThreshold()
    for count in range(slash_threshold):
        slash_indicator.slash(consensuses[0])
        slash_indicator.slash(consensuses[1])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2
    turn_round(consensuses)


def test_new_validator_join_after_upgrade(slash_indicator):
    btc_value = 100
    btc_lst_value = 1000
    delegate_amount = 600000
    power_value = 1
    operators = []
    consensuses = []
    for operator in accounts[5:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    old_claim_reward_success(operators, accounts[0])
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    for operator in accounts[8:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    redeem_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    delegate_btc_success(operators[0], accounts[0], btc_value, LOCK_SCRIPT)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[1], delegate_amount)
    delegate_btc_success(operators[2], accounts[0], btc_value, LOCK_SCRIPT)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)],
        }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(btc_lst_value, btc_lst_value)}, state_map={'core_lp': 4})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, stake_duration=MONTH),
                    set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)],
        }, {
            "address": operators[2],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, stake_duration=MONTH)]
        }], BLOCK_REWARD // 2, state_map={'core_lp': 4})
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, stake_duration=MONTH),
                    set_delegate(accounts[0], btc_value),
                    set_delegate(accounts[1], btc_value)],
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
        }, {
            "address": operators[2],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, stake_duration=MONTH)]
        }], BLOCK_REWARD // 2, {accounts[0]: set_btc_lst_delegate(btc_lst_value)}, state_map={'core_lp': 4})
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


def test_no_btc_lst_stake_after_upgrade(set_candidate):
    btc_value = 100
    delegate_amount = 600000
    power_value = 1
    operators, consensuses = set_candidate
    old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    old_delegate_coin_success(operators[0], accounts[0], delegate_amount, False)
    delegate_power_success(operators[2], accounts[0], power_value)
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount // 2)
    old_undelegate_coin_success(operators[1], accounts[0], delegate_amount // 2, False)
    transfer_coin_success(operators[1], operators[0], accounts[0], delegate_amount // 2)
    transfer_btc_success(tx_ids[0], operators[1], accounts[0])
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount * 2, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value, btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
            "power": [set_delegate(accounts[2], power_value)],
        }, {
            "address": operators[2],
            "power": [set_delegate(accounts[0], power_value)]
        }], BLOCK_REWARD // 2, state_map={'core_lp': 4})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


def test_stake_in_next_round_after_upgrade(set_candidate):
    btc_value = 100
    delegate_amount = 600000
    operators, consensuses = set_candidate
    old_turn_round()
    tx_ids = []
    for op in operators[:2]:
        for account in accounts[:2]:
            tx_id = old_delegate_btc_success(btc_value, op, account)
            tx_ids.append(tx_id)
            old_delegate_coin_success(op, account, delegate_amount)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data(tx_ids)
    turn_round(consensuses, round_count=3)
    old_claim_reward_success(operators, accounts[0])
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount // 2)
    old_undelegate_coin_success(operators[1], accounts[0], delegate_amount // 2, False)
    transfer_coin_success(operators[1], operators[0], accounts[0], delegate_amount // 2)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "btc": [set_delegate(accounts[0], btc_value), set_delegate(accounts[1], btc_value)],
        }, {
            "address": operators[1]
        }], BLOCK_REWARD // 2, state_map={'core_lp': 4})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


@pytest.mark.parametrize("round_count", [0, 1, 2])
def test_claim_rewards_after_becoming_validator_post_upgrade(pledge_agent, validator_set, slash_indicator,
                                                             candidate_hub, round_count):
    operators = []
    consensuses = []
    for operator in accounts[5:11]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for op in operators[:4]:
        old_delegate_coin_success(op, accounts[0], MIN_INIT_DELEGATE_VALUE)
    for op in operators:
        old_delegate_coin_success(op, accounts[1], MIN_INIT_DELEGATE_VALUE)
    old_turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    old_turn_round()
    candidate_hub.unregister({'from': operators[0]})
    slash_threshold = slash_indicator.felonyThreshold()
    for count in range(slash_threshold):
        slash_indicator.slash(consensuses[2])
    candidate_hub.refuseDelegate({'from': operators[1]})
    old_turn_round(consensuses)
    candidate_hub.refuseDelegate({'from': operators[3]})
    old_turn_round(consensuses)
    assert len(validator_set.getValidatorOps()) == 2
    init_hybrid_score_mock()
    pledge_agent.moveCandidateData([operators[0]])
    turn_round(consensuses, round_count=round_count)
    operators.append(operators[0])
    consensuses.append(register_candidate(operator=operators[0]))
    candidate_hub.acceptDelegate({'from': operators[1]})
    candidate_hub.acceptDelegate({'from': operators[3]})
    required_margin = 100000000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    old_claim_reward_success(operators, accounts[0])
    turn_round(consensuses)
    assert len(validator_set.getValidatorOps()) == 6
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2 * 4


def test_btclst_claim_extra_rewards_after_upgrade(set_candidate):
    btc_lst_value = 1000
    delegate_amount = 600000
    power_value = 1
    operators, consensuses = set_candidate
    old_turn_round()
    for op in operators[:2]:
        for account in accounts[:2]:
            old_delegate_coin_success(op, account, delegate_amount)
        for i in range(3):
            delegate_power_success(op, accounts[2], power_value, stake_round=i)
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    old_claim_reward_success(operators, accounts[0])
    delegate_btc_lst_success(accounts[0], btc_lst_value, BTCLST_LOCK_SCRIPT, Utils.DENOMINATOR * 2)
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[0], btc_lst_value // 2, BTCLST_LOCK_SCRIPT)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount)
    transfer_coin_success(operators[2], operators[1], accounts[0], delegate_amount)
    transfer_coin_success(operators[1], operators[0], accounts[0], delegate_amount)
    undelegate_coin_success(operators[0], accounts[0], delegate_amount // 2)
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount // 2),
                     set_delegate(accounts[1], delegate_amount)],
            "power": [set_delegate(accounts[2], power_value)]
        },
        {
            "address": operators[1],
            "coin": [set_delegate(accounts[0], delegate_amount), set_delegate(accounts[1], delegate_amount)],
            "power": [set_delegate(accounts[2], power_value)],
        }, {
            "address": operators[2],
        }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(btc_lst_value, btc_lst_value // 2)}, state_map={
        'core_lp': 4,
        'percentage': Utils.DENOMINATOR * 2
    })
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


def test_btc_data_migration_not_affected_by_stake_duration(set_candidate):
    stake_manager.set_is_stake_hub_active(False)
    stake_manager.set_tlp_rates([[0, 5000], [2 * Utils.MONTH_TIMESTAMP, 10000]])
    btc_value = 100
    operators, consensuses = set_candidate
    old_turn_round()
    tx_id = old_delegate_btc_success(btc_value, operators[0], accounts[0])
    old_turn_round(consensuses)
    init_hybrid_score_mock()
    move_btc_data([tx_id])
    turn_round(consensuses)
    delegate_btc_success(operators[1], accounts[1], btc_value, LOCK_SCRIPT, relay=accounts[1])
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD
    turn_round(consensuses, round_count=2)
    trackers = get_trackers(accounts[:2])
    stake_hub_claim_reward(accounts[:2])
    assert trackers[0].delta() == TOTAL_REWARD * 2
    assert trackers[1].delta() == TOTAL_REWARD // 2


@pytest.mark.parametrize("hard_cap", [
    [['coreHardcap', 2000], ['hashHardcap', 9000], ['btcHardcap', 10000]],
    [['coreHardcap', 3000], ['hashHardcap', 3000], ['btcHardcap', 3000]],
    [['coreHardcap', 100000], ['hashHardcap', 50000], ['btcHardcap', 30000]],
])
def test_claim_reward_after_hardcap_update(stake_hub, hard_cap, set_candidate):
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    for h in hard_cap:
        hex_value = padding_left(Web3.to_hex(h[1]), 64)
        stake_hub.updateParam(h[0], hex_value)
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[0], COIN_VALUE)
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE, LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[2], accounts[2], POWER_VALUE)
    delegate_btc_lst_success(accounts[0], BTC_LST_VALUE, BTCLST_LOCK_SCRIPT)
    turn_round(consensuses, round_count=2, tx_fee=TX_FEE)
    _, unclaimed_rewards, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], COIN_VALUE)],
    }, {
        "address": operators[1],
        "btc": [set_delegate(accounts[1], BTC_VALUE, stake_duration=Utils.MONTH)],
    }, {
        "address": operators[2],
        "power": [set_delegate(accounts[2], POWER_VALUE)]
    }
    ], BLOCK_REWARD // 2, btc_lst_stake={
        accounts[0]: set_btc_lst_delegate(BTC_LST_VALUE)},
        state_map={'core_lp': 4},
        reward_cap={
            'coin': hard_cap[0][-1],
            'power': hard_cap[1][-1],
            'btc': hard_cap[2][-1]
        }
    )
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[:3])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def init_hybrid_score_mock():
    STAKE_HUB.initHybridScoreMock()
    set_round_tag(get_current_round())


def move_btc_data(tx_ids):
    BTC_STAKE.moveData(tx_ids)


def old_turn_round(miners: list = None, tx_fee=100, round_count=1):
    if miners is None:
        miners = []
    tx = None
    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[99]})
        tx = CandidateHubMock[0].turnRoundOld()
        chain.sleep(1)
    return tx
