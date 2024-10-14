import brownie
import pytest
from .calc_reward import parse_delegation, set_delegate, set_btc_lst_delegate
from .common import *
from .delegate import *
from .utils import *

BLOCK_REWARD = 0
BTC_VALUE = 2000
TX_FEE = 100
FEE = 0
TOTAL_REWARD = 0
UTXO_FEE = 100
LOCK_TIME = 1736956800
BTC_LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
MIN_INIT_DELEGATE_VALUE = 20000
LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_relayer_register(relay_hub):
    for account in accounts[:3]:
        relay_hub.setRelayerRegister(account.address, True)


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, btc_lst_stake,
                     gov_hub, lst_token):
    global BLOCK_REWARD, FEE, TOTAL_REWARD
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LST_STAKE, BTC_LIGHT_CLIENT, BTC_LST_TOKEN
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    BTC_LIGHT_CLIENT = btc_light_client
    BTC_LST_STAKE = btc_lst_stake
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    BTC_LST_TOKEN = lst_token
    set_block_time_stamp(150, LOCK_TIME)
    btc_lst_stake.updateParam('add', LOCK_SCRIPT, {'from': gov_hub.address})


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate_btc_lst_success(set_candidate, lst_token, internal):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses, round_count=internal)
    tracker = get_tracker(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    claim_stake_and_relay_reward(accounts[0])
    actual_reward = 0
    if internal > 0:
        actual_reward = TOTAL_REWARD * 3 * internal // 2
    assert tracker.delta() == actual_reward


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_redeem_btc_lst_success(set_candidate, lst_token, internal):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round(consensuses, round_count=internal)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == 0
    assert tracker.delta() == 0


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_transfer_btc_lst_success(set_candidate, lst_token, internal):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses, round_count=internal)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    actual_reward = 0
    if internal > 1:
        actual_reward = TOTAL_REWARD * 3 // 2
    assert tracker0.delta() == 0
    assert tracker1.delta() == actual_reward


def test_rewards_before_and_after_transfer(set_candidate, lst_token):
    operators, consensuses = set_candidate
    redeem_amount = BTC_VALUE // 4
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], redeem_amount, REDEEM_SCRIPT)
    transfer_btc_lst_success(accounts[0], redeem_amount, accounts[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 4
    assert tracker1.delta() == 0


def test_partial_redeem_and_transfer(set_candidate, lst_token):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    assert tracker1.delta() == TOTAL_REWARD * 3 * 2 // 2


def test_multiple_currencies_stake_and_claim_reward(set_candidate, stake_hub, lst_token, btc_lst_stake):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE * 2, BTC_LOCK_SCRIPT)
    delegate_power_success(operators[2], accounts[1], 200)
    delegate_coin_success(operators[1], accounts[1], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[2], BTC_VALUE * 2, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
    }, {
        "address": operators[1],
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[1], BTC_VALUE * 2)]
    }, {
        "address": operators[2],
        "power": [set_delegate(accounts[1], 200)],
    }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(BTC_VALUE),
        accounts[2]: set_btc_lst_delegate(BTC_VALUE * 2)})
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]] - FEE
    assert tracker2.delta() == account_rewards[accounts[2]] - FEE


@pytest.mark.parametrize("validator_type", ['refuse', 'unregister', 'active'])
def test_no_reward_for_stake_to_invalid_validator(candidate_hub, validator_set, set_candidate, validator_type):
    operators, consensuses = set_candidate
    expect_reward = 0
    validator_count = 2
    if validator_type == 'refuse':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    else:
        expect_reward = TOTAL_REWARD // 2
        validator_count = 3
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == validator_count
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD + expect_reward


def test_reward_claim_post_validator_reduction(candidate_hub, validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round(consensuses)
    validators = validator_set.getValidators()
    assert len(validators) == 2
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 2 // 2


def test_redeem_stake_on_refused_validator(candidate_hub, validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], TOTAL_REWARD, {accounts[0]: set_btc_lst_delegate(BTC_VALUE)})
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 2


