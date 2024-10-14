import pytest
import brownie
import rlp
from brownie import *
from .delegate import delegate_btc_success, delegate_coin_success, delegate_btc_lst_success
from .utils import *
from .common import register_candidate, turn_round, get_current_round, stake_hub_claim_reward
from collections import OrderedDict
from .delegate import *

MIN_INIT_DELEGATE_VALUE = 0
CANDIDATE_REGISTER_MARGIN = 0
candidate_hub_instance = None
core_agent_instance = None
btc_light_client_instance = None
required_coin_deposit = 0
TX_FEE = Web3.to_wei(1, 'ether')
# the tx fee is 1 ether
actual_block_reward = 0
COIN_REWARD = 0
BLOCK_REWARD = 0
stake_manager = StakeManager()
round_reward_manager = RoundRewardManager()


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


@pytest.fixture(scope="module", autouse=True)
def set_up(min_init_delegate_value, core_agent, candidate_hub, btc_lst_stake, btc_agent, hash_power_agent,
           btc_light_client, validator_set, stake_hub, btc_stake, system_reward, gov_hub):
    global MIN_INIT_DELEGATE_VALUE
    global CANDIDATE_REGISTER_MARGIN
    global candidate_hub_instance
    global core_agent_instance
    global required_coin_deposit
    global btc_light_client_instance
    global actual_block_reward
    global COIN_REWARD
    global BLOCK_REWARD
    global BTC_STAKE, STAKE_HUB, BTC_AGENT, CORE_AGENT, BTC_LST_STAKE, HASH_POWER_AGENT, TOTAL_REWARD, GOV_HUB
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    BTC_AGENT = btc_agent
    CORE_AGENT = core_agent
    BTC_LST_STAKE = btc_lst_stake
    HASH_POWER_AGENT = hash_power_agent
    GOV_HUB = gov_hub
    btc_agent.setAssetWeight(1)
    candidate_hub_instance = candidate_hub
    core_agent_instance = core_agent
    btc_light_client_instance = btc_light_client
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value
    CANDIDATE_REGISTER_MARGIN = candidate_hub.requiredMargin()
    required_coin_deposit = core_agent.requiredCoinDeposit()
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    actual_block_reward = total_block_reward * (100 - block_reward_incentive_percent) // 100
    tx_fee = 100
    BLOCK_REWARD = (block_reward + tx_fee) * ((100 - block_reward_incentive_percent) / 100)
    total_reward = BLOCK_REWARD // 2
    COIN_REWARD = total_reward * HardCap.CORE_HARD_CAP // HardCap.SUM_HARD_CAP
    STAKE_HUB = stake_hub
    system_reward.setOperator(stake_hub.address)
    btc_agent.setAssetWeight(1)


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, system_reward):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))


def test_reinit(pledge_agent):
    with brownie.reverts("the contract already init"):
        pledge_agent.init()


def test_validators_and_rewards_length_mismatch_revert(validator_set):
    validators = [accounts[1], accounts[2]]
    reward_list = [1000]
    value_sum = sum(reward_list)
    with brownie.reverts('the length of validators and rewardList should be equal'):
        validator_set.addRoundRewardMock(validators, reward_list, 100,
                                         {'from': accounts[0], 'value': value_sum})


def test_only_validator_can_call_add_round_reward(stake_hub):
    validators = [accounts[1], accounts[2]]
    reward_list = [1000, 1000]
    value_sum = sum(reward_list)
    with brownie.reverts('the msg sender must be validatorSet contract'):
        stake_hub.addRoundReward(validators, reward_list, 100,
                                 {'from': accounts[0], 'value': value_sum})


