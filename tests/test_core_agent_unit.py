import pytest
import brownie
from brownie import *
from web3 import Web3
from .calc_reward import parse_delegation, set_delegate
from .constant import *
from .utils import random_address, expect_event, get_tracker, encode_args_with_signature
from .common import register_candidate, turn_round, get_current_round, stake_hub_claim_reward

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


@pytest.fixture(scope="module", autouse=True)
def set_up(min_init_delegate_value, core_agent, candidate_hub, btc_light_client, validator_set, stake_hub):
    global MIN_INIT_DELEGATE_VALUE
    global CANDIDATE_REGISTER_MARGIN
    global candidate_hub_instance
    global core_agent_instance
    global required_coin_deposit
    global btc_light_client_instance
    global actual_block_reward
    global COIN_REWARD
    global BLOCK_REWARD

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


def test_core_agent_distribute_reward(core_agent, stake_hub):
    tests = [
        {'status': 'success', 'validators': [], 'reward_list': [], 'round': 100, 'amout_list': [],
         'real_amout_list': [], 'expect_round_reward': []},
        {'status': 'success', 'validators': [accounts[1]], 'reward_list': [100], 'round': 101, 'amout_list': [100],
         'real_amout_list': [100], 'expect_round_reward': [1000000]},
        {'status': 'success', 'validators': [accounts[1], accounts[2]], 'reward_list': [100, 200], 'round': 102,
         'amout_list': [100, 100], 'real_amout_list': [100, 100],
         'expect_round_reward': [2000000, 2000000]},
        {'status': 'failed', 'validators': [accounts[1], accounts[2]], 'reward_list': [100], 'round': 102,
         'amout_list': [100, 100], 'real_amout_list': [100, 100], 'expect_round_reward': []},
    ]

    for test in tests:
        if test['status'] == 'success':
            for validator, amout, real_amout in zip(test['validators'], test['amout_list'], test['real_amout_list']):
                core_agent.setCandidateMapAmount(validator, amout, real_amout, 0)
            tx = stake_hub.coreAgentDistributeReward(test['validators'], test['reward_list'], test['round'])
            for i in range(len(test['expect_round_reward'])):
                assert test['expect_round_reward'][i] == core_agent.getAccuredRewardMap(test['validators'][i],
                                                                                        test['round'])
        else:
            with brownie.reverts("the length of validators and rewardList should be equal"):
                stake_hub.coreAgentDistributeReward(test['validators'], test['reward_list'], test['round'])


def test_core_agent_get_stake_amounts(core_agent):
    tests = [
        {'candidates': [], 'set_candidates': {accounts[1]: 100}, 'expect_amounts': [], 'expect_total_amount': 0},
        {'candidates': [accounts[1]], 'set_candidates': {accounts[1]: 100}, 'expect_amounts': [100],
         'expect_total_amount': 100},
        {'candidates': [accounts[1], accounts[2]], 'set_candidates': {accounts[1]: 100, accounts[2]: 200},
         'expect_amounts': [100, 200], 'expect_total_amount': 300},
    ]

    for test in tests:
        for candidate, amount in test['set_candidates'].items():
            core_agent.setCandidateMapAmount(candidate, 0, amount, 0)
        amounts, total_amount = core_agent.getStakeAmounts(test['candidates'], 0)
        assert len(amounts) == len(test['expect_amounts'])
        for i in range(len(amounts)):
            assert test['expect_amounts'][i] == amounts[i]
        assert test['expect_total_amount'] == total_amount


def test_core_agent_delegate_coin(core_agent, candidate_hub):
    turn_round()
    register_candidate(operator=accounts[1])
    round_tag = candidate_hub.roundTag()
    tests = [
        {'status': 'failed', 'err': 'delegate amount is too small', 'candidate': accounts[1],
         'value': required_coin_deposit - 1},
        {'status': 'failed', 'err': encode_args_with_signature("InactiveCandidate(address)", [accounts[2]]),
         'candidate': accounts[2], 'value': required_coin_deposit},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit,
         'expect_cd': (0, required_coin_deposit, 0, round_tag)},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit,
         'expect_cd': (0, required_coin_deposit * 2, 0, round_tag)},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit,
         'expect_cd': (required_coin_deposit * 2, required_coin_deposit * 3, 0, round_tag + 1), 'turn_round': 1},
    ]

    for test in tests:
        if 'turn_round' in test:
            turn_round([accounts[1]])
        if test['status'] == 'success':
            core_agent.delegateCoin(test['candidate'], {'from': accounts[0], 'value': test['value']})
            info = core_agent.getDelegator(test['candidate'], accounts[0])
            assert info == test['expect_cd']
        else:
            with brownie.reverts(test['err']):
                core_agent.delegateCoin(test['candidate'], {'from': accounts[0], 'value': test['value']})