def test_redeem_and_claim_reward_after_transfer(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[2], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[1], BTC_VALUE // 2, REDEEM_SCRIPT)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    _, _, account_rewards, asset_unit_reward = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE)],
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], TOTAL_REWARD, {accounts[1]: set_btc_lst_delegate(BTC_VALUE)})
    assert tracker0.delta() == 0
    assert tracker1.delta() == BTC_VALUE // 2 * asset_unit_reward['btc_lst'] // Utils.BTC_DECIMAL // 2
    redeem_btc_lst_success(accounts[1], BTC_VALUE // 2, REDEEM_SCRIPT)
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[1])
    assert tracker1.delta() == 0


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_transfer_post_multiple_round_reward_claim(validator_set, set_candidate, internal):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=internal)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses, round_count=2)
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[1])
    assert tracker1.delta() == TOTAL_REWARD * 3 // 2


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_redeem_post_multiple_round_reward_claim(validator_set, set_candidate, internal):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=internal)
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    _, _, account_rewards, asset_unit_reward = parse_delegation([{
        "address": operators[0],
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], TOTAL_REWARD, {accounts[0]: set_btc_lst_delegate(BTC_VALUE)})
    remain_btc = BTC_VALUE // 2
    btc_unit_reward = asset_unit_reward['btc_lst']
    if internal == 1:
        actual_reward = remain_btc * btc_unit_reward // Utils.BTC_DECIMAL // 2
    elif internal == 2:
        actual_reward = remain_btc * (btc_unit_reward + btc_unit_reward * 2) // Utils.BTC_DECIMAL // 2
    else:
        actual_reward = 0
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == actual_reward


def test_transfer_and_claim_reward_after_redeem(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    transfer_btc_lst_success(accounts[0], BTC_VALUE // 2, accounts[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker1.delta() == TOTAL_REWARD * 3 // 2


def test_transfer_redeem_then_transfer_again(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[1], BTC_VALUE // 2, REDEEM_SCRIPT)
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[1], BTC_VALUE // 2, accounts[0])
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == TOTAL_REWARD * 3 // 4
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker1.delta() == 0


def test_additional_stake_redeem_then_transfer(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    delegate_btc_lst_success(accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round(consensuses)
    _, _, account_rewards, asset_unit_reward = parse_delegation([{
        "address": operators[0]
    }, {
        "address": operators[1]
    }, {
        "address": operators[2]
    }], TOTAL_REWARD, {accounts[0]: set_btc_lst_delegate(BTC_VALUE * 3)})
    actual_reward = BTC_VALUE * 2 * asset_unit_reward['btc_lst'] // Utils.BTC_DECIMAL // 2
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == actual_reward
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[0])
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    actual_reward = TOTAL_REWARD * 3 // 4
    assert tracker0.delta() == actual_reward


def test_reward_claim_post_multiple_transfers_in_round(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    for i in range(6):
        transfer_btc_lst_success(accounts[i], BTC_VALUE, accounts[i + 1])
    turn_round(consensuses)
    tracker = get_tracker(accounts[6])
    claim_stake_and_relay_reward(accounts[6])
    assert tracker.delta() == 0


def test_new_validator_post_stake_reward_claim(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    new_agent = accounts[8]
    consensus = register_candidate(operator=new_agent)
    operators.append(accounts[8])
    consensuses.append(consensus)
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 4 // 2


def test_stake_in_current_round_with_new_validator(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    new_agent = accounts[8]
    consensus = register_candidate(operator=new_agent)
    operators.append(accounts[8])
    consensuses.append(consensus)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


@pytest.mark.parametrize("percentage", [
    pytest.param(100, id="percentage is 100"),
    pytest.param(500, id="percentage is 500"),
    pytest.param(3000, id="percentage is 3000"),
    pytest.param(8000, id="percentage is 8000")
])
def test_claim_reward_after_percentage_update(btc_agent, set_candidate, percentage):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    btc_agent.setPercentage(percentage)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 3 * percentage // Utils.DENOMINATOR


def test_deduct_relay_fee_after_transfer(set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT, relay=accounts[1])
    turn_round(consensuses)
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2 - FEE
    assert tracker1.delta() == FEE


def test_no_relay_fee_after_btc_lst_stake_and_transfer(set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT, relay=accounts[0])
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == TOTAL_REWARD * 3 // 2


def test_porter_fee_deduction_success_over_multiple_rounds(set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT, relay=accounts[1])
    turn_round(consensuses, round_count=3)
    tracker1 = get_tracker(accounts[1])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker1.delta() == FEE


def test_claim_reward_after_self_transfer(set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[0])
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[0])
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2


@pytest.mark.parametrize("validator_state", ['minor', 'major'])
def test_btc_lst_stake_with_validator_slashed(set_candidate, slash_indicator, validator_state):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    tx0 = None
    if validator_state == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = TOTAL_REWARD * 6 // 2
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        # no rewards for the current round if a major offense occurs
        expect_reward = TOTAL_REWARD * 2
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    delegate_btc_lst_success(accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == expect_reward
    turn_round(consensuses)


@pytest.mark.parametrize("validator_state", ['minor', 'major'])
def test_validator_slashed_during_redeem(set_candidate, slash_indicator, validator_state):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, LOCK_SCRIPT)
    tx0 = None
    expect_reward = 0
    if validator_state == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        # no rewards for the current round if a major offense occurs
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[:2])
    assert tracker0.delta() == expect_reward
    turn_round(consensuses)


@pytest.mark.parametrize("validator_state", ['minor', 'major'])
def test_transfer_with_validator_slashed(set_candidate, slash_indicator, validator_state):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    transfer_btc_lst_success(accounts[0], BTC_VALUE // 2, accounts[1])
    tx0 = None
    if validator_state == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = TOTAL_REWARD * 3 // 2

    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = TOTAL_REWARD
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    transfer_btc_lst_success(accounts[0], BTC_VALUE // 2, accounts[1])
    transfer_btc_lst_success(accounts[1], BTC_VALUE, accounts[2])
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[:3])
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0
    assert tracker2.delta() == expect_reward
    turn_round(consensuses)


def test_contract_stake_and_claim_reward(set_candidate, btc_agent, btc_lst_stake, stake_hub, relay_hub, lst_token):
    operators, consensuses = set_candidate
    turn_round()
    btc_agent.setPercentage(Utils.DENOMINATOR // 2)
    btc_lst_stake = delegateBtcLstProxy.deploy(btc_lst_stake.address, stake_hub.address, lst_token,
                                               {'from': accounts[0]})
    btc_lst_stake.setReceiveState(True)
    accounts[4].transfer(btc_lst_stake.address, Web3.to_wei(1, 'ether'))
    relay_hub.setRelayerRegister(btc_lst_stake.address, True)
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    tx = btc_lst_stake.delegateBtcLst(btc_tx, 1, [], 1, LOCK_SCRIPT)
    assert 'delegated' in tx.events
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(btc_lst_stake)
    btc_lst_stake.setReceiveState(True)
    claim_stake_and_relay_reward([accounts[0], btc_lst_stake])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2 - FEE
    assert tracker1.delta() == FEE
    turn_round(consensuses)


def test_contract_stake_and_redeem(set_candidate, btc_agent, btc_lst_stake, stake_hub, relay_hub, lst_token):
    operators, consensuses = set_candidate
    turn_round()
    btc_lst_stake = delegateBtcLstProxy.deploy(btc_lst_stake.address, stake_hub.address, lst_token.address,
                                               {'from': accounts[0]})
    btc_tx = build_btc_lst_tx(btc_lst_stake.address, BTC_VALUE, LOCK_SCRIPT)
    tx = btc_lst_stake.delegateBtcLst(btc_tx, 1, [], 1, LOCK_SCRIPT)
    btc_agent.setPercentage(Utils.DENOMINATOR // 2)
    assert 'delegated' in tx.events
    turn_round()
    tx = btc_lst_stake.redeemBtcLst(BTC_VALUE // 2, REDEEM_SCRIPT)
    assert 'redeemed' in tx.events
    turn_round(consensuses)
    tx = btc_lst_stake.transferBtcLst(accounts[0].address, BTC_VALUE // 2)
    assert tx.events['transferBtcLstSuccess']
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(btc_lst_stake)
    btc_lst_stake.setReceiveState(True)
    btc_lst_stake.claimReward()
    assert tracker1.delta() == TOTAL_REWARD * 3 // 4 - FEE
    turn_round(consensuses, round_count=2)
    btc_lst_stake.claimReward()
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    assert tracker1.delta() == 0
    turn_round(consensuses)


def test_claim_reward_after_multiple_stakes_and_operations(set_candidate, stake_hub, lst_token, btc_lst_stake):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    for i in range(2):
        delegate_coin_success(operators[0], accounts[i + 1], MIN_INIT_DELEGATE_VALUE)
    delegate_power_success(operators[0], accounts[1], 200)
    tx_id = delegate_btc_success(operators[1], accounts[1], BTC_VALUE * 2, BTC_LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[2], accounts[1], 200)
    delegate_coin_success(operators[1], accounts[2], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[2], BTC_VALUE * 2, LOCK_SCRIPT, relay=accounts[2])
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[1], MIN_INIT_DELEGATE_VALUE)
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    transfer_btc_success(tx_id, operators[2], accounts[1])
    undelegate_coin_success(operators[0], accounts[2], MIN_INIT_DELEGATE_VALUE // 4)
    undelegate_coin_success(operators[1], accounts[2], MIN_INIT_DELEGATE_VALUE)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE),
                 set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE, MIN_INIT_DELEGATE_VALUE // 4)],
        "power": [set_delegate(accounts[1], 200)]
    }, {
        "address": operators[1],
        "coin": [set_delegate(accounts[2], MIN_INIT_DELEGATE_VALUE, MIN_INIT_DELEGATE_VALUE)],
        "btc": [set_delegate(accounts[1], BTC_VALUE * 2, BTC_VALUE * 2)]
    }, {
        "address": operators[2],
        "power": [set_delegate(accounts[1], 200)]
    }], BLOCK_REWARD // 2, {
        accounts[0]: set_btc_lst_delegate(BTC_VALUE, BTC_VALUE // 2),
        accounts[2]: set_btc_lst_delegate(BTC_VALUE * 2)})
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]
    turn_round(consensuses)


def test_claim_reward_after_turnround_failure(set_candidate, candidate_hub, stake_hub, lst_token, btc_lst_stake):
    operators, consensuses = set_candidate
    block_times_tamp = 1723122315
    set_last_round_tag(2, block_times_tamp)
    chain.mine(timestamp=block_times_tamp)
    turn_round()
    candidate_hub.setControlRoundTimeTag(False)
    block_time = block_times_tamp
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    for i in range(2):
        delegate_coin_success(operators[0], accounts[i + 1], MIN_INIT_DELEGATE_VALUE)
    delegate_power_success(operators[0], accounts[1], 200)
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE * 2, BTC_LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[2], accounts[1], 200)
    delegate_coin_success(operators[1], accounts[2], MIN_INIT_DELEGATE_VALUE)
    delegate_btc_lst_success(accounts[2], BTC_VALUE * 2, LOCK_SCRIPT, relay=accounts[2])
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    candidate_hub.setTurnroundFailed(True)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 2)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    candidate_hub.setTurnroundFailed(False)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 3)
    turn_round(consensuses)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 4)
    turn_round(consensuses)


def test_retry_turnround_after_failure(set_candidate, candidate_hub, stake_hub, lst_token, btc_lst_stake):
    operators, consensuses = set_candidate
    block_times_tamp = 1723122315
    set_last_round_tag(2, block_times_tamp)
    chain.mine(timestamp=block_times_tamp)
    turn_round()
    candidate_hub.setControlRoundTimeTag(False)
    block_time = block_times_tamp
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    candidate_hub.setTurnroundFailed(True)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 2)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    candidate_hub.setTurnroundFailed(False)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 3)
    turn_round(consensuses)
    claim_stake_and_relay_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 6 // 2


def __get_redeem_requests(index):
    redeem_request = BTC_LST_STAKE.redeemRequests(index)
    return redeem_request


def __get_btc_tx_map(tx_id):
    bt = BTC_LST_STAKE.btcTxMap(tx_id)
    return bt


def __check_user_stake_info(delegator, result: dict):
    user_info = BTC_LST_STAKE.userStakeInfo(delegator)
    for r in result:
        assert result[r] == user_info[r]


def __check_redeem_requests(redeem_index, result: dict):
    redeem_request = BTC_LST_STAKE.redeemRequests(redeem_index)
    for i in result:
        assert redeem_request[i] == result[i]
