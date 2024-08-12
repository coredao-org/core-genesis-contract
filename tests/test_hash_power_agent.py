import brownie
import pytest
from web3 import Web3
from brownie import accounts
from .common import turn_round, register_candidate, get_current_round
from .delegate import delegate_power_success
from .utils import update_system_contract_address

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
POWER_REWARD = 0
ONE_ETHER = Web3.to_wei(1, 'ether')
TX_FEE = int(1e4)


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_min_init_delegate_value(min_init_delegate_value):
    global MIN_INIT_DELEGATE_VALUE
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, stake_hub, hash_power_agent, btc_light_client):
    global BLOCK_REWARD, HASH_POWER_AGENT, BTC_LIGHT_CLIENT
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * (100 - block_reward_incentive_percent) // 100
    HASH_POWER_AGENT = hash_power_agent
    BTC_LIGHT_CLIENT = btc_light_client


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_init_can_only_run_once(hash_power_agent):
    with brownie.reverts("the contract already init"):
        hash_power_agent.init()


def __check_reward_power(delegator, result: dict):
    reward = HASH_POWER_AGENT.rewardMap(delegator)
    for r in result:
        assert reward[r] == result.get(r)


def test_distribute_reward_success(hash_power_agent):
    validators = accounts[:3]
    staked_amounts = [6, 12, 15]
    sum_stake_amounts = [6, 14, 17]
    reward_list = [1000, 20000, 30000]
    round_tag = get_current_round()
    for index, v in enumerate(validators):
        if index == 0:
            delegate_power_success(v, accounts[index], staked_amounts[index])
        else:
            BTC_LIGHT_CLIENT.setMiners(1, v, [accounts[index]] * staked_amounts[index] + [accounts[5]] * 2)
    turn_round()
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    hash_power_agent.distributeReward(validators, reward_list, round_tag + 1)
    for index, v in enumerate(validators):
        reward = reward_list[index] // sum_stake_amounts[index] * staked_amounts[index]
        __check_reward_power(accounts[index], {
            'reward': reward,
            'accStakedAmount': staked_amounts[index]
        })
    __check_reward_power(accounts[5], {
        'accStakedAmount': 4
    })


def test_distribute_reward_with_new_validator(hash_power_agent):
    validators = accounts[:3]
    staked_amounts = [6, 12, 15]
    reward_list = [1000, 20000, 30000]
    round_tag = get_current_round()
    for index, v in enumerate(validators[1:]):
        index = index + 1
        delegate_power_success(v, accounts[index], staked_amounts[index])
    turn_round()
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    hash_power_agent.distributeReward(validators, reward_list, round_tag + 1)
    for index, v in enumerate(validators):
        reward = reward_list[index] // staked_amounts[index] * staked_amounts[index]
        acc_stake_amount = staked_amounts[index]
        if index == 0:
            reward = 0
            acc_stake_amount = 0
        __check_reward_power(accounts[index], {
            'reward': reward,
            'accStakedAmount': acc_stake_amount
        })


def test_distribute_reward_with_zero_amount(hash_power_agent, candidate_hub):
    validators = accounts[:3]
    rewards = [0, 0, 0]
    round_tag = get_current_round()
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    hash_power_agent.distributeReward(validators, rewards, round_tag)
    reward = 0
    for index, v in enumerate(validators):
        __check_reward_power(v, {
            'reward': reward,
            'accStakedAmount': 0
        })


def test_distribute_reward_only_stake_hub_can_call(hash_power_agent):
    validators = accounts[:3]
    reward_list = [1000, 20000, 30000]
    with brownie.reverts("the msg sender must be stake hub contract"):
        hash_power_agent.distributeReward(validators, reward_list, 0)


def test_get_power_stake_amounts_success(hash_power_agent, set_candidate):
    operators, consensuses = set_candidate
    staked_amounts = [6, 12, 15]
    sum_stake_amounts = [6, 14, 17]
    round_tag = get_current_round()
    for index, v in enumerate(operators):
        if index == 0:
            delegate_power_success(v, accounts[index], staked_amounts[index])
        else:
            BTC_LIGHT_CLIENT.setMiners(round_tag - 6, v, [accounts[index]] * staked_amounts[index] + [accounts[5]] * 2)
    turn_round()
    power_amounts = hash_power_agent.getStakeAmounts(operators, round_tag + 1)
    assert power_amounts[0] == sum_stake_amounts
    assert power_amounts[1] == sum(sum_stake_amounts)


def test_power_claim_reward_success(hash_power_agent):
    validators = accounts[:3]
    staked_amounts = [6, 12, 15]
    sum_stake_amounts = [6, 14, 17]
    reward_list = [1000, 20000, 30000]
    round_tag = get_current_round()
    for index, v in enumerate(validators):
        if index == 0:
            delegate_power_success(v, accounts[index], staked_amounts[index])
        else:
            BTC_LIGHT_CLIENT.setMiners(1, v, [accounts[index]] * staked_amounts[index] + [accounts[5]] * 2)
    turn_round()
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    hash_power_agent.distributeReward(validators, reward_list, round_tag + 1)
    for index, v in enumerate(validators):
        reward_sum, unclaimed, acc_staked_amount = hash_power_agent.claimReward(accounts[index], 0).return_value
        reward = reward_list[index] // sum_stake_amounts[index] * staked_amounts[index]
        actual_acc_staked_amount = staked_amounts[index]
        assert reward_sum == reward
        assert actual_acc_staked_amount == actual_acc_staked_amount
        assert unclaimed == 0
        __check_reward_power(accounts[5], {
            'accStakedAmount': 4
        })


def test_claim_power_no_reward_success(hash_power_agent):
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    reward_sum, unclaimed, acc_staked_amount = hash_power_agent.claimReward(accounts[0], 0).return_value
    assert reward_sum == 0
    assert acc_staked_amount == 0


def test_acc_stake_amount_success(hash_power_agent, set_candidate, stake_hub):
    turn_round()
    operators, consensuses = set_candidate
    staked_amounts = [6, 12, 15]
    for index, v in enumerate(operators):
        delegate_power_success(v, accounts[index], staked_amounts[index])
    turn_round()
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    reward_sum, unclaimed, acc_staked_amount = hash_power_agent.claimReward(accounts[0], 0).return_value
    assert acc_staked_amount == 0
    update_system_contract_address(hash_power_agent, stake_hub=stake_hub)
    turn_round(consensuses)
    update_system_contract_address(hash_power_agent, stake_hub=accounts[0])
    reward_sum, unclaimed, acc_staked_amount = hash_power_agent.claimReward(accounts[0], 0).return_value
    assert acc_staked_amount == staked_amounts[0]


def test_only_stake_hub_can_call_claim_reward(hash_power_agent):
    with brownie.reverts("the msg sender must be stake hub contract"):
        hash_power_agent.claimReward(accounts[0], 0)


def test_update_param_callable_only_after_init(hash_power_agent):
    hash_power_agent.setAlreadyInit(False)
    with brownie.reverts("the contract not init yet"):
        hash_power_agent.updateParam('requiredCoinDeposit', '0x00')


def test_only_gov_can_call_update_param(hash_power_agent):
    with brownie.reverts("the msg sender must be governance contract"):
        hash_power_agent.updateParam('requiredCoinDeposit', '0x00')


def test_revert_on_nonexistent_governance_param(hash_power_agent):
    update_system_contract_address(hash_power_agent, gov_hub=accounts[0])
    with brownie.reverts("UnsupportedGovParam: error"):
        hash_power_agent.updateParam('error', '0x00')