def test_core_agent_undelegate_coin(core_agent, candidate_hub):
    turn_round()
    register_candidate(operator=accounts[1])
    core_agent.delegateCoin(accounts[1], {'from': accounts[0], 'value': required_coin_deposit * 3})
    round_tag = candidate_hub.roundTag()
    tests = [
        {'status': 'failed', 'err': 'undelegate amount is too small', 'candidate': accounts[1],
         'value': required_coin_deposit - 1},
        {'status': 'failed', 'err': 'no delegator information found', 'candidate': accounts[2],
         'value': required_coin_deposit},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit,
         'expect_cd': (0, required_coin_deposit * 2, 0, round_tag)},
        {'status': 'failed', 'err': 'Not enough staked tokens', 'candidate': accounts[1],
         'value': required_coin_deposit * 2 + 1, 'turn_round': 1},
        {'status': 'failed', 'err': 'remain amount is too small', 'candidate': accounts[1],
         'value': required_coin_deposit * 2 - 1},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit,
         'expect_cd': (required_coin_deposit, required_coin_deposit, 0, round_tag + 1)},
        {'status': 'success', 'candidate': accounts[1], 'value': required_coin_deposit, 'expect_cd': (0, 0, 0, 0)},
    ]

    for test in tests:
        if 'turn_round' in test:
            turn_round([accounts[1]])
        if test['status'] == 'success':
            core_agent.undelegateCoin(test['candidate'], test['value'], {'from': accounts[0]})
            info = core_agent.getDelegator(test['candidate'], accounts[0])
            assert info == test['expect_cd']
        else:
            with brownie.reverts(test['err']):
                core_agent.undelegateCoin(test['candidate'], test['value'], {'from': accounts[0]})


def test_core_agent_transfer_coin(core_agent, candidate_hub):
    turn_round()
    register_candidate(operator=accounts[1])
    register_candidate(operator=accounts[2])
    core_agent.delegateCoin(accounts[1], {'from': accounts[0], 'value': required_coin_deposit * 2})
    turn_round()
    round_tag = candidate_hub.roundTag()
    tests = [
        {'status': 'failed', 'err': encode_args_with_signature("InactiveCandidate(address)", [accounts[3]]),
         'source_andidate': accounts[1], 'target_candidate': accounts[3], 'value': required_coin_deposit},
        {'status': 'failed', 'err': encode_args_with_signature("SameCandidate(address)", [accounts[1]]),
         'source_andidate': accounts[1], 'target_candidate': accounts[1], 'value': required_coin_deposit},
        {'status': 'failed', 'err': 'undelegate amount is too small', 'source_andidate': accounts[1],
         'target_candidate': accounts[2], 'value': required_coin_deposit - 1},
        {'status': 'failed', 'err': 'no delegator information found', 'source_andidate': accounts[3],
         'target_candidate': accounts[2], 'value': required_coin_deposit},
        {'status': 'failed', 'err': 'Not enough staked tokens', 'source_andidate': accounts[1],
         'target_candidate': accounts[2], 'value': required_coin_deposit * 2 + 1},
        {'status': 'failed', 'err': 'remain amount is too small', 'source_andidate': accounts[1],
         'target_candidate': accounts[2], 'value': required_coin_deposit * 2 - 1},
        {'status': 'success', 'source_andidate': accounts[1], 'target_candidate': accounts[2],
         'value': required_coin_deposit,
         'expect_scd': (required_coin_deposit, required_coin_deposit, required_coin_deposit, round_tag),
         'expect_tcd': (0, required_coin_deposit, 0, round_tag)},
        {'status': 'success', 'source_andidate': accounts[1], 'target_candidate': accounts[2],
         'value': required_coin_deposit, 'expect_scd': (0, 0, required_coin_deposit * 2, round_tag),
         'expect_tcd': (0, required_coin_deposit * 2, 0, round_tag)},
    ]

    for test in tests:
        if 'turn_round' in test:
            turn_round([accounts[1]])
        if test['status'] == 'success':
            core_agent.transferCoin(test['source_andidate'], test['target_candidate'], test['value'],
                                    {'from': accounts[0]})
            assert core_agent.getDelegator(test['source_andidate'], accounts[0]) == test['expect_scd']
            assert core_agent.getDelegator(test['target_candidate'], accounts[0]) == test['expect_tcd']
        else:
            with brownie.reverts(test['err']):
                core_agent.transferCoin(test['source_andidate'], test['target_candidate'], test['value'],
                                        {'from': accounts[0]})
