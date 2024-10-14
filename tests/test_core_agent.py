import pytest
import brownie
from brownie import *
from web3 import Web3
from .calc_reward import parse_delegation, set_delegate
from .constant import *
from .delegate import *
from .utils import random_address, expect_event, get_tracker, encode_args_with_signature, \
    update_system_contract_address, padding_left
from .common import register_candidate, turn_round, get_current_round, stake_hub_claim_reward

MIN_INIT_DELEGATE_VALUE = 0
CANDIDATE_REGISTER_MARGIN = 0
candidate_hub_instance = None
core_agent_instance = None
required_coin_deposit = 0
TX_FEE = Web3.to_wei(1, 'ether')
# the tx fee is 1 ether
actual_block_reward = 0
BLOCK_REWARD = 0
TOTAL_REWARD = 0


@pytest.fixture(scope="module", autouse=True)
def set_up(min_init_delegate_value, core_agent, candidate_hub, btc_light_client, validator_set):
    global MIN_INIT_DELEGATE_VALUE
    global CANDIDATE_REGISTER_MARGIN
    global candidate_hub_instance
    global core_agent_instance
    global required_coin_deposit
    global actual_block_reward
    global BLOCK_REWARD
    global CORE_AGENT
    global TOTAL_REWARD

    candidate_hub_instance = candidate_hub
    core_agent_instance = core_agent
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value
    CANDIDATE_REGISTER_MARGIN = candidate_hub.requiredMargin()
    required_coin_deposit = core_agent.requiredCoinDeposit()

    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    actual_block_reward = total_block_reward * (100 - block_reward_incentive_percent) // 100
    tx_fee = 100
    BLOCK_REWARD = (block_reward + tx_fee) * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    CORE_AGENT = core_agent


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_core_agent_init_can_only_run_once(core_agent):
    with brownie.reverts("the contract already init"):
        core_agent.init()


def test_revert_if_not_called_by_only_pledge_agent(core_agent):
    candidates = accounts[:3]
    amounts = [1000, 2000, 3000]
    realtime_amounts = [2000, 2000, 4000]
    with brownie.reverts("the sender must be PledgeAgent contract"):
        core_agent._initializeFromPledgeAgent(candidates, amounts, realtime_amounts)


def test_initialize_from_pledge_agent_success(core_agent):
    update_system_contract_address(core_agent, pledge_agent=accounts[0])
    candidates = accounts[:3]
    amounts = [1000, 2000, 3000]
    realtime_amounts = [2000, 2000, 4000]
    core_agent._initializeFromPledgeAgent(candidates, amounts, realtime_amounts)
    for index, i in enumerate(candidates):
        c = core_agent.candidateMap(i)
        assert c['amount'] == amounts[index]
        assert c['realtimeAmount'] == realtime_amounts[index]


def test_distribute_reward_success(core_agent):
    validators = accounts[:3]
    staked_amounts = [3000, 5000, 6000]
    reward_list = [1000, 20000, 30000]
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    round_tag = get_current_round()
    for index, v in enumerate(validators):
        core_agent.setCandidateMapAmount(v, staked_amounts[index], staked_amounts[index] * 2, round_tag - 1)
    core_agent.distributeReward(validators, reward_list, round_tag)
    for index, v in enumerate(validators):
        reward = reward_list[index] * Utils.CORE_STAKE_DECIMAL // staked_amounts[index]
        __check_accured_reward_core(v, round_tag, reward)


def test_distribute_reward_with_new_validator(core_agent):
    validators = accounts[:3]
    reward_list = [3000, 1200, 3000]
    staked_amounts = [5000, 8000, 13000]
    round_tag = get_current_round()
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    for index, v in enumerate(validators[:2]):
        core_agent.setCandidateMapAmount(v, staked_amounts[index], staked_amounts[index] * 2, round_tag - 1)
    core_agent.setCandidateMapAmount(accounts[2], staked_amounts[2], staked_amounts[2], 0)
    assert len(__get_continuous_reward_end_rounds(accounts[2])) == 0
    core_agent.distributeReward(validators, reward_list, round_tag)
    for index, v in enumerate(validators):
        reward = reward_list[index] * Utils.CORE_STAKE_DECIMAL // staked_amounts[index]
        __check_accured_reward_core(v, round_tag, reward)
    assert __get_continuous_reward_end_rounds(accounts[2])[0] == round_tag


def test_distribute_reward_with_existing_history(core_agent, candidate_hub):
    validators = accounts[:3]
    reward_list = [2000, 1000, 3000]
    staked_amounts = [3000, 5000, 6000]
    round_tag = get_current_round()
    history_reward0 = 5000
    history_reward1 = 120000
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    core_agent.setCandidateMapAmount(accounts[0], staked_amounts[0], staked_amounts[0] * 2, round_tag - 6)
    core_agent.setCandidateMapAmount(accounts[0], staked_amounts[0], staked_amounts[0] * 2, round_tag - 3)
    core_agent.setAccuredRewardMap(accounts[0], round_tag - 6, history_reward0)
    core_agent.setAccuredRewardMap(accounts[0], round_tag - 3, history_reward1)
    core_agent.setCandidateMapAmount(accounts[1], staked_amounts[1], staked_amounts[1], round_tag - 1)
    core_agent.setCandidateMapAmount(accounts[2], staked_amounts[2], staked_amounts[2], 0)
    core_agent.distributeReward(validators, reward_list, round_tag)
    account_reward0 = history_reward1 + reward_list[0] * Utils.CORE_STAKE_DECIMAL // staked_amounts[0]
    __check_accured_reward_core(accounts[0], round_tag, account_reward0)
    for index, v in enumerate(validators[1:]):
        index = index + 1
        reward = reward_list[index] * Utils.CORE_STAKE_DECIMAL // staked_amounts[index]
        __check_accured_reward_core(v, round_tag, reward)
    assert __get_continuous_reward_end_rounds(accounts[2])[0] == round_tag


def test_distribute_reward_with_zero_amount(core_agent, candidate_hub):
    validators = accounts[:3]
    rewards = [0, 0, 0]
    round_tag = get_current_round()
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    core_agent.distributeReward(validators, rewards, round_tag)
    reward = 0
    for index, v in enumerate(validators[1:]):
        __check_accured_reward_core(v, round_tag, reward)


def test_distribute_reward_only_stake_hub_can_call(core_agent):
    validators = accounts[:3]
    reward_list = [1000, 20000, 30000]
    with brownie.reverts("the msg sender must be stake hub contract"):
        core_agent.distributeReward(validators, reward_list, 0)


def test_get_core_stake_amounts_success(core_agent, set_candidate):
    operators, consensuses = set_candidate
    stake_amounts = []
    for index, o in enumerate(operators):
        __delegate_coin_success(o, accounts[0], 0, MIN_INIT_DELEGATE_VALUE + index)
        stake_amounts.append(MIN_INIT_DELEGATE_VALUE + index)
    amounts = core_agent.getStakeAmounts(operators, 0)
    assert amounts[0] == stake_amounts
    assert amounts[1] == sum(stake_amounts)


def test_only_stake_hub_can_call_set_new_round(core_agent, btc_agent):
    round_tag = get_current_round()
    with brownie.reverts("the msg sender must be stake hub contract"):
        core_agent.setNewRound(accounts[:2], round_tag)