def test_add_round_reward_success(validator_set, core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    reward_list = [1000, 2000]
    value_sum = sum(reward_list)
    power_value = 5
    core_value = 100
    btc_value = 10
    for validator in validators:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
        btc_stake.setCandidateMap(validator, btc_value, btc_value, [])
    candidate_hub.getScoreMock(validators, round_tag)
    tx = validator_set.addRoundRewardMock(validators, reward_list, round_tag,
                                          {'from': accounts[0], 'value': value_sum})
    for index, round_reward in enumerate(tx.events['roundReward']):
        amounts = []
        for v1, v2 in enumerate(validators):
            scores = stake_hub.getCandidateScores(v2)
            reward = reward_list[v1] * scores[index + 1] // scores[0]
            amounts.append(reward)
        assert round_reward['amount'] == amounts


def test_no_stake_on_validator(validator_set, core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    reward_list = [1000, 2000]
    value_sum = sum(reward_list)
    candidate_hub.getScoreMock(validators, round_tag)
    tx = validator_set.addRoundRewardMock(validators, reward_list, round_tag,
                                          {'from': accounts[0], 'value': value_sum})
    expect_event(tx, 'receiveDeposit', {
        'from': stake_hub.address,
        'amount': value_sum
    })


def test_reward_without_stake(validator_set, core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    reward_list = [0, 0]
    value_sum = sum(reward_list)
    power_value = 5
    core_value = 100
    btc_value = 10
    for validator in validators:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
        btc_stake.setCandidateMap(validator, btc_value, btc_value, [])
    candidate_hub.getScoreMock(validators, round_tag)
    tx = validator_set.addRoundRewardMock(validators, reward_list, round_tag,
                                          {'from': accounts[0], 'value': value_sum})
    for round_reward in tx.events['roundReward']:
        assert round_reward['amount'] == [0, 0]


def test_only_candidate_can_call(validator_set, stake_hub):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    with brownie.reverts('the msg sender must be candidate contract'):
        stake_hub.getHybridScore(validators, round_tag)


@pytest.mark.parametrize("test", [
    pytest.param({'add_core': 10e18}, id="core"),
    pytest.param({'add_hash': 100}, id="hash"),
    pytest.param({'add_btc': 10e8}, id="btc"),
    pytest.param({'add_core': 1e18, 'add_hash': 200}, id="core & hash"),
    pytest.param({'add_core': 1e18, 'add_btc': 100e8}, id="core & btc"),
    pytest.param({'add_hash': 200, 'add_btc': 100e8}, id="hash & btc"),
    pytest.param({'add_core': 10e8, 'add_hash': 200, 'add_btc': 1000e8}, id="core & hash & btc"),
    pytest.param({'add_core': 1e8, 'add_hash': 100, 'add_btc': 10e8}, id="core & hash & btc"),
    pytest.param({'add_core': 0, 'add_hash': 0, 'add_btc': 0}, id="core & hash & btc"),
])
def test_get_hybrid_score_success(core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub,
                                  hash_power_agent, btc_agent, test):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    core_value = test.get('add_core', 0)
    power_value = test.get('add_hash', 0)
    btc_value = test.get('add_btc', 0)
    values = [core_value, power_value, btc_value]
    for validator in validators[:1]:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
        btc_stake.setCandidateMap(validator, btc_value, btc_value, [])
    tx = candidate_hub.getScoreMock(validators, round_tag)
    scores = tx.return_value
    hard_cap = [6000, 2000, 4000]
    factors = []
    factor0 = 0
    for index, h in enumerate(hard_cap):
        factor = 1
        if index == 0:
            factor0 = 1
        if index > 0 and values[0] != 0 and values[index] != 0:
            factor = (factor0 * core_value) * h // hard_cap[0] // values[index]
        factors.append(factor)
    assets = [core_agent, hash_power_agent, btc_agent]
    for index, asset in enumerate(assets):
        factor = stake_hub.stateMap(asset)
        assert factor == [values[index], int(factors[index])]
    candidate_scores = stake_hub.getCandidateScores(validators[0])
    assert candidate_scores[0] == sum(candidate_scores[1:4])
    for index, score in enumerate(candidate_scores[1:]):
        assert score == values[index] * factors[index]
    assert scores == [candidate_scores[0], 0]


def test_calculate_factor_success(core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub,
                                  hash_power_agent, btc_agent):
    round_tag = 100
    validators = [accounts[1]]
    core_value = 100e18
    power_value = 200
    for validator in validators[:1]:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
    candidate_hub.getScoreMock(validators, round_tag)
    candidate_scores = stake_hub.getCandidateScoresMap(validators[0])
    assert candidate_scores[0] == sum(candidate_scores[1:4])
    assert candidate_scores[1] - candidate_scores[2] * 3 < 1000


def test_two_rounds_score_calculation_success(core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub,
                                              hash_power_agent, btc_agent):
    round_tag = 100
    validators = [accounts[1]]
    core_value = 100e18
    power_value = 200
    btc_value = 200
    for validator in validators[:1]:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
    candidate_hub.getScoreMock(validators, round_tag)
    candidate_scores = stake_hub.getCandidateScoresMap(validators[0])
    assert candidate_scores[-1] == 0
    btc_stake.setCandidateMap(validators[0], btc_value, btc_value, [])
    candidate_hub.getScoreMock(validators, round_tag)
    candidate_scores = stake_hub.getCandidateScoresMap(validators[0])
    assert candidate_scores[0] == sum(candidate_scores[1:4])
    assert candidate_scores[-1] != 0


def test_validators_score_calculation_success(core_agent, btc_light_client, btc_stake, candidate_hub, stake_hub,
                                              hash_power_agent, btc_agent):
    round_tag = 100
    validators = [accounts[1], accounts[2]]
    core_value = 100e18
    power_value = 200
    btc_value = 200
    for validator in validators:
        core_agent.setCandidateMapAmount(validator, core_value, core_value, 0)
        btc_light_client.setMiners(round_tag - 7, validator, [accounts[0]] * power_value)
        btc_stake.setCandidateMap(validators[0], btc_value, btc_value, [])
    tx = candidate_hub.getScoreMock(validators, round_tag)
    scores = tx.return_value
    actual_scores = []
    for v in validators:
        candidate_scores = stake_hub.getCandidateScoresMap(v)
        actual_scores.append(candidate_scores[0])
    assert scores == actual_scores


def test_only_candidate_can_call_set_new_round(stake_hub):
    with brownie.reverts("the msg sender must be candidate contract"):
        stake_hub.setNewRound(accounts[:2], 100)


def test_set_new_round_success(stake_hub, core_agent, btc_lst_stake, btc_stake):
    round_tag = 100
    update_system_contract_address(stake_hub, candidate_hub=accounts[0])
    stake_hub.setNewRound(accounts[:2], round_tag)
    assert core_agent.roundTag() == btc_lst_stake.roundTag() == btc_stake.roundTag() == round_tag


def __mock_stake_hub_reward():
    accounts[3].transfer(STAKE_HUB, Web3.to_wei(1, 'ether'))


@pytest.mark.parametrize("claim", ['btc', 'lst_btc'])
@pytest.mark.parametrize("tests", [
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 0, 'actual_bonus': 90000},
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 2000, 'actual_bonus': 92000},
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 10000, 'actual_bonus': 0},
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 12000, 'actual_bonus': 2000},
    {'btc_reward': 10000, 'unclaimed_reward': 2000, 'reward_pool': 0, 'actual_bonus': 72000},
    {'btc_reward': 10000, 'unclaimed_reward': 5000, 'reward_pool': 0, 'actual_bonus': 45000},
    {'btc_reward': 10000, 'unclaimed_reward': 10000, 'reward_pool': 0, 'actual_bonus': 0},
    {'btc_reward': 10000, 'unclaimed_reward': 12000, 'reward_pool': 0, 'actual_bonus': 2000},
    {'btc_reward': 10000, 'unclaimed_reward': 9000, 'reward_pool': 12000, 'actual_bonus': 11000},
    {'btc_reward': 10000, 'unclaimed_reward': 12000, 'reward_pool': 9000, 'actual_bonus': 11000},
    {'btc_reward': 10000, 'unclaimed_reward': 10000, 'reward_pool': 1000, 'actual_bonus': 1000},
    {'btc_reward': 10000, 'unclaimed_reward': 1000, 'reward_pool': 10000, 'actual_bonus': 1000},
    {'btc_reward': 10000, 'unclaimed_reward': 4000, 'reward_pool': 4000, 'actual_bonus': 58000},
    {'btc_reward': 10000, 'unclaimed_reward': 5000, 'reward_pool': 5000, 'actual_bonus': 0},
    {'btc_reward': 10000, 'unclaimed_reward': 15000, 'reward_pool': 15000, 'actual_bonus': 20000}
])
def test_btc_claim_bonus_reward(stake_hub, btc_agent, tests, claim):
    stake_manager.set_lp_rates([[0, 20000]])
    btc_agent.setPercentage(20000)
    stake_manager.set_is_stake_hub_active(True)
    btc_reward = tests['btc_reward']
    unclaimed_reward = tests['unclaimed_reward']
    reward_pool = tests['reward_pool']
    stake_hub.setSurplus(reward_pool)
    float_reward = btc_reward - unclaimed_reward
    __mock_stake_hub_reward()
    if claim == 'btc':
        round_reward_manager.mock_btc_reward_map(accounts[0], btc_reward, unclaimed_reward, MIN_INIT_DELEGATE_VALUE)
    else:
        round_reward_manager.mock_btc_reward_map(accounts[0], 0, unclaimed_reward, MIN_INIT_DELEGATE_VALUE)
        round_reward_manager.mock_btc_lst_reward_map(accounts[0], btc_reward, MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    tx = stake_hub.claimReward()
    if float_reward > reward_pool:
        reward_pool += float_reward * 10
    reward_pool -= float_reward
    assert tracker.delta() == btc_reward * 2
    assert stake_hub.surplus() == reward_pool
    assert reward_pool == tests['actual_bonus']


@pytest.mark.parametrize("claim", ['btc', 'lst_btc'])
@pytest.mark.parametrize("tests", [
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 0, 'actual_bonus': 5000},
    {'btc_reward': 10000, 'unclaimed_reward': 3000, 'reward_pool': 0, 'actual_bonus': 8000},
    {'btc_reward': 10000, 'unclaimed_reward': 6000, 'reward_pool': 0, 'actual_bonus': 11000},
    {'btc_reward': 10000, 'unclaimed_reward': 0, 'reward_pool': 2000, 'actual_bonus': 7000},
    {'btc_reward': 10000, 'unclaimed_reward': 1000, 'reward_pool': 2000, 'actual_bonus': 8000},
    {'btc_reward': 0, 'unclaimed_reward': 1000, 'reward_pool': 2000, 'actual_bonus': 3000}
])
def test_btc_no_bonus(stake_hub, btc_agent, tests, claim):
    stake_manager.set_lp_rates([[0, 5000]])
    btc_agent.setPercentage(5000)
    stake_manager.set_is_stake_hub_active(True)
    btc_reward = tests['btc_reward']
    actual_reward = btc_reward // 2
    unclaimed_reward = tests['unclaimed_reward']
    reward_pool = tests['reward_pool']
    stake_hub.setSurplus(reward_pool)
    reward_pool += actual_reward
    reward_pool += unclaimed_reward
    __mock_stake_hub_reward()
    if claim == 'btc':
        round_reward_manager.mock_btc_reward_map(accounts[0], btc_reward, unclaimed_reward, MIN_INIT_DELEGATE_VALUE)
    else:
        round_reward_manager.mock_btc_reward_map(accounts[0], 0, unclaimed_reward, MIN_INIT_DELEGATE_VALUE)
        round_reward_manager.mock_btc_lst_reward_map(accounts[0], btc_reward, MIN_INIT_DELEGATE_VALUE)
    tracker = get_tracker(accounts[0])
    tx = stake_hub.claimReward()
    assert tracker.delta() == actual_reward
    assert stake_hub.surplus() == reward_pool
    assert reward_pool == tests['actual_bonus']


