import pytest
from web3 import Web3
import brownie
from brownie import accounts
from eth_abi import encode_abi
from .utils import random_address, expect_event, padding_left, expect_event_not_emitted, get_tracker, \
    encode_args_with_signature
from .common import register_candidate, turn_round, execute_proposal

MIN_INIT_DELEGATE_VALUE = 0
POWER_FACTOR = 0
POWER_BLOCK_FACTOR = 0
CANDIDATE_REGISTER_MARGIN = 0
candidate_hub_instance = None
pledge_agent_instance = None
btc_light_client_instance = None
required_coin_deposit = 0
TX_FEE = Web3.toWei(1, 'ether')
actual_block_reward = 0


@pytest.fixture(scope="module", autouse=True)
def set_up(min_init_delegate_value, pledge_agent, candidate_hub, btc_light_client, validator_set):
    global MIN_INIT_DELEGATE_VALUE
    global POWER_FACTOR
    global POWER_BLOCK_FACTOR
    global CANDIDATE_REGISTER_MARGIN
    global candidate_hub_instance
    global pledge_agent_instance
    global required_coin_deposit
    global btc_light_client_instance
    global actual_block_reward

    candidate_hub_instance = candidate_hub
    pledge_agent_instance = pledge_agent
    btc_light_client_instance = btc_light_client
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value
    POWER_FACTOR = pledge_agent.powerFactor()
    POWER_BLOCK_FACTOR = pledge_agent.POWER_BLOCK_FACTOR()
    CANDIDATE_REGISTER_MARGIN = candidate_hub.requiredMargin()
    required_coin_deposit = pledge_agent.requiredCoinDeposit()

    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    actual_block_reward = total_block_reward * (100 - block_reward_incentive_percent) // 100


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-2].transfer(validator_set.address, Web3.toWei(100000, 'ether'))