def test_set_new_round_success(core_agent):
    round_tag = 7
    core_agent.setRoundTag(round_tag)
    assert core_agent.roundTag() == round_tag
    turn_round()
    round_tag += 1
    for index, o in enumerate(accounts[:4]):
        core_agent.setCandidateMapAmount(o, 0, MIN_INIT_DELEGATE_VALUE + index, 0)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    for index, op in enumerate(accounts[:4]):
        assert core_agent.candidateMap(op) == [0, MIN_INIT_DELEGATE_VALUE + index]
    core_agent.setNewRound(accounts[:4], round_tag + 1)
    for index, op in enumerate(accounts[:4]):
        assert core_agent.candidateMap(op) == [MIN_INIT_DELEGATE_VALUE + index, MIN_INIT_DELEGATE_VALUE + index]
    assert core_agent.roundTag() == round_tag + 1


class TestDelegateCoin:
    def test_delegate2unregistered_agent(self, core_agent):
        random_agent_addr = random_address()
        error_msg = encode_args_with_signature("InactiveCandidate(address)", [random_agent_addr])
        with brownie.reverts(error_msg):
            core_agent.delegateCoin(random_agent_addr)

    def test_delegate2registered_agent(self, core_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        tx = core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        expect_event(tx, "delegatedCoin", {
            "candidate": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE,
            "realtimeAmount": MIN_INIT_DELEGATE_VALUE
        })

    @pytest.mark.parametrize("second_value", [
        pytest.param(0, marks=pytest.mark.xfail),
        1,
        100,
        10000000,
        9999999999
    ])
    def test_delegate_multiple_times(self, core_agent, second_value):
        operator = accounts[1]
        register_candidate(operator=operator)
        core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        if second_value >= MIN_INIT_DELEGATE_VALUE:
            tx = core_agent.delegateCoin(operator, {"value": second_value})
            expect_event(tx, "delegatedCoin", {
                "amount": second_value,
                "realtimeAmount": MIN_INIT_DELEGATE_VALUE + second_value
            })
        else:
            with brownie.reverts('delegate amount is too small'):
                core_agent.delegateCoin(operator, {"value": second_value})

    def test_delegate2refused(self, core_agent, candidate_hub):
        operator = accounts[1]
        register_candidate(operator=operator)
        candidate_hub.refuseDelegate({'from': operator})
        error_msg = encode_args_with_signature("InactiveCandidate(address)", [operator.address])
        with brownie.reverts(f"{error_msg}"):
            core_agent.delegateCoin(operator)

    def test_delegate2validator(self, core_agent, candidate_hub, validator_set):
        operator = accounts[1]
        consensus_address = register_candidate(operator=operator)
        candidate_hub.turnRound()
        assert validator_set.isValidator(consensus_address)
        tx = core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        expect_event(tx, "delegatedCoin", {
            "candidate": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE,
            "realtimeAmount": MIN_INIT_DELEGATE_VALUE
        })

    def test_delegate2jailed(self, core_agent, slash_indicator, candidate_hub, validator_set):
        register_candidate(operator=accounts[10])

        operator = accounts[1]
        margin = candidate_hub.requiredMargin() + slash_indicator.felonyDeposit()
        consensus_address = register_candidate(operator=operator, margin=margin)
        candidate_hub.turnRound()

        assert len(validator_set.getValidators()) == 2

        felony_threshold = slash_indicator.felonyThreshold()
        for _ in range(felony_threshold):
            slash_indicator.slash(consensus_address)

        assert candidate_hub.isJailed(operator) is True
        error_msg = encode_args_with_signature("InactiveCandidate(address)", [operator.address])
        with brownie.reverts(f"{error_msg}"):
            core_agent.delegateCoin(operator)

    def test_delegate2under_margin(self, core_agent, slash_indicator, candidate_hub, validator_set):
        register_candidate(operator=accounts[10])
        operator = accounts[1]
        consensus_address = register_candidate(operator=operator)
        turn_round()

        assert len(validator_set.getValidators()) == 2
        assert validator_set.currentValidatorSetMap(consensus_address) > 0
        felony_threshold = slash_indicator.felonyThreshold()
        for _ in range(felony_threshold):
            slash_indicator.slash(consensus_address)
        assert candidate_hub.isJailed(operator) is True

        felony_round = slash_indicator.felonyRound()
        turn_round(round_count=felony_round)
        assert candidate_hub.isJailed(operator) is False

        error_msg = encode_args_with_signature("InactiveCandidate(address)", [operator.address])
        with brownie.reverts(f"{error_msg}"):
            core_agent.delegateCoin(operator)


def test_delegate_coin_failed_with_insufficient_deposit(core_agent):
    agent = accounts[1]
    delegator = accounts[2]

    __candidate_register(agent)
    with brownie.reverts("delegate amount is too small"):
        core_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit - 1})

    with brownie.reverts("delegate amount is too small"):
        core_agent.delegateCoin(agent, {'from': delegator})

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    with brownie.reverts("delegate amount is too small"):
        core_agent.delegateCoin(agent, {'from': delegator})


def test_delegate_coin_success(core_agent):
    turn_round()
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)
    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent, delegator, 0, required_coin_deposit, round_tag, 0)
    deposit = int(1e9)
    __delegate_coin_success(agent, delegator, required_coin_deposit, deposit)
    result = core_agent.getDelegator(agent, delegator).dict()
    result1 = core_agent.getDelegatorMap(delegator)
    assert result1[0][0] == agent
    __check_coin_delegator(agent, delegator, 0, required_coin_deposit + deposit, round_tag, 0)
    change_round = get_current_round()
    turn_round()
    turn_round()
    assert result['changeRound'] == change_round
    tx = core_agent.delegateCoin(agent, {'from': delegator, 'value': deposit})
    round_tag = core_agent.roundTag()
    expect_event(tx, "delegatedCoin", {
        'candidate': agent,
        'delegator': delegator,
        'amount': deposit,
        'realtimeAmount': required_coin_deposit + deposit * 2
    })
    __check_coin_delegator(agent, delegator, required_coin_deposit + deposit, required_coin_deposit + deposit * 2,
                           round_tag, 0)