@pytest.mark.parametrize("tests", [
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 0, 'btc_lst_percentage': 8000,
     'btc_percentage': 8000, 'surplus': 3000, 'expect_reward': 16000, 'expect_surplus': 7000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 0, 'btc_lst_percentage': 12000,
     'btc_percentage': 6000, 'surplus': 3000, 'expect_reward': 18000, 'expect_surplus': 5000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 0, 'btc_lst_percentage': 12000,
     'btc_percentage': 10000, 'surplus': 3000, 'expect_reward': 22000, 'expect_surplus': 1000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 3000, 'btc_lst_percentage': 15000,
     'btc_percentage': 15000, 'surplus': 2000, 'expect_reward': 30000, 'expect_surplus': 65000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 2000, 'btc_lst_percentage': 10000,
     'btc_percentage': 12000, 'surplus': 0, 'expect_reward': 22000, 'expect_surplus': 0},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 2000, 'btc_lst_percentage': 5000,
     'btc_percentage': 5000, 'surplus': 0, 'expect_reward': 10000, 'expect_surplus': 12000}
])
def test_claim_reward_update_surplus(stake_hub, btc_agent, btc_lst_stake, tests):
    __mock_stake_hub_reward()
    stake_hub.setSurplus(tests['surplus'])
    btc_reward = tests['btc_reward']
    duration_unclaimed = tests['duration_unclaimed']
    btc_lst_percentage = tests['btc_lst_percentage']
    btc_percentage = tests['btc_percentage']
    stake_manager.set_lp_rates([[0, btc_percentage]])
    btc_agent.setPercentage(btc_lst_percentage)
    stake_manager.set_is_stake_hub_active(True)
    turn_round()
    actual_btc_reward = btc_reward * btc_percentage // Utils.DENOMINATOR
    btc_lst_reward = tests['btc_lst_reward']
    actual_btc_lst_reward = btc_lst_reward * btc_lst_percentage // Utils.DENOMINATOR
    round_reward_manager.mock_btc_reward_map(accounts[0], btc_reward, duration_unclaimed, 100)
    round_reward_manager.mock_btc_lst_reward_map(accounts[0], btc_lst_reward, 0)
    actual_reward = actual_btc_reward + actual_btc_lst_reward
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert actual_reward == tests['expect_reward']
    assert stake_hub.surplus() == tests['expect_surplus']
    assert tracker.delta() == actual_reward