class TestDelegateCoin:
    def test_delegate2unregistered_agent(self, pledge_agent):
        random_agent_addr = random_address()
        error_msg = encode_args_with_signature("InactiveAgent(address)", [random_agent_addr])
        with brownie.reverts(f"typed error: {error_msg}"):
            pledge_agent.delegateCoin(random_agent_addr)

    def test_delegate2registered_agent(self, pledge_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        tx = pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        expect_event(tx, "delegatedCoin", {
            "agent": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE,
            "totalAmount": MIN_INIT_DELEGATE_VALUE
        })

    @pytest.mark.parametrize("second_value", [
        pytest.param(0, marks=pytest.mark.xfail),
        1,
        100,
        10000000,
        9999999999
    ])
    def test_delegate_multiple_times(self, pledge_agent, second_value):
        operator = accounts[1]
        register_candidate(operator=operator)
        pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        if second_value >= MIN_INIT_DELEGATE_VALUE:
            tx = pledge_agent.delegateCoin(operator, {"value": second_value})
            expect_event(tx, "delegatedCoin", {
                "amount": second_value,
                "totalAmount": MIN_INIT_DELEGATE_VALUE + second_value
            })
        else:
            with brownie.reverts('deposit is too small'):
                pledge_agent.delegateCoin(operator, {"value": second_value})

    def test_delegate2refused(self, pledge_agent, candidate_hub):
        operator = accounts[1]
        register_candidate(operator=operator)
        candidate_hub.refuseDelegate({'from': operator})
        error_msg = encode_args_with_signature("InactiveAgent(address)", [operator.address])
        with brownie.reverts(f"typed error: {error_msg}"):
            pledge_agent.delegateCoin(operator)

    def test_delegate2validator(self, pledge_agent, candidate_hub, validator_set):
        operator = accounts[1]
        consensus_address = register_candidate(operator=operator)
        candidate_hub.turnRound()
        assert validator_set.isValidator(consensus_address)
        tx = pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        expect_event(tx, "delegatedCoin", {
            "agent": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE,
            "totalAmount": MIN_INIT_DELEGATE_VALUE
        })

    def test_delegate2jailed(self, pledge_agent, slash_indicator, candidate_hub, validator_set):
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
        error_msg = encode_args_with_signature("InactiveAgent(address)", [operator.address])
        with brownie.reverts(f"typed error: {error_msg}"):
            pledge_agent.delegateCoin(operator)

    def test_delegate2under_margin(self, pledge_agent, slash_indicator, candidate_hub, validator_set):
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

        error_msg = encode_args_with_signature("InactiveAgent(address)", [operator.address])
        with brownie.reverts(f"typed error: {error_msg}"):
            pledge_agent.delegateCoin(operator)


class TestUndelegateCoin:
    def test_undelegate(self, pledge_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round()
        tx = pledge_agent.undelegateCoin(operator)
        expect_event(tx, "undelegatedCoin", {
            "agent": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE
        })

    def test_undelegate_failed(self, pledge_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        turn_round()
        with brownie.reverts("delegator does not exist"):
            pledge_agent.undelegateCoin(operator)

    def test_fail_to_undelegate_after_transfer(self, pledge_agent):
        delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
        operators = []
        consensuses = []
        transfer_amount0 = delegate_amount // 2
        undelegate_amount = transfer_amount0 + MIN_INIT_DELEGATE_VALUE
        for operator in accounts[4:7]:
            operators.append(operator)
            consensuses.append(register_candidate(operator=operator))
        pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
        turn_round()
        pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
        with brownie.reverts("remaining amount is too small"):
            pledge_agent.undelegateCoin(operators[0], undelegate_amount)

    def test_undelegeate_self(self, pledge_agent):
        register_candidate()
        pledge_agent.delegateCoin(accounts[0], {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round()
        tx = pledge_agent.undelegateCoin(accounts[0])
        expect_event(tx, "undelegatedCoin", {
            "agent": accounts[0],
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE
        })

    def test_undelegate_with_reward(self, pledge_agent):
        operator = accounts[1]
        consensus = register_candidate(operator=operator)
        pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round([consensus])

        pledge_agent.undelegateCoin(operator)


class TestUpdateParams:
    def test_update_power_factor(self, pledge_agent):
        new_power_factor = 250
        hex_value = padding_left(Web3.toHex(new_power_factor), 64)

        execute_proposal(
            pledge_agent.address,
            0,
            "updateParam(string,bytes)",
            encode_abi(['string', 'bytes'], ['powerFactor', Web3.toBytes(hexstr=hex_value)]),
            "update power factor"
        )

        # check
        assert pledge_agent.powerFactor() == new_power_factor


def test_add_round_reward_success_with_normal_agent(pledge_agent, validator_set):
    agents = accounts[1:4]
    rewards = [1e7, 1e8, 1e8]
    coins = [1e6, 4e6]
    powers = [2, 5]
    total_coin = 1e7
    total_power = 10
    expect_coin_rewards = [0, 0]
    expect_power_rewards = [0, 0]

    for i in range(len(coins)):
        c_score = coins[i] * (total_power + 1)
        p_score = (total_coin + 1) * powers[i] * POWER_FACTOR // 10000
        agent_score = c_score + p_score
        expect_coin_rewards[i] = rewards[i] * c_score // agent_score
        expect_power_rewards[i] = rewards[i] * p_score // agent_score

    __candidate_register(agents[0])
    __candidate_register(agents[1])
    pledge_agent.setRoundState(total_power, total_coin)
    pledge_agent.setAgentValidator(agents[0], powers[0], coins[0])
    pledge_agent.setAgentValidator(agents[1], powers[1], coins[1])
    tx = validator_set.addRoundRewardMock(agents, rewards)

    for i in range(len(coins)):
        expect_event(tx, "roundReward", {
            "agent": agents[i],
            "coinReward": expect_coin_rewards[i],
            "powerReward": expect_power_rewards[i]
        }, idx=i)


def test_add_round_reward_success_with_no_agent(pledge_agent, validator_set):
    agents = accounts[1:4]
    rewards = (1e7, 1e8, 1e8)
    total_coin = 1e7
    total_power = 10
    __candidate_register(agents[0])
    __candidate_register(agents[1])
    pledge_agent.setRoundState(total_power, total_coin)
    tx = validator_set.addRoundRewardMock(agents, rewards)
    expect_event_not_emitted(tx, "roundReward")


def test_add_round_reward_failed_with_invalid_argument(validator_set):
    agents = accounts[1:4]
    rewards = [1e7, 1e8]
    with brownie.reverts("the length of agentList and rewardList should be equal"):
        validator_set.addRoundRewardMock(agents, rewards)


def test_get_score_success(candidate_hub, validator_set):
    agents = accounts[1:6]
    delegators = accounts[6:11]

    for i in range(3):
        __candidate_register(agents[i])
        __delegate_coin_success(agents[i], delegators[i], 0, required_coin_deposit + i)

    turn_round()
    for i in range(3):
        validator_set.deposit(agents[i], {'value': TX_FEE})

    for i in range(3, 5):
        __candidate_register(agents[i])
        __delegate_coin_success(agents[i], delegators[i], 0, required_coin_deposit + i)

    powers = [0, 0, 0, 3, 5]
    total_coin = required_coin_deposit * 5 + 1 + 10
    total_power = POWER_BLOCK_FACTOR * (3 + 5) + 1
    candidate_hub.getScoreMock(agents, powers)
    scores = candidate_hub.getScores()
    assert len(scores) == 5
    for i in range(5):
        expected_score = (required_coin_deposit + i) * total_power + total_coin * powers[
            i] * POWER_BLOCK_FACTOR * POWER_FACTOR // 10000
        assert expected_score == scores[i]


def test_collect_coin_reward_success(validator_set, pledge_agent):
    agent = accounts[1]
    consensus_address = __candidate_register(agent)
    delegator = accounts[2]
    turn_round()

    validator_set.deposit(consensus_address, {'value': TX_FEE})
    turn_round()

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    for _ in range(5):
        validator_set.deposit(consensus_address, {'value': TX_FEE})
        turn_round()

    expect_reward = actual_block_reward * 90 // 100 * 4
    delegator_tracker = get_tracker(delegator)
    result = pledge_agent.getDelegator(agent, delegator).dict()
    round_tag = result['changeRound']
    pledge_agent.collectCoinRewardMock(agent, delegator, 10, {'from': agent})
    reward_amount_M = pledge_agent.rewardAmountM()
    result = pledge_agent.getDelegator(agent, delegator).dict()

    assert expect_reward == reward_amount_M

    assert delegator_tracker.delta() == 0

    assert result['deposit'] == 0
    assert required_coin_deposit == result['newDeposit']
    assert round_tag == result['changeRound']
    assert result['rewardIndex'] == 6


def test_delegate_coin_success(pledge_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    round_tag = pledge_agent.roundTag()
    result = pledge_agent.getDelegator(agent, delegator).dict()
    __check_coin_delegator(result, 0, required_coin_deposit, round_tag, 0)

    reward_length = pledge_agent.getRewardLength(agent)
    assert reward_length == 0

    deposit = int(1e9)
    __delegate_coin_success(agent, delegator, required_coin_deposit, deposit)

    result = pledge_agent.getDelegator(agent, delegator).dict()
    __check_coin_delegator(result, 0, required_coin_deposit + deposit, round_tag, 0)

    turn_round()
    assert pledge_agent.getRewardLength(agent) == 1
    turn_round()
    assert pledge_agent.getRewardLength(agent) == 2

    tx = pledge_agent.delegateCoin(agent, {'from': delegator, 'value': deposit})
    round_tag = pledge_agent.roundTag()
    expect_event(tx, "delegatedCoin", {
        'agent': agent,
        'delegator': delegator,
        'amount': deposit,
        'totalAmount': required_coin_deposit + deposit * 2
    })
    result = pledge_agent.getDelegator(agent, delegator).dict()
    __check_coin_delegator(result, required_coin_deposit + deposit, required_coin_deposit + deposit * 2, round_tag, 1)


def test_delegate_coin_failed_with_insufficient_deposit(pledge_agent):
    agent = accounts[1]
    delegator = accounts[2]

    __candidate_register(agent)
    with brownie.reverts("deposit is too small"):
        pledge_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit - 1})

    with brownie.reverts("deposit is too small"):
        pledge_agent.delegateCoin(agent, {'from': delegator})

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    with brownie.reverts("deposit is too small"):
        pledge_agent.delegateCoin(agent, {'from': delegator})


def test_delegate_coin_failed_with_invalid_candidate(pledge_agent):
    agent = accounts[1]
    delegator = accounts[2]

    error_msg = encode_args_with_signature("InactiveAgent(address)", [agent.address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit - 1})


def test_undelegate_coin_success(pledge_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    round_tag = pledge_agent.roundTag()
    result = pledge_agent.getDelegator(agent, delegator).dict()
    __check_coin_delegator(result, 0, required_coin_deposit, round_tag, 0)

    tx = pledge_agent.undelegateCoin(agent, {'from': delegator})
    expect_event(tx, "undelegatedCoin", {
        'agent': agent,
        'delegator': delegator,
        'amount': required_coin_deposit
    })
    __check_coin_delegator(pledge_agent.getDelegator(agent, delegator).dict(), 0, 0, 0, 0)


def test_undelegate_coin_failed_with_no_delegate(pledge_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    with brownie.reverts("delegator does not exist"):
        pledge_agent.undelegateCoin(agent, {'from': delegator})


def test_transfer_coin_success(pledge_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    __candidate_register(agent_target)
    delegator = accounts[2]

    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)
    round_tag = pledge_agent.roundTag()
    result = pledge_agent.getDelegator(agent_source, delegator).dict()
    __check_coin_delegator(result, 0, required_coin_deposit, round_tag, 0)

    tx = pledge_agent.transferCoin(agent_source, agent_target, {'from': delegator})
    expect_event(tx, "transferredCoin", {
        'sourceAgent': agent_source,
        'targetAgent': agent_target,
        'delegator': delegator,
        'amount': required_coin_deposit,
        'totalAmount': required_coin_deposit
    })
    __check_coin_delegator(pledge_agent.getDelegator(agent_target, delegator), 0, required_coin_deposit, round_tag, 0)


def test_transfer_coin_failed_with_no_delegator_in_source_agent(pledge_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    __candidate_register(agent_target)
    delegator = accounts[2]

    with brownie.reverts("delegator does not exist"):
        pledge_agent.transferCoin(agent_source, agent_target, {'from': delegator})


def test_transfer_coin_failed_with_inactive_target_agent(pledge_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    delegator = accounts[2]

    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)
    round_tag = pledge_agent.roundTag()
    __check_coin_delegator(pledge_agent.getDelegator(agent_source, delegator).dict(), 0, required_coin_deposit,
                           round_tag, 0)

    error_msg = encode_args_with_signature("InactiveAgent(address)", [agent_target.address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.transferCoin(agent_source, agent_target, {'from': delegator})


def test_transfer_coin_failed_with_same_agent(pledge_agent):
    agent_source = accounts[1]
    agent_target = agent_source
    __candidate_register(agent_source)
    delegator = accounts[2]

    __delegate_coin_success(agent_source, delegator, 0, required_coin_deposit)

    error_msg = encode_args_with_signature("SameCandidate(address,address)",
                                           [agent_source.address, agent_target.address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.transferCoin(agent_source, agent_target, {'from': delegator})


def test_claim_reward_success_with_one_agent(pledge_agent, validator_set):
    agent = accounts[1]
    consensus_address = __candidate_register(agent)
    delegator = accounts[2]

    pledge_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit})
    turn_round()
    tracker = get_tracker(delegator)

    validator_set.deposit(consensus_address, {'value': TX_FEE})
    validator_set.deposit(consensus_address, {'value': TX_FEE})
    turn_round()

    pledge_agent.claimReward([agent], {'from': delegator})
    assert actual_block_reward * 2 * 900 // 1000 == tracker.delta()


def test_claim_reward_with_multi_agent(pledge_agent, validator_set):
    staked_num = 5
    delegator = accounts[1]
    agent_list = []
    consensus_list = []
    expect_reward = 0

    for i in range(staked_num):
        agent_list.append(accounts[2 + i])
        consensus_list.append(__candidate_register(agent_list[i], 100 + i))
        if i < 3:
            pledge_agent.delegateCoin(agent_list[i], {'from': delegator, 'value': required_coin_deposit})
            expect_reward += actual_block_reward * (1000 - 100 - i) // 1000
    turn_round()
    tracker = get_tracker(delegator)
    for i in range(staked_num):
        validator_set.deposit(consensus_list[i], {'value': TX_FEE})
    turn_round()
    pledge_agent.claimReward(agent_list[:5], {'from': delegator})
    assert expect_reward == tracker.delta()


def test_claim_reward_with_transfer_coin(pledge_agent, validator_set):
    agent1 = accounts[1]
    agent2 = accounts[2]
    delegator = accounts[3]
    consensus_addr1 = __candidate_register(agent1, 100)
    consensus_addr2 = __candidate_register(agent2, 500)
    pledge_agent.delegateCoin(agent1, {'from': delegator, 'value': required_coin_deposit})
    pledge_agent.delegateCoin(agent2, {'from': delegator, 'value': required_coin_deposit})

    turn_round()

    validator_set.deposit(consensus_addr1, {'value': TX_FEE})
    validator_set.deposit(consensus_addr2, {'value': TX_FEE})

    turn_round()
    tracker = get_tracker(delegator)

    tx = pledge_agent.transferCoin(agent1, agent2, {'from': delegator})
    validator_set.deposit(consensus_addr1, {'value': TX_FEE})
    validator_set.deposit(consensus_addr2, {'value': TX_FEE})

    turn_round()

    pledge_agent.claimReward([agent1, agent2], {'from': delegator})
    expect_reward1 = actual_block_reward * 900 // 1000
    expect_reward2 = actual_block_reward * 500 // 1000 * 2
    assert (expect_reward1 + expect_reward2 + expect_reward1) == tracker.delta()


def __candidate_register(agent, percent=100):
    consensus_addr = random_address()
    fee_addr = random_address()
    candidate_hub_instance.register(consensus_addr, fee_addr, percent,
                                    {'from': agent, 'value': CANDIDATE_REGISTER_MARGIN})
    return consensus_addr


def __delegate_coin_success(agent, delegator, old_value, new_value):
    tx = pledge_agent_instance.delegateCoin(agent, {'from': delegator, 'value': new_value})
    expect_event(tx, "delegatedCoin", {
        "agent": agent,
        "delegator": delegator,
        "amount": new_value,
        "totalAmount": new_value + old_value
    })


def __check_coin_delegator(c_delegator, deposit, new_deposit, change_round, reward_idx):
    assert c_delegator['deposit'] == deposit
    assert c_delegator['newDeposit'] == new_deposit
    assert c_delegator['changeRound'] == change_round
    assert c_delegator['rewardIndex'] == reward_idx