def test_redelegate_calculates_reward(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    tx = core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    assert core_agent.delegatorMap(accounts[0]) == MIN_INIT_DELEGATE_VALUE * 2
    expect_event(tx, "delegatedCoin", {
        'candidate': operators[0],
        'delegator': accounts[0],
        'amount': MIN_INIT_DELEGATE_VALUE,
        'realtimeAmount': MIN_INIT_DELEGATE_VALUE * 2
    })
    assert core_agent.candidateMap(operators[0])['realtimeAmount'] == MIN_INIT_DELEGATE_VALUE * 2
    reward, acc_staked_amount = core_agent.rewardMap(accounts[0])
    assert reward == BLOCK_REWARD // 2
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE


def test_delegate_transfer_reward_calculation(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE)
    reward, acc_staked_amount = core_agent.rewardMap(accounts[0])
    assert reward == BLOCK_REWARD // 2
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE


def test_undelegate_amount_small(core_agent, validator_set):
    undelegate_value = MIN_INIT_DELEGATE_VALUE - 1
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensus in validator_set.getValidators()
    with brownie.reverts("undelegate amount is too small"):
        core_agent.undelegateCoin(operator, undelegate_value)


def test_undelegate_cannot_be_zero(core_agent, validator_set):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensus in validator_set.getValidators()
    with brownie.reverts("Undelegate zero coin"):
        core_agent.undelegateCoin(operator, 0)


def test_undelegate_coin_success(core_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)
    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent, delegator, 0, required_coin_deposit, round_tag, 0)
    turn_round()
    tracker = get_tracker(delegator)
    tx = core_agent.undelegateCoin(agent, required_coin_deposit, {'from': delegator})
    assert core_agent.candidateMap(agent)['realtimeAmount'] == 0
    expect_event(tx, "undelegatedCoin", {
        'candidate': agent,
        'delegator': delegator,
        'amount': required_coin_deposit
    })
    __check_coin_delegator(agent, delegator, 0, 0, 0, 0)
    assert tracker.delta() == MIN_INIT_DELEGATE_VALUE


def test_undelegate_coin_failed_with_no_delegate(core_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    with brownie.reverts("no delegator information found"):
        core_agent.undelegateCoin(agent, required_coin_deposit, {'from': delegator})


def test_fail_to_undelegate_after_transfer(core_agent):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    consensuses = []
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = transfer_amount0 + MIN_INIT_DELEGATE_VALUE
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], undelegate_amount)


def test_undelegeate_self(core_agent):
    register_candidate()
    core_agent.delegateCoin(accounts[0], {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    tx = core_agent.undelegateCoin(accounts[0], MIN_INIT_DELEGATE_VALUE)
    expect_event(tx, "undelegatedCoin", {
        "candidate": accounts[0],
        "delegator": accounts[0],
        "amount": MIN_INIT_DELEGATE_VALUE
    })


def test_partial_undelegate_coin_success(core_agent):
    delegate_amount = required_coin_deposit * 10
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)
    __delegate_coin_success(agent, delegator, 0, delegate_amount)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent, delegator, 0, delegate_amount, round_tag, 0)
    turn_round()
    tracker = get_tracker(delegator)
    tx = core_agent.undelegateCoin(agent, required_coin_deposit, {'from': delegator})
    assert core_agent.candidateMap(agent)['realtimeAmount'] == delegate_amount - MIN_INIT_DELEGATE_VALUE
    expect_event(tx, "undelegatedCoin", {
        'candidate': agent,
        'delegator': delegator,
        'amount': required_coin_deposit
    })
    __check_coin_delegator(agent, delegator, delegate_amount - MIN_INIT_DELEGATE_VALUE,
                           delegate_amount - MIN_INIT_DELEGATE_VALUE, get_current_round(), 0)
    assert tracker.delta() == MIN_INIT_DELEGATE_VALUE


def test_check_delegate_map_on_full_unstake(core_agent, validator_set):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    undelegate_amount = delegate_amount - required_coin_deposit
    core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    __check_coin_delegator(operators[0], accounts[0], 0, 0, get_current_round(), required_coin_deposit)
    turn_round(consensuses)
    candidates_length = len(__get_candidate_list_by_delegator(accounts[0]))
    assert candidates_length == 2
    stake_hub_claim_reward(accounts[0])
    candidates_length = len(__get_candidate_list_by_delegator(accounts[0]))
    assert candidates_length == 1
    turn_round()
    stake_hub_claim_reward(accounts[0])
    core_agent.undelegateCoin(operators[1], required_coin_deposit, {'from': accounts[0]})
    candidates_length = len(__get_candidate_list_by_delegator(accounts[0]))
    assert candidates_length == 0