def test_system_reward_insufficient_balance(stake_hub):
    stake_manager.set_lp_rates([[0, 30000]])
    stake_manager.set_is_stake_hub_active(True)
    btc_reward = 100000e18
    accounts[3].transfer(STAKE_HUB, Web3.to_wei(100000, 'ether'))
    round_reward_manager.mock_btc_reward_map(accounts[0], btc_reward, 0, 100)
    # revert: Address: insufficient balance
    with brownie.reverts("Address: insufficient balance"):
        stake_hub.claimReward()


def test_only_pledge_agent_can_call(stake_hub):
    with brownie.reverts("the sender must be pledge agent contract"):
        stake_hub.proxyClaimReward(accounts[0])


def test_proxy_claim_reward_success(stake_hub, btc_agent, pledge_agent, set_candidate):
    fee = 0
    delegate_amount = 1000000
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[2], delegate_amount)
    script, pay_address, timestamp = random_btc_lock_script()
    delegate_btc_success(operators[1], accounts[2], 100, script, timestamp, relay=accounts[2])
    btc_lst_scirpt = random_btc_lst_lock_script()
    stake_manager.add_wallet(btc_lst_scirpt)
    delegate_btc_lst_success(accounts[2], 200, btc_lst_scirpt, relay=accounts[2], percentage=Utils.DENOMINATOR)
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    update_system_contract_address(stake_hub, pledge_agent=accounts[0])
    stake_hub.proxyClaimReward(accounts[2])
    assert tracker.delta() == BLOCK_REWARD // 2 * 3 - 1 - fee * 2


def test_calculate_reward_success(stake_hub, btc_agent, core_agent, btc_lst_stake, btc_stake, hash_power_agent,
                                  set_candidate):
    accounts[3].transfer(stake_hub, Web3.to_wei(1, 'ether'))
    reward = 10000
    actual_rewards = [reward, reward, reward]
    core_agent.setCoreRewardMap(accounts[0], reward, 0)
    hash_power_agent.setPowerRewardMap(accounts[0], reward, 0)
    btc_lst_stake.setBtcLstRewardMap(accounts[0], reward, 0)
    round_reward_manager.mock_btc_reward_map(accounts[0], reward, 0, MIN_INIT_DELEGATE_VALUE)
    btc_agent.setIsActive(True)
    stake_manager.set_lp_rates([[0, 5000]])
    btc_agent.setPercentage(5000)
    stake_hub.setOperators(accounts[3], True)
    rewards = stake_hub.calculateRewardMock(accounts[0]).return_value
    assert rewards == actual_rewards
    assert stake_hub.surplus() == reward


@pytest.mark.parametrize("tests", [
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 0, 'btc_lst_percentage': 8000,
     'btc_percentage': 8000, 'surplus': 0, 'expect_reward': 16000, 'expect_surplus': 4000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 1000, 'btc_lst_percentage': 8000,
     'btc_percentage': 8000, 'surplus': 0, 'expect_reward': 16000, 'expect_surplus': 5000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 0, 'btc_lst_percentage': 12000,
     'btc_percentage': 12000, 'surplus': 0, 'expect_reward': 24000, 'expect_surplus': 36000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 1000, 'btc_lst_percentage': 12000,
     'btc_percentage': 12000, 'surplus': 2000, 'expect_reward': 24000, 'expect_surplus': 29000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 2000, 'btc_lst_percentage': 11000,
     'btc_percentage': 12000, 'surplus': 2000, 'expect_reward': 23000, 'expect_surplus': 1000},
    {'btc_reward': 10000, 'btc_lst_reward': 10000, 'duration_unclaimed': 1000, 'btc_lst_percentage': 5000,
     'btc_percentage': 12000, 'surplus': 2000, 'expect_reward': 17000, 'expect_surplus': 6000},
])
def test_calculate_reward_update_surplus(stake_hub, btc_agent, btc_lst_stake, tests):
    stake_hub.setSurplus(tests['surplus'])
    btc_reward = tests['btc_reward']
    duration_unclaimed = tests['duration_unclaimed']
    btc_lst_percentage = tests['btc_lst_percentage']
    btc_percentage = tests['btc_percentage']
    stake_manager.set_lp_rates([[0, btc_percentage]])
    btc_agent.setPercentage(btc_lst_percentage)
    stake_manager.set_is_stake_hub_active(True)
    turn_round()
    actual_btc_reward = btc_reward * btc_percentage // Utils.DENOMINATOR
    btc_lst_reward = tests['btc_lst_reward']
    actual_btc_lst_reward = btc_lst_reward * btc_lst_percentage // Utils.DENOMINATOR
    round_reward_manager.mock_btc_reward_map(accounts[0], btc_reward, duration_unclaimed, 100)
    round_reward_manager.mock_btc_lst_reward_map(accounts[0], btc_lst_reward, 0)
    actual_reward = actual_btc_reward + actual_btc_lst_reward
    reward = stake_hub.calculateRewardMock(accounts[0]).return_value
    assert actual_reward == tests['expect_reward']
    assert stake_hub.surplus() == tests['expect_surplus']
    assert reward == [0, 0, actual_reward]