def test_undelegate_calculates_historical_rewards(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    core_agent.undelegateCoin(operators[0], MIN_INIT_DELEGATE_VALUE)
    reward, acc_staked_amount = core_agent.rewardMap(accounts[0])
    assert reward == BLOCK_REWARD // 2
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelegate_with_recent_stake(core_agent, validator_set, undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    additional_amount = MIN_INIT_DELEGATE_VALUE * 3
    operator = accounts[2]
    register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.delegateCoin(operator, {"value": additional_amount, 'from': accounts[0]})
    undelegate_amount = additional_amount + delegate_amount
    core_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelegate_from_recent_transfer(core_agent, validator_set, undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.transferCoin(operators[1], operators[0], delegate_amount, {'from': accounts[0]})
    undelegate_amount = delegate_amount + MIN_INIT_DELEGATE_VALUE
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount * 2
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelagate_current_stake(core_agent, validator_set, undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    undelegate_amount = delegate_amount // 2
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelagate_current_transfer(core_agent, validator_set, undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.transferCoin(operators[1], operators[0], delegate_amount, {'from': accounts[0]})
    undelegate_amount = delegate_amount // 2
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})


def test_cancel_current_round_stake_on_candidate(core_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    delegate_amount = required_coin_deposit * 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


def test_cancel_current_round_stake_on_refuse_delegate_validator(core_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    delegate_amount = required_coin_deposit * 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    tx = core_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[0]})
    assert 'undelegatedCoin' in tx.events


def test_undelegate_small_remainder_success(core_agent, validator_set, candidate_hub):
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 7
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    additional_amount = delegate_amount
    operators = []
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    turn_round()
    core_agent.delegateCoin(operators[0], {"value": additional_amount, 'from': accounts[0]})
    core_agent.transferCoin(operators[0], operators[2], undelegate_amount, {'from': accounts[0]})
    tx = core_agent.undelegateCoin(operators[0], transfer_amount0, {'from': accounts[0]})
    assert 'undelegatedCoin' in tx.events


def test_undelegate_remain_amount_small(core_agent, validator_set):
    operators = []
    for operator in accounts[2:5]:
        operators.append(operator)
        register_candidate(operator=operator)
    operator = operators[0]
    undelegate_value = MIN_INIT_DELEGATE_VALUE + 99
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    turn_round()
    assert len(validator_set.getValidators()) == 3
    with brownie.reverts("remain amount is too small"):
        core_agent.undelegateCoin(operators[0], undelegate_value)


def test_cancel_all_without_amount_limit(core_agent, validator_set):
    operators = []
    for operator in accounts[2:5]:
        operators.append(operator)
        register_candidate(operator=operator)
    operator = operators[0]
    undelegate_value = MIN_INIT_DELEGATE_VALUE // 2 + MIN_INIT_DELEGATE_VALUE
    core_agent.setRequiredCoinDeposit(10)
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    turn_round()
    core_agent.undelegateCoin(operators[0], undelegate_value)
    core_agent.setRequiredCoinDeposit(1000)
    undelegate_value1 = 50
    with brownie.reverts("undelegate amount is too small"):
        core_agent.undelegateCoin(operators[0], undelegate_value1 - 1)
    tx = core_agent.undelegateCoin(operators[0], undelegate_value1)
    assert 'undelegatedCoin' in tx.events
    assert tx.events['undelegatedCoin']['amount'] == undelegate_value1


def test_remove_validator_info_after_full_cancel_stake(core_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = MIN_INIT_DELEGATE_VALUE * 10
    for op in operators:
        core_agent.delegateCoin(op, {"value": delegate_value})
    turn_round()
    core_agent.undelegateCoin(operators[1], undelegate_value)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert operators[0] in candidate_list
    assert operators[1] not in candidate_list
    assert operators[2] in candidate_list
    __check_coin_delegator_map(operators[1], accounts[0], {
        'changeRound': 0
    })
    core_agent.undelegateCoin(operators[0], undelegate_value)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert operators[1] not in candidate_list
    assert operators[0] not in candidate_list
    assert operators[2] in candidate_list
    __check_coin_delegator_map(operators[0], accounts[0], {
        'changeRound': 0
    })


def test_cancel_all_after_transfer_existing_stake(core_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = MIN_INIT_DELEGATE_VALUE * 10
    for op in operators:
        core_agent.delegateCoin(op, {"value": delegate_value})
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value)
    core_agent.undelegateCoin(operators[1], undelegate_value * 2)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert len(candidate_list) == 2
    __check_coin_delegator_map(operators[0], accounts[0], {
        'changeRound': get_current_round()
    })
    __check_coin_delegator_map(operators[1], accounts[0], {
        'changeRound': 0
    })
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert len(candidate_list) == 1
    __check_coin_delegator_map(operators[0], accounts[0], {
        'changeRound': 0
    })
    __check_coin_delegator_map(operators[1], accounts[0], {
        'changeRound': 0
    })
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD


@pytest.mark.parametrize("deduct_equal", [True, False])
def test_remove_validator_after_full_transfer_deduction(core_agent, deduct_equal):
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = delegate_value
    for op in operators:
        core_agent.delegateCoin(op, {"value": delegate_value * 2})
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_value)
    core_agent.undelegateCoin(operators[0], undelegate_value)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert operators == candidate_list
    __check_coin_delegator_map(operators[0], accounts[0], {
        'changeRound': get_current_round()
    })
    core_agent.deductTransferredAmountMock(accounts[0], undelegate_value * 2)
    __check_coin_delegator_map(operators[0], accounts[0], {
        'changeRound': 0
    })
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert [operators[4], operators[1], operators[2], operators[3]] == candidate_list
    core_agent.undelegateCoin(operators[1], undelegate_value * 2)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert [operators[4], operators[3], operators[2]] == candidate_list
    transfer_coin_success(operators[3], operators[4], accounts[0], delegate_value)
    core_agent.undelegateCoin(operators[3], undelegate_value)
    __check_coin_delegator_map(operators[3], accounts[0], {
        'transferredAmount': delegate_value
    })
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert [operators[4], operators[3], operators[2]] == candidate_list
    actual_candidate_list = [operators[4], operators[3], operators[2]]
    if deduct_equal is False:
        undelegate_value += 1
        actual_candidate_list = [operators[4], operators[2]]
    core_agent.deductTransferredAmountMock(accounts[0], undelegate_value)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert actual_candidate_list == candidate_list


@pytest.mark.parametrize("tests", [
    {'existing_stake': True, 'amount': 100, 'stakedAmount': 500, 'transferAmount': 400, 'realtimeAmount': 500,
     'changeRound': 8},
    {'existing_stake': True, 'amount': 600, 'stakedAmount': 500, 'transferAmount': 0, 'realtimeAmount': 500,
     'changeRound': 8},
    {'existing_stake': False, 'amount': 500, 'stakedAmount': 500, 'transferAmount': 0, 'realtimeAmount': 500,
     'changeRound': 8},
    {'existing_stake': False, 'amount': 200, 'stakedAmount': 500, 'transferAmount': 300, 'realtimeAmount': 500,
     'changeRound': 8}
])
def test_deduct_transferred_amount_success(core_agent, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['amount']
    staked_amount = tests['stakedAmount']
    transfer_amount = tests['transferAmount']
    realtime_amount = tests['realtimeAmount']
    change_round = tests['changeRound']
    delegate_coin_success(operators[0], accounts[0], delegate_value)
    realtime_amount1 = delegate_value // 2
    staked_amount1 = 0
    if tests['existing_stake']:
        delegate_coin_success(operators[1], accounts[0], delegate_value)
        realtime_amount1 = delegate_value + delegate_value // 2
        staked_amount1 = delegate_value
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value // 2)
    core_agent.deductTransferredAmountMock(accounts[0], undelegate_value)
    __check_coin_delegator_map(operators[0], accounts[0], {
        'stakedAmount': staked_amount,
        'realtimeAmount': realtime_amount,
        'transferredAmount': transfer_amount,
        'changeRound': change_round,
    })
    __check_coin_delegator_map(operators[1], accounts[0], {
        'stakedAmount': staked_amount1,
        'realtimeAmount': realtime_amount1,
        'transferredAmount': 0,
        'changeRound': get_current_round(),
    })


@pytest.mark.parametrize("tests", [
    {'deduct_amount': 500, 'transferAmount2': 500, 'transferAmount1': 1000, 'transferAmount0': 1000},
    {'deduct_amount': 1500, 'transferAmount2': 0, 'transferAmount1': 500, 'transferAmount0': 1000},
    {'deduct_amount': 2500, 'transferAmount2': 0, 'transferAmount1': 0, 'transferAmount0': 500},
    {'deduct_amount': 3000, 'transferAmount2': 0, 'transferAmount1': 0, 'transferAmount0': 0},
    {'deduct_amount': 2200, 'transferAmount2': 0, 'transferAmount1': 0, 'transferAmount0': 800}
])
def test_deduct_transfer_rewards_multi_validators(core_agent, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['deduct_amount']
    for index, op in enumerate(operators):
        delegate_coin_success(op, accounts[0], delegate_value * 2)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value)
    transfer_coin_success(operators[1], operators[2], accounts[0], delegate_value)
    transfer_coin_success(operators[2], operators[0], accounts[0], delegate_value)
    core_agent.deductTransferredAmountMock(accounts[0], undelegate_value)
    for i in range(3):
        __check_coin_delegator_map(operators[i], accounts[0], {
            'transferredAmount': tests[f'transferAmount{i}']
        })


def test_no_reward_deduction_on_transfer(core_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    for index, op in enumerate(operators):
        core_agent.delegateCoin(op, {"value": delegate_value * 2})
    turn_round()
    core_agent.deductTransferredAmountMock(accounts[0], MIN_INIT_DELEGATE_VALUE)
    for i in range(3):
        __check_coin_delegator_map(operators[i], accounts[0], {
            'stakedAmount': 0,
            'realtimeAmount': delegate_value * 2,
            'transferredAmount': 0,
            'changeRound': get_current_round() - 1,
        })


def test_transfer_coin_success(core_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    __candidate_register(agent_target)
    delegator = accounts[2]
    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent_source, delegator, 0, required_coin_deposit, round_tag, 0)
    turn_round()
    round_tag = core_agent.roundTag()
    tx = core_agent.transferCoin(agent_source, agent_target, required_coin_deposit, {'from': delegator})
    expect_event(tx, "transferredCoin", {
        'sourceCandidate': agent_source,
        'targetCandidate': agent_target,
        'delegator': delegator,
        'amount': required_coin_deposit,
        'realtimeAmount': required_coin_deposit
    })
    __check_coin_delegator(agent_source, delegator, 0, 0, round_tag, required_coin_deposit)
    __check_coin_delegator(agent_target, delegator, 0, required_coin_deposit, round_tag, 0)


def test_transfer_coin_failed_with_unregistered_agent(core_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    delegator = accounts[2]
    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent_source, delegator, 0, required_coin_deposit,
                           round_tag, 0)
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [agent_target.address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.transferCoin(agent_source, agent_target, required_coin_deposit, {'from': delegator})


def test_transfer2refused(core_agent, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    __delegate_coin_success(operators[0], accounts[0], 0, required_coin_deposit)
    candidate_hub.refuseDelegate({'from': operators[2]})
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [operators[2].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.transferCoin(operators[0], operators[2], required_coin_deposit, {'from': accounts[0]})


def test_transfer2jailed(core_agent, slash_indicator, candidate_hub, validator_set, set_candidate):
    operators, consensuses = set_candidate
    __delegate_coin_success(operators[0], accounts[0], 0, required_coin_deposit)
    turn_round()
    assert len(validator_set.getValidators()) == 3
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        slash_indicator.slash(consensuses[1])
    assert candidate_hub.isJailed(operators[1]) is True
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [operators[1].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


def test_transfer2under_margin(core_agent, slash_indicator, candidate_hub, validator_set, set_candidate):
    operators, consensuses = set_candidate
    __delegate_coin_success(operators[0], accounts[0], 0, required_coin_deposit)
    turn_round()
    assert len(validator_set.getValidators()) == 3
    assert validator_set.currentValidatorSetMap(consensuses[1]) > 0
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        slash_indicator.slash(consensuses[1])
    assert candidate_hub.isJailed(operators[1]) is True
    felony_round = slash_indicator.felonyRound()
    turn_round(round_count=felony_round)
    assert candidate_hub.isJailed(operators[1]) is False
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [operators[1].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


def test_transfer_amount_small(core_agent, validator_set, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensuses[0] in validator_set.getValidators()
    with brownie.reverts("undelegate amount is too small"):
        core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE - 1, {'from': accounts[0]})


def test_transfer_remain_amount_small(core_agent, validator_set):
    operators = []
    for operator in accounts[2:5]:
        operators.append(operator)
        register_candidate(operator=operator)
    operator = operators[0]
    undelegate_value = MIN_INIT_DELEGATE_VALUE + 99
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    turn_round()
    assert len(validator_set.getValidators()) == 3
    with brownie.reverts("remain amount is too small"):
        core_agent.transferCoin(operators[0], operators[1], undelegate_value)


def test_transfer_coin_failed_with_same_agent(core_agent):
    agent_source = accounts[1]
    agent_target = agent_source
    __candidate_register(agent_source)
    delegator = accounts[2]

    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)

    error_msg = encode_args_with_signature("SameCandidate(address)",
                                           [agent_source.address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.transferCoin(agent_source, agent_target, required_coin_deposit, {'from': delegator})


def test_transfer_coin_failed_with_no_delegator_in_source_agent(core_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    __candidate_register(agent_target)
    delegator = accounts[2]
    with brownie.reverts("no delegator information found"):
        core_agent.transferCoin(agent_source, agent_target, required_coin_deposit, {'from': delegator})


def test_stake_current_round_can_transfer(core_agent, validator_set, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': required_coin_deposit})
    core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


def test_transfer_small_remainder_success(core_agent, validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    tx = core_agent.transferCoin(operators[0], operators[1], delegate_amount - 1, {'from': accounts[0]})
    assert 'transferredCoin' in tx.events


def test_transfer_calculates_historical_rewards(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert core_agent.rewardMap(accounts[0]) == [BLOCK_REWARD // 2, MIN_INIT_DELEGATE_VALUE]


def test_only_stake_hub_can_call_claim_reward(core_agent):
    with brownie.reverts("the msg sender must be stake hub contract"):
        core_agent.claimReward(accounts[0], 0)


def test_core_claim_reward_success(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == TOTAL_REWARD
    assert reward_unclaimed == 0
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE
    assert core_agent.rewardMap(accounts[0]) == [0, 0]


def test_claim_reward_success_with_existing_historical_rewards(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    assert core_agent.rewardMap(accounts[0]) == [TOTAL_REWARD, MIN_INIT_DELEGATE_VALUE]
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == TOTAL_REWARD * 2
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE * 2
    assert core_agent.rewardMap(accounts[0]) == [0, 0]


def test_multi_validator_stake(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE * 2})
    core_agent.delegateCoin(operators[1], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses, round_count=2)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == TOTAL_REWARD * 4
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE * 6


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_validate_acc_stake_amount(core_agent, set_candidate, operate, stake_hub):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    delegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    acc_stake_amount0 = MIN_INIT_DELEGATE_VALUE * 3
    turn_round()
    if operate == 'delegate':
        delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    elif operate == 'undelegate':
        undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    elif operate == 'transfer':
        transfer_coin_success(operators[0], operators[2], accounts[0], MIN_INIT_DELEGATE_VALUE)
    else:
        stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    if operate == 'undelegate':
        acc_stake_amount0 -= MIN_INIT_DELEGATE_VALUE
    assert acc_staked_amount == acc_stake_amount0
    if operate == 'delegate':
        acc_stake_amount0 += MIN_INIT_DELEGATE_VALUE
    update_system_contract_address(core_agent, stake_hub=stake_hub)
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert acc_staked_amount == acc_stake_amount0


@pytest.mark.parametrize('round_count', [0, 1])
@pytest.mark.parametrize("tests", [
    [300, 'delegate', 'delegate', 'transfer', 'claim'],
    [200, 'delegate', 'undelegate', 'transfer', 'claim'],
    [200, 'undelegate', 'transfer', 'claim'],
    [200, 'transfer', 'undelegate', 'delegate']
])
def test_calc_acc_stake_after_coin_stake(core_agent, set_candidate, stake_hub, round_count, tests):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    delegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    acc_stake_amount0 = MIN_INIT_DELEGATE_VALUE * 3
    turn_round()
    operate = tests[1:]
    for i in operate:
        if i == 'delegate':
            delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
        elif i == 'undelegate':
            undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
            acc_stake_amount0 -= MIN_INIT_DELEGATE_VALUE
        elif i == 'transfer':
            transfer_coin_success(operators[0], operators[2], accounts[0], MIN_INIT_DELEGATE_VALUE)
        else:
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=round_count)
    acc_stake_amount0 *= round_count
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    expect_stake_amount = 0
    if round_count > 0:
        expect_stake_amount = tests[0]
    assert acc_staked_amount == acc_stake_amount0
    assert acc_staked_amount == expect_stake_amount


@pytest.mark.parametrize("tests", [
    [800, 'delegate', 'delegate', 'transfer', 'claim'],
    [500, 'delegate', 'undelegate', 'transfer', 'claim'],
    [400, 'undelegate', 'undelegate', 'delegate', 'delegate'],
    [700, 'transfer', 'transfer', 'delegate']
])
def test_acc_stake_amount_cross_round_success(core_agent, set_candidate, stake_hub, tests):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2)
    delegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)

    turn_round()
    operate = tests[1:]
    for i in operate:
        if i == 'delegate':
            delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
        elif i == 'undelegate':
            undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
        elif i == 'transfer':
            transfer_coin_success(operators[0], operators[2], accounts[0], MIN_INIT_DELEGATE_VALUE)
        else:
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=2)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    expect_stake_amount = tests[0]
    assert acc_staked_amount == expect_stake_amount

def test_clear_acc_stake_amount_after_claiming_rewards(core_agent, slash_indicator, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round()
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        slash_indicator.slash(consensuses[0])
    turn_round(consensuses, round_count=2)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == 0
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE * 2
    update_system_contract_address(core_agent, stake_hub=stake_hub)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert acc_staked_amount == MIN_INIT_DELEGATE_VALUE * 2


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_acc_stake_amount': 2500},
    {'transfer': 500, 'undelagate': 1, 'amount': 1000, 'expect_acc_stake_amount': 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_acc_stake_amount': 1500},
])
def test_check_acc_amount_after_cancel_stake_current_round(core_agent, validator_set, set_candidate, round_count,
                                                           tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_acc_stake_amount = tests['expect_acc_stake_amount']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses, round_count=round_count)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert acc_staked_amount == expect_acc_stake_amount * round_count


@pytest.mark.parametrize("tests", [
    {'delegate': 3000, 'transfer': 1500, 'undelagate': 0, 'amount': 1500, 'expect_reward': 13545 * 2 + 6772,
     'expect_stake_amount': 3500},
    {'delegate': 2000, 'transfer': 1000, 'undelagate': 1, 'amount': 2000, 'expect_reward': 13545 + 6772,
     'expect_stake_amount': 2000},
    {'delegate': 3000, 'transfer': 1500, 'undelagate': 2, 'amount': 3000, 'expect_reward': 13545 * 2 // 3,
     'expect_stake_amount': 2000}
])
def test_check_rewards_after_cancel_transfer_current_round(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        if index == 0:
            delegate_value = tests['delegate']
        delegate_coin_success(op, accounts[0], delegate_value)
    turn_round()
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == expect_reward
    assert acc_staked_amount == tests['expect_stake_amount']


def test_calculate_reward_success(core_agent, set_candidate):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    assert core_agent.rewardMap(accounts[0]) == (TOTAL_REWARD, MIN_INIT_DELEGATE_VALUE)
    turn_round(consensuses)
    update_system_contract_address(core_agent, stake_hub=accounts[0])
    reward = core_agent.claimReward(accounts[0], 0).return_value
    assert reward == [TOTAL_REWARD * 2, 0, MIN_INIT_DELEGATE_VALUE * 2]
    assert core_agent.rewardMap(accounts[0]) == [0, 0]


@pytest.mark.parametrize("round", [0, 1, 2, 3])
def test_multi_round_coin_stake_success(core_agent, set_candidate, round):
    operators, consensuses = set_candidate
    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses, round_count=round)
    reward = core_agent.collectCoinRewardMock(operators[0], accounts[0]).return_value
    assert reward == (TOTAL_REWARD * round, MIN_INIT_DELEGATE_VALUE * round)


def test_move_data_success(core_agent, pledge_agent):
    turn_round()
    operators, consensuses = __register_candidates(accounts[2:5])
    pledge_agent.delegateCoinOld(operators[1], {"value": Web3.to_wei(100000, 'ether')})
    candidate = accounts[2]
    delegator0 = accounts[0]
    delegator1 = accounts[1]
    staked_amount = MIN_INIT_DELEGATE_VALUE * 10
    transferred_amount = MIN_INIT_DELEGATE_VALUE * 5
    round_tag = 6
    real_amount = MIN_INIT_DELEGATE_VALUE * 20
    # scenario 1: Reward settlement is required
    core_agent.moveData(candidate, delegator0, staked_amount, transferred_amount, round_tag,
                        {'from': pledge_agent, 'value': real_amount})
    # the transfer part of the reward has been settled, so it is cleared to 0
    __check_coin_delegator(candidate, delegator0, real_amount, real_amount, get_current_round(), 0)
    assert __get_candidate_list_by_delegator(delegator0)[0] == candidate
    assert core_agent.delegatorMap(delegator0) == real_amount
    # scenario 2: No reward settlement
    staked_amount = MIN_INIT_DELEGATE_VALUE * 10 + 1
    transferred_amount = MIN_INIT_DELEGATE_VALUE * 5 + 1
    real_amount = MIN_INIT_DELEGATE_VALUE * 20 + 1

    core_agent.moveData(candidate, delegator1, staked_amount, transferred_amount, get_current_round(),
                        {'from': pledge_agent, 'value': real_amount})
    __check_coin_delegator(candidate, delegator1, staked_amount, real_amount, get_current_round(),
                           transferred_amount)
    assert __get_candidate_list_by_delegator(delegator1)[0] == candidate
    assert core_agent.delegatorMap(delegator1) == real_amount


def test_only_pledge_agent_can_call_move_data(core_agent, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    with brownie.reverts("the sender must be PledgeAgent contract"):
        core_agent.moveData(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE, 0, 0)


def test_move_data_with_excessive_stake_amount_reverts(core_agent):
    update_system_contract_address(core_agent, pledge_agent=accounts[0])
    with brownie.reverts("require stakedAmount <= realtimeAmount"):
        core_agent.moveData(accounts[0], accounts[0], MIN_INIT_DELEGATE_VALUE * 2, MIN_INIT_DELEGATE_VALUE, 0)


@pytest.mark.parametrize("operate", ['delegateCoin', 'undelegateCoin', 'transferCoin'])
def test_only_pledge_agent_can_call_proxy(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    error = 'the sender must be PledgeAgent contract'
    if operate == 'delegateCoin':
        with brownie.reverts(error):
            core_agent.proxyDelegate(operators[0], accounts[0], {'from': accounts[2], 'value': delegate_amount})
    elif operate == 'undelegateCoin':
        with brownie.reverts(error):
            core_agent.proxyUnDelegate(operators[0], accounts[0], delegate_amount, {'from': accounts[2]})
    else:
        with brownie.reverts(error):
            core_agent.proxyTransfer(operators[0], operators[1], accounts[0], delegate_amount, {'from': accounts[2]})


@pytest.mark.parametrize("operate", ['delegateCoin', 'undelegateCoin', 'transferCoin'])
def test_successful_proxy_method_call(core_agent, validator_set, operate, pledge_agent):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    pledge_agent.delegateCoinOld(operators[1], {"value": Web3.to_wei(100000, 'ether')})
    tx = core_agent.proxyDelegate(operators[0], accounts[0], {'from': pledge_agent, 'value': delegate_amount})
    assert tx.events['delegatedCoin']['amount'] == delegate_amount
    coin_reward = TOTAL_REWARD
    turn_round()
    if operate == 'delegateCoin':
        core_agent.proxyDelegate(operators[0], accounts[0], {'from': pledge_agent, 'value': delegate_amount})
    elif operate == 'undelegateCoin':
        core_agent.proxyUnDelegate(operators[0], accounts[0], delegate_amount, {'from': pledge_agent})
        coin_reward = 0
    else:
        core_agent.proxyTransfer(operators[0], operators[1], accounts[0], delegate_amount, {'from': pledge_agent})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == coin_reward


@pytest.mark.parametrize("operate", ['delegateCoin', 'undelegateCoin', 'transferCoin'])
def test_proxy_operation_with_insufficient_amount_reverts(core_agent, validator_set, operate, pledge_agent):
    delegate_amount = required_coin_deposit - 1
    operators, consensuses = __register_candidates(accounts[2:5])
    turn_round()
    update_system_contract_address(core_agent, pledge_agent=accounts[1])
    core_agent.proxyDelegate(operators[0], accounts[0], {'from': accounts[1], 'value': delegate_amount * 2})
    if operate == 'delegateCoin':
        with brownie.reverts("delegate amount is too small"):
            core_agent.proxyDelegate(operators[0], accounts[0], {'from': accounts[1], 'value': delegate_amount})
    elif operate == 'undelegateCoin':
        with brownie.reverts("undelegate amount is too small"):
            core_agent.proxyUnDelegate(operators[0], accounts[0], delegate_amount, {'from': accounts[1]})
    else:
        with brownie.reverts("undelegate amount is too small"):
            core_agent.proxyTransfer(operators[0], operators[1], accounts[0], delegate_amount, {'from': accounts[1]})


def test_proxy_delegate2_unregistered_agent(core_agent):
    update_system_contract_address(core_agent, pledge_agent=accounts[1])
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [accounts[5].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.proxyDelegate(accounts[5], accounts[0], {'from': accounts[1], 'value': MIN_INIT_DELEGATE_VALUE})


def test_proxy_delegate2refused(core_agent, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    update_system_contract_address(core_agent, pledge_agent=accounts[1])
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [operators[0].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.proxyDelegate(operators[0], accounts[3], {'from': accounts[1], 'value': MIN_INIT_DELEGATE_VALUE})


def test_proxy_transfer2unregistered_agent(core_agent):
    update_system_contract_address(core_agent, pledge_agent=accounts[0])
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [accounts[3].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.proxyTransfer(accounts[5], accounts[3], accounts[1], MIN_INIT_DELEGATE_VALUE)


def test_proxy_transfer_coin_failed_with_same_agent(core_agent, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(core_agent, pledge_agent=accounts[0])
    error_msg = encode_args_with_signature("SameCandidate(address)", [operators[0].address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.proxyTransfer(operators[0], operators[0], accounts[1], MIN_INIT_DELEGATE_VALUE)


def test_remove_delegation_success(core_agent, validator_set):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    candidates = __get_candidate_list_by_delegator(accounts[0])
    assert candidates[0] == operators[0]
    undelegate_amount = delegate_amount - required_coin_deposit
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
    core_agent.delegateCoin(operators[2], {'from': accounts[0], 'value': delegate_amount})
    candidates = __get_candidate_list_by_delegator(accounts[0])
    for index, c in enumerate(candidates):
        assert candidates[index] == operators[index]
    assert len(candidates) == 3
    turn_round()
    stake_hub_claim_reward(accounts[0])
    core_agent.undelegateCoin(operators[1], required_coin_deposit, {'from': accounts[0]})
    candidates = __get_candidate_list_by_delegator(accounts[0])
    assert candidates[0] == operators[-1]


def test_collect_coin_reward_success(validator_set, core_agent, stake_hub):
    operators = []
    consensuses = []
    for operator in accounts[6:11]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, commission=100))
    turn_round()
    __delegate_coin_success(operators[0], accounts[0], 0, required_coin_deposit)
    turn_round()
    turn_round([consensuses[0]], round_count=4, tx_fee=TX_FEE)
    delegator_tracker = get_tracker(accounts[0])
    reward_amount_m, acc_staked_amount = core_agent.collectCoinRewardMock(operators[0], accounts[0],
                                                                          {'from': accounts[0]}).return_value
    result = core_agent.getDelegator(operators[0], accounts[0]).dict()
    assert reward_amount_m == actual_block_reward * 90 // 100 * 4
    assert acc_staked_amount == required_coin_deposit * 4
    assert delegator_tracker.delta() == 0
    assert result['stakedAmount'] == MIN_INIT_DELEGATE_VALUE
    assert required_coin_deposit == result['realtimeAmount']
    assert result['changeRound'] == get_current_round()


def test_claim_reward_success_with_one_agent(core_agent, validator_set):
    agent = accounts[1]
    consensus_address = __candidate_register(agent)
    delegator = accounts[2]
    core_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit})
    turn_round()
    tracker = get_tracker(delegator)
    validator_set.deposit(consensus_address, {'value': TX_FEE})
    validator_set.deposit(consensus_address, {'value': TX_FEE})
    turn_round()
    stake_hub_claim_reward(delegator)
    denominator = 1000
    commission = 100
    assert actual_block_reward * 2 * (denominator - commission) // denominator == tracker.delta()


def test_claim_reward_with_multi_agent(core_agent, validator_set):
    staked_num = 5
    delegator = accounts[1]
    agent_list = []
    consensus_list = []
    expect_reward = 0

    for i in range(staked_num):
        agent_list.append(accounts[2 + i])
        consensus_list.append(__candidate_register(agent_list[i], 100 + i))
        if i < 3:
            core_agent.delegateCoin(agent_list[i], {'from': delegator, 'value': required_coin_deposit})
            expect_reward += actual_block_reward * (1000 - 100 - i) // 1000
    turn_round()
    tracker = get_tracker(delegator)
    for i in range(staked_num):
        validator_set.deposit(consensus_list[i], {'value': TX_FEE})
    turn_round()
    stake_hub_claim_reward(delegator)
    assert expect_reward == tracker.delta()


def test_claim_reward_with_transfer_coin(core_agent, validator_set):
    agent1 = accounts[1]
    agent2 = accounts[2]
    delegator = accounts[3]
    commission_percentage1 = 100
    commission_percentage2 = 500
    denominator = 1000
    consensus_addr1 = __candidate_register(agent1, commission_percentage1)
    consensus_addr2 = __candidate_register(agent2, commission_percentage2)
    core_agent.delegateCoin(agent1, {'from': delegator, 'value': required_coin_deposit})
    core_agent.delegateCoin(agent2, {'from': delegator, 'value': required_coin_deposit})

    turn_round()

    validator_set.deposit(consensus_addr1, {'value': TX_FEE})
    validator_set.deposit(consensus_addr2, {'value': TX_FEE})

    turn_round()
    tracker = get_tracker(delegator)

    core_agent.transferCoin(agent1, agent2, required_coin_deposit, {'from': delegator})
    validator_set.deposit(consensus_addr1, {'value': TX_FEE})
    validator_set.deposit(consensus_addr2, {'value': TX_FEE})

    turn_round()

    stake_hub_claim_reward(delegator)
    # the actual reward is subject to the deduction of the validator commission
    expect_reward1 = actual_block_reward * (denominator - commission_percentage1) // denominator * 2
    expect_reward2 = actual_block_reward * (denominator - commission_percentage2) // denominator * 2
    assert (expect_reward1 + expect_reward2) == tracker.delta()


def test_current_delegate_map(core_agent, validator_set):
    turn_round()
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator(operators[0], accounts[0], 0, delegate_amount, get_current_round(), 0)
    turn_round()
    __check_coin_delegator(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator(operators[0], accounts[0], delegate_amount, delegate_amount * 2, get_current_round(), 0)
    core_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[0]})
    __check_coin_delegator(operators[0], accounts[0], 0, delegate_amount, get_current_round(), 0)
    turn_round()
    __check_coin_delegator(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    transfer_amount = delegate_amount // 2
    core_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    __check_coin_delegator(operators[0], accounts[0], transfer_amount, transfer_amount, get_current_round(),
                           transfer_amount)
    turn_round()
    __check_coin_delegator(operators[2], accounts[0], 0, transfer_amount, get_current_round() - 1, 0)
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    core_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    __check_coin_delegator(operators[2], accounts[0], transfer_amount - undelegate_amount,
                           transfer_amount - undelegate_amount, get_current_round(), 0)


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_revert_on_cancel_with_zero_amount_transfer(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    if operate == 'undelegate':
        with brownie.reverts("Undelegate zero coin"):
            core_agent.undelegateCoin(operators[1], 0, {'from': accounts[0]})
    else:
        with brownie.reverts("Undelegate zero coin"):
            core_agent.transferCoin(operators[1], operators[2], 0, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_change_round_success_after_additional_stake(core_agent, validator_set, operate):
    turn_round()
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    __check_coin_delegator(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator(operators[0], accounts[0], delegate_amount, delegate_amount * 3, get_current_round(), 0)
    turn_round(consensuses)
    __check_coin_delegator(operators[0], accounts[0], delegate_amount, delegate_amount * 3, get_current_round() - 1,
                           0)
    transfer_amount = 0
    if operate == 'delegate':
        core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
        stake_amount = delegate_amount * 3
        real_amount = delegate_amount * 4
    elif operate == 'undelegate':
        core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
        stake_amount = delegate_amount * 3 - required_coin_deposit
        real_amount = stake_amount
    elif operate == 'transfer':
        core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
        stake_amount = delegate_amount * 3 - required_coin_deposit
        real_amount = stake_amount
        transfer_amount = required_coin_deposit
    else:
        stake_hub_claim_reward(accounts[0])
        stake_amount = delegate_amount * 3
        real_amount = stake_amount
    __check_coin_delegator(operators[0], accounts[0], stake_amount, real_amount, get_current_round(),
                           transfer_amount)


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_remaining_stake_includes_current_round_stake(core_agent, validator_set, operate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount - MIN_INIT_DELEGATE_VALUE + 1
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    if operate == 'undelegate':
        tx = core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
        event = 'undelegatedCoin'
        __check_coin_delegator(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE - 1,
                               delegate_amount * 2 - undelegate_amount,
                               get_current_round(), 0)
        core_agent.undelegateCoin.call(operators[0], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
        with brownie.reverts("undelegate amount is too small"):
            core_agent.undelegateCoin.call(operators[0], MIN_INIT_DELEGATE_VALUE - 1, {'from': accounts[0]})
    else:
        tx = core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})
        event = 'transferredCoin'
        __check_coin_delegator(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE - 1,
                               delegate_amount * 2 - undelegate_amount,
                               get_current_round(), undelegate_amount)
        __check_coin_delegator(operators[1], accounts[0], 0, undelegate_amount,
                               get_current_round(), 0)
        core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
        with brownie.reverts("undelegate amount is too small"):
            core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE - 1, {'from': accounts[0]})
    assert event in tx.events


def test_claim_without_rewards(core_agent, validator_set):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[2], 'value': delegate_amount})
    turn_round()
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_update_param_callable_only_after_init(core_agent):
    hex_value = padding_left(Web3.to_hex(150), 64)
    core_agent.setAlreadyInit(False)
    with brownie.reverts("the contract not init yet"):
        core_agent.updateParam('requiredCoinDeposit', hex_value)


def test_only_gov_can_call_update_param(core_agent):
    hex_value = padding_left(Web3.to_hex(150), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        core_agent.updateParam('requiredCoinDeposit', hex_value)


def test_update_param_success_about_key_requiredCoinDeposit(core_agent):
    new_value = 150
    hex_value = padding_left(Web3.to_hex(new_value), 64)
    update_system_contract_address(core_agent, gov_hub=accounts[0])
    core_agent.updateParam('requiredCoinDeposit', hex_value)
    assert core_agent.requiredCoinDeposit() == new_value


def test_updateParam_non_32bit_reverts(core_agent):
    new_value = 150
    hex_value = padding_left(Web3.to_hex(new_value), 58)
    update_system_contract_address(core_agent, gov_hub=accounts[0])
    with brownie.reverts("MismatchParamLength: requiredCoinDeposit"):
        core_agent.updateParam('requiredCoinDeposit', hex_value)


def test_revert_on_nonexistent_governance_param(core_agent):
    new_value = 150
    hex_value = padding_left(Web3.to_hex(new_value), 64)
    update_system_contract_address(core_agent, gov_hub=accounts[0])
    with brownie.reverts("UnsupportedGovParam: error"):
        core_agent.updateParam('error', hex_value)


def __get_continuous_reward_end_rounds(candidate):
    end_rounds = CORE_AGENT.getContinuousRewardEndRounds(candidate)
    return end_rounds


def __get_accured_reward_map(validate, round_tag):
    data = CORE_AGENT.getAccuredRewardMap(validate, round_tag)
    return data


def __check_accured_reward_core(validate, round_tag, result: int):
    reward = __get_accured_reward_map(validate, round_tag)
    assert reward == result


def __get_delegator_info(candidate, delegator):
    delegator_info = CoreAgentMock[0].getDelegator(candidate, delegator)
    return delegator_info


def __get_candidate_list_by_delegator(delegator):
    candidate_info = CoreAgentMock[0].getCandidateListByDelegator(delegator)
    return candidate_info


def __register_candidates(agents=None):
    operators = []
    consensuses = []
    if agents is None:
        agents = accounts[2:5]
    for operator in agents:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def __candidate_register(agent, percent=100):
    consensus_addr = random_address()
    fee_addr = random_address()
    candidate_hub_instance.register(consensus_addr, fee_addr, percent,
                                    {'from': agent, 'value': CANDIDATE_REGISTER_MARGIN})
    return consensus_addr


def __delegate_coin_success(agent, delegator, old_value, new_value):
    tx = core_agent_instance.delegateCoin(agent, {'from': delegator, 'value': new_value})
    expect_event(tx, "delegatedCoin", {
        "candidate": agent,
        "delegator": delegator,
        "amount": new_value,
        "realtimeAmount": new_value + old_value
    })


def __check_coin_delegator(candidate, delegator, staked_amount, real_amount, change_round, transferred_amount):
    c_delegator = __get_delegator_info(candidate, delegator)
    assert c_delegator['stakedAmount'] == staked_amount
    assert c_delegator['realtimeAmount'] == real_amount
    assert c_delegator['changeRound'] == change_round
    assert c_delegator['transferredAmount'] == transferred_amount


def __check_coin_delegator_map(candidate, delegator, result):
    c_delegator = __get_delegator_info(candidate, delegator)
    for i in result:
        assert c_delegator[i] == result[i]