@pytest.mark.parametrize("lp_rates", [
    [(0, 1000), (1000, 5000), (30000, 10000)],
    [(0, 1000), (1000, 2000), (2000, 5000)],
    [(0, 5000), (12000, 10000), (20000, 12000)]
])
def test_claim_rewards_multiple_grades(stake_hub, core_agent, btc_lst_stake, hash_power_agent, btc_agent, lp_rates):
    accounts[3].transfer(stake_hub, Web3.to_wei(1, 'ether'))
    reward = 10000
    actual_rewards = [reward, reward, reward // 2]
    core_agent.setCoreRewardMap(accounts[0], reward, 10000)
    btc_lst_stake.setBtcLstRewardMap(accounts[0], reward, 1)
    hash_power_agent.setPowerRewardMap(accounts[0], reward, 10)
    btc_agent.setIsActive(True)
    btc_agent.setPercentage(5000)
    for lp in lp_rates:
        btc_agent.setLpRates(lp[0], lp[1])
    rewards = stake_hub.calculateRewardMock(accounts[0]).return_value
    assert rewards == actual_rewards


def test_get_assets_success(stake_hub, core_agent, hash_power_agent, btc_agent):
    assets = stake_hub.getAssets()
    assert assets == [['CORE', core_agent.address, 6000], ['HASHPOWER', hash_power_agent.address, 2000],
                      ['BTC', btc_agent.address, 4000]]


def test_only_govhub_can_call(stake_hub):
    grades_encode = rlp.encode([])
    with brownie.reverts("the msg sender must be governance contract"):
        stake_hub.updateParam('grades', grades_encode)


@pytest.mark.parametrize("hard_cap", [
    [['coreHardcap', 2000], ['hashHardcap', 9000], ['btcHardcap', 10000]],
    [['coreHardcap', 1000], ['hashHardcap', 2000], ['btcHardcap', 8000]],
    [['coreHardcap', 100000], ['hashHardcap', 20000], ['btcHardcap', 30000]],
    [['coreHardcap', 10000], ['hashHardcap', 100000], ['btcHardcap', 30000]],
    [['coreHardcap', 10000], ['hashHardcap', 10000], ['btcHardcap', 100000]]
])
def test_update_hard_cap_success(stake_hub, hard_cap):
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    for h in hard_cap:
        hex_value = padding_left(Web3.to_hex(h[1]), 64)
        stake_hub.updateParam(h[0], hex_value)
    for i in range(3):
        assert stake_hub.assets(i)['hardcap'] == hard_cap[i][-1]


@pytest.mark.parametrize("hard_cap", [
    ['coreHardcap', 100001],
    ['hashHardcap', 100001],
    ['btcHardcap', 100001],
    ['btcHardcap', 200002],
])
def test_update_hard_cap_failed(stake_hub, hard_cap):
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(hard_cap[1]), 64)
    with brownie.reverts(f"OutOfBounds: {hard_cap[0]}, {hard_cap[1]}, 1, 100000"):
        stake_hub.updateParam(hard_cap[0], hex_value)


def test_update_param_nonexistent_governance_param_reverts(stake_hub):
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    with brownie.reverts(f"UnsupportedGovParam: error"):
        hex_value = padding_left(Web3.to_hex(100), 64)
        stake_hub.updateParam('error', hex_value)


def test_stake_hup_add_round_reward(stake_hub, validator_set, candidate_hub, core_agent, btc_light_client, btc_stake):
    turn_round()
    register_candidate(operator=accounts[1])
    register_candidate(operator=accounts[2])

    tests = [
        {'status': 'success', 'validators': [], 'reward_list': [], 'round': 100,
         'expect_round_reward': [OrderedDict([('round', 100), ('validator', ()), ('amount', ())]),
                                 OrderedDict([('round', 100), ('validator', ()), ('amount', ())]),
                                 OrderedDict([('round', 100), ('validator', ()), ('amount', ())])]},

        {'status': 'success', 'validators': [accounts[1]], 'reward_list': [100], 'round': 100,
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (0,))]),
                                 OrderedDict([('round', 100), ('amount', (0,))]),
                                 OrderedDict([('round', 100), ('amount', (0,))])]},

        {'status': 'success', 'validators': [accounts[1], accounts[2]], 'reward_list': [100, 200], 'round': 100,
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (0, 0))]),
                                 OrderedDict([('round', 100), ('amount', (0, 0))]),
                                 OrderedDict([('round', 100), ('amount', (0, 0))])]},

        {'status': 'success', 'validators': [accounts[1]], 'reward_list': [100], 'round': 100,
         'add_core': [(accounts[1], 100)],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (100,))]),
                                 OrderedDict([('round', 100), ('amount', (0,))]),
                                 OrderedDict([('round', 100), ('amount', (0,))])]},

        {'status': 'success', 'validators': [accounts[1], accounts[2]], 'reward_list': [100, 100], 'round': 100,
         'add_core': [(accounts[1], 100), (accounts[2], 100)],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (100, 100))]),
                                 OrderedDict([('round', 100), ('amount', (0, 0))]),
                                 OrderedDict([('round', 100), ('amount', (0, 0))])]},

        {'status': 'success', 'validators': [accounts[1]], 'reward_list': [100], 'round': 100,
         'add_core': [(accounts[1], 100)], 'add_pow': [(accounts[1], [accounts[0]])],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (75,))]),
                                 OrderedDict([('round', 100), ('amount', (24,))]),
                                 OrderedDict([('round', 100), ('amount', (0,))])]},

        {'status': 'success', 'validators': [accounts[1], accounts[1]], 'reward_list': [100, 100], 'round': 100,
         'add_core': [(accounts[1], 100), (accounts[2], 100)], 'add_pow': [(accounts[1], [accounts[0]])],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (75, 75))]),
                                 OrderedDict([('round', 100), ('amount', (24, 24))]),
                                 OrderedDict([('round', 100), ('amount', (0, 0))])]},

        {'status': 'success', 'validators': [accounts[1]], 'reward_list': [100], 'round': 100,
         'add_core': [(accounts[1], 100)], 'add_pow': [(accounts[1], [accounts[0]])],
         'add_btc': [(accounts[1], 1, 1, [])],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (50,))]),
                                 OrderedDict([('round', 100), ('amount', (16,))]),
                                 OrderedDict([('round', 100), ('amount', (33,))])]},

        {'status': 'success', 'validators': [accounts[1], accounts[1]], 'reward_list': [100, 100], 'round': 100,
         'add_core': [(accounts[1], 100), (accounts[2], 100)], 'add_pow': [(accounts[1], [accounts[0]])],
         'add_btc': [(accounts[1], 1, 1, []), (accounts[2], 1, 1, [])],
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (50, 50))]),
                                 OrderedDict([('round', 100), ('amount', (16, 16))]),
                                 OrderedDict([('round', 100), ('amount', (33, 33))])]},

        {'status': 'success', 'validators': [accounts[1], accounts[1]], 'reward_list': [100, 100], 'round': 100,
         'add_core': [(accounts[1], 100), (accounts[2], 100)], 'add_pow': [(accounts[1], [accounts[0]])],
         'add_btc': [(accounts[1], 1, 1, []), (accounts[2], 1, 1, [])], 'unclaimed_reward': 10,
         'expect_round_reward': [OrderedDict([('round', 100), ('amount', (50, 50))]),
                                 OrderedDict([('round', 100), ('amount', (16, 16))]),
                                 OrderedDict([('round', 100), ('amount', (33, 33))])]},

        {'status': 'failed', 'err': 'the length of validators and rewardList should be equal',
         'validators': [accounts[1], accounts[2]], 'reward_list': [100], 'round': 100, 'expect_round_reward': []},
    ]

    for test in tests:
        print(f'case{tests.index(test)}:', test)
        value_sum = 0
        for v in test['reward_list']:
            value_sum += v
        if 'add_core' in test:
            for validator, v in test['add_core']:
                core_agent.setCandidateMapAmount(validator, v, v, 0)
        if 'add_pow' in test:
            for v1, v2 in test['add_pow']:
                btc_light_client.setMiners(test['round'] - 7, v1, v2)
        if 'add_btc' in test:
            for validator, v1, v2, arr in test['add_btc']:
                btc_stake.setCandidateMap(validator, v1, v2, arr)
        if 'unclaimed_reward' in test:
            stake_hub.setSurplus(test['unclaimed_reward'])
        tx = candidate_hub.getScoreMock(test['validators'], test['round'])
        if test['status'] == 'success':
            tx = validator_set.addRoundRewardMock(test['validators'], test['reward_list'], test['round'],
                                                  {'from': accounts[0], 'value': value_sum})
            print(tx.events['roundReward'])
            for i in range(len(test['expect_round_reward'])):
                expect_event(tx, 'roundReward', test['expect_round_reward'][i], i)
        else:
            with brownie.reverts(test['err']):
                validator_set.addRoundRewardMock(test['validators'], test['reward_list'], test['round'],
                                                 {'from': accounts[0], 'value': value_sum})


def test_stake_hup_get_hybrid_score(stake_hub, validator_set, candidate_hub, core_agent, btc_light_client, btc_stake):
    turn_round()
    register_candidate(operator=accounts[1])
    register_candidate(operator=accounts[2])

    tests = [
        {'status': 'success', 'validators': [], 'round': 100, 'expect_scores': ()},
        {'status': 'success', 'validators': [accounts[1]], 'round': 100, 'expect_scores': [(0, 0, 0, 0)]},
        {'status': 'success', 'validators': [accounts[1]], 'round': 100, 'add_core': [(accounts[1], 100)],
         'expect_scores': [(100, 100, 0, 0)]},
        {'status': 'success', 'validators': [accounts[1]], 'round': 100, 'add_core': [(accounts[1], 100)],
         'add_pow': [(accounts[1], [accounts[0]])], 'expect_scores': [(133, 100, 33, 0)]},
        {'status': 'success', 'validators': [accounts[1]], 'round': 100, 'add_core': [(accounts[1], 100)],
         'add_pow': [(accounts[1], [accounts[0]])], 'add_btc': [(accounts[1], 1, 1, [])],
         'expect_scores': [(199, 100, 33, 66)]},
        {'status': 'success', 'validators': [accounts[1], accounts[2]], 'round': 100,
         'add_core': [(accounts[1], 100), (accounts[2], 200)],
         'add_pow': [(accounts[1], [accounts[0]]), (accounts[2], [accounts[0]])],
         'add_btc': [(accounts[1], 1, 1, []), (accounts[2], 1, 1, [])],
         'expect_scores': [(250, 100, 50, 100), (350, 200, 50, 100)]}
    ]

    for test in tests:
        print(f'case{tests.index(test)}:', test)
        if 'add_core' in test:
            for validator, v in test['add_core']:
                core_agent.setCandidateMapAmount(validator, v, v, 0)
        if 'add_pow' in test:
            for v1, v2 in test['add_pow']:
                btc_light_client.setMiners(test['round'] - 7, v1, v2)
        if 'add_btc' in test:
            for validator, v1, v2, arr in test['add_btc']:
                btc_stake.setCandidateMap(validator, v1, v2, arr)
        if test['status'] == 'success':
            tx = candidate_hub.getScoreMock(test['validators'], test['round'])
            for validator, expect_score in zip(test['validators'], test['expect_scores']):
                assert stake_hub.getCandidateScores(validator) == expect_score


def test_stake_hup_calculate_reward(stake_hub, btc_agent, validator_set, candidate_hub, core_agent, btc_light_client,
                                    btc_stake):
    turn_round()
    register_candidate(operator=accounts[1])
    register_candidate(operator=accounts[2])

    tests = [
        {'status': 'success', 'delegator': accounts[1], 'expect_rewards': (0, 0, 0), 'expect_debt_amount': 0},
        {'status': 'success', 'delegator': accounts[1], 'add_core': [(accounts[1], 100, 0)],
         'expect_rewards': (100, 0, 0), 'expect_debt_amount': 0},
        {'status': 'success', 'delegator': accounts[1], 'add_core': [(accounts[1], 10000, 0)],
         'add_btc': [(accounts[1], 10000, 0)], 'expect_rewards': (10000, 0, 10000), 'expect_debt_amount': 0},
        {'status': 'success', 'delegator': accounts[1], 'add_core': [(accounts[1], 10000, 10000)],
         'add_btc': [(accounts[1], 10000, 1)], 'set_grades': (1000, 5000, 4000, 7000, 5000, 8000, 10000, 10000),
         'expect_rewards': (10000, 0, 10000), 'expect_debt_amount': 0},
        {'status': 'success', 'delegator': accounts[1], 'add_core': [(accounts[1], 10000, 5000)],
         'add_btc': [(accounts[1], 20000, 1)], 'set_grades': (1000, 5000, 4000, 7000, 5000, 8000, 10000, 10000),
         'expect_rewards': (10000, 0, 16000), 'expect_debt_amount': 0},
        {'status': 'success', 'delegator': accounts[1], 'add_core': [(accounts[1], 10000, 500)],
         'add_btc': [(accounts[1], 100000, 1)], 'set_grades': (1000, 5000, 4000, 7000, 5000, 8000, 10000, 10000),
         'expect_rewards': (10000, 0, 50000), 'expect_debt_amount': 0}

    ]

    for test in tests:
        print(f'case{tests.index(test)}:', test)
        if 'add_core' in test:
            for delegator, v1, v2 in test['add_core']:
                core_agent.setCoreRewardMap(delegator, v1, v2)
        if 'add_btc' in test:
            for validator, v1, v2 in test['add_btc']:
                btc_stake.setBtcRewardMap(validator, v1, v2, v2)
        if 'set_grades' in test:
            btc_agent.setIsActive(True)
            btc_agent.setInitLpRates(*test['set_grades'])

        if test['status'] == 'success':
            assert stake_hub.calculateRewardMock(test['delegator']).return_value == (
                test['expect_rewards'])

