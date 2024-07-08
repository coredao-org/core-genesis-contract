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
def set_up(min_init_delegate_value, core_agent, candidate_hub, btc_light_client, validator_set):
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


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


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


class TestUndelegateCoin:
    def test_undelegate(self, core_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round()
        tx = core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)
        expect_event(tx, "undelegatedCoin", {
            "candidate": operator,
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE
        })

    def test_undelegate_failed(self, core_agent):
        operator = accounts[1]
        register_candidate(operator=operator)
        turn_round()
        with brownie.reverts("no delegator information found"):
            core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)

    def test_fail_to_undelegate_after_transfer(self, core_agent):
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

    def test_undelegeate_self(self, core_agent):
        register_candidate()
        core_agent.delegateCoin(accounts[0], {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round()
        tx = core_agent.undelegateCoin(accounts[0], MIN_INIT_DELEGATE_VALUE)
        expect_event(tx, "undelegatedCoin", {
            "candidate": accounts[0],
            "delegator": accounts[0],
            "amount": MIN_INIT_DELEGATE_VALUE
        })

    def test_undelegate_with_reward(self, core_agent):
        operator = accounts[1]
        consensus = register_candidate(operator=operator)
        core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round([consensus])

        core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)


def test_add_round_reward_success_with_normal_agent(core_agent, validator_set, candidate_hub, hash_power_agent,
                                                    btc_agent, stake_hub):
    agents = accounts[1:4]
    rewards = [1e7, 1e8]
    coins = [1e6, 4e6]
    powers = [2, 5]
    __candidate_register(agents[0])
    __candidate_register(agents[1])
    stake_hub.setCandidateAmountMap(agents[0], coins[0], powers[0], 0)
    stake_hub.setCandidateAmountMap(agents[1], coins[1], powers[1], 0)
    _, _, account_rewards, _, collateral_state = parse_delegation([{
        "address": agents[0],
        "active": True,
        "coin": [set_delegate(accounts[0], coins[0])],
        "power": [set_delegate(accounts[0], powers[0])],
        "btc": []
    }, {
        "address": agents[1],
        "active": True,
        "coin": [set_delegate(accounts[0], coins[1])],
        "power": [set_delegate(accounts[0], powers[1])],
        "btc": []
    }], 0)
    stake_hub.setStateMapDiscount(core_agent.address, 0, 1, collateral_state['coin'])
    core_agent.setCandidateMapAmount(agents[0], coins[0], coins[0])
    core_agent.setCandidateMapAmount(agents[1], coins[1], coins[1])
    round_tag = candidate_hub.roundTag()
    tx = validator_set.addRoundRewardMock(agents[:2], rewards, round_tag)
    factor = 500
    reward0 = rewards[0] * coins[0] / (coins[0] + powers[0] * factor)
    reward1 = rewards[1] * coins[1] / (coins[1] + powers[1] * factor)
    validator_coin_reward0 = reward0 * collateral_state['coin'] // Utils.DENOMINATOR
    validator_coin_reward1 = reward1 * collateral_state['coin'] // Utils.DENOMINATOR
    validator_power_reward0 = rewards[0] * (powers[0] * factor) // (coins[0] + powers[0] * factor)
    validator_power_reward1 = rewards[1] * (powers[1] * factor) // (coins[1] + powers[1] * factor)
    assert tx.events['roundReward'][0]['amount'] == [0, 0]
    assert tx.events['roundReward'][1]['amount'] == [validator_power_reward0, validator_power_reward1]
    assert tx.events['roundReward'][2]['amount'] == [validator_coin_reward0, validator_coin_reward1]


def test_add_round_reward_success_with_no_agent(core_agent, validator_set, candidate_hub, stake_hub, btc_agent):
    agents = accounts[1:4]
    rewards = (1e7, 1e8, 1e8)
    __candidate_register(agents[0])
    __candidate_register(agents[1])
    round_tag = candidate_hub.roundTag()
    tx = validator_set.addRoundRewardMock(agents, rewards, round_tag)
    assert len(tx.events['roundReward']) == 3
    for r in tx.events['roundReward']:
        assert r['amount'] == [0, 0, 0]


def test_add_round_reward_success(core_agent, validator_set, candidate_hub, stake_hub, btc_agent, btc_lst_stake,
                                  hash_power_agent):
    agents = accounts[1:4]
    rewards = (1e8, 1e8, 1e8)
    total_coin = 250
    btc_coin = 10
    total_power = 5
    __candidate_register(agents[0])
    __candidate_register(agents[1])
    stake_hub.setCandidateAmountMap(agents[0], total_coin, total_power, btc_coin * 2)
    stake_hub.setCandidateAmountMap(agents[1], total_coin, total_power, btc_coin)
    core_agent.setCandidateMapAmount(agents[0], total_coin, total_coin)
    core_agent.setCandidateMapAmount(agents[1], total_coin, total_coin)
    btc_agent.setCandidateMap(agents[0], btc_coin * 2, 0)
    btc_agent.setCandidateMap(agents[1], btc_coin, 0)
    _, _, account_rewards, collateral_reward, collateral_state = parse_delegation([{
        "address": agents[0],
        "active": True,
        "coin": [set_delegate(accounts[0], total_coin)],
        "power": [set_delegate(accounts[0], total_power)],
        "btc": [set_delegate(accounts[0], btc_coin * 2)]
    }, {
        "address": agents[1],
        "active": True,
        "coin": [set_delegate(accounts[0], total_coin)],
        "power": [set_delegate(accounts[0], total_power)],
        "btc": [set_delegate(accounts[0], btc_coin)]
    }], 1e8)
    collateral_reward = collateral_reward[1]
    stake_hub.setStateMapDiscount(hash_power_agent.address, 0, 500, collateral_state['power'])
    round_tag = candidate_hub.roundTag()
    tx = validator_set.addRoundRewardMock(agents, rewards, round_tag)
    for index, t in enumerate(tx.events['roundReward']):
        # core
        r = t[0]
        if t['name'] == Web3.keccak(text='CORE').hex():
            assert t['amount'] == [collateral_reward['coin'][agents[0]], collateral_reward['coin'][agents[1]], 0]
            assert t['bonus'] == 0
        # power
        elif t['name'] == Web3.keccak(text='HASHPOWER').hex():
            assert t['amount'] == [collateral_reward['power'][agents[0]], collateral_reward['power'][agents[1]], 0]
            assert t['bonus'] == 0
        # btc
        elif t['name'] == Web3.keccak(text='BTC').hex():
            assert t['amount'] == [collateral_reward['btc'][agents[0]], collateral_reward['btc'][agents[1]], 0]
            assert t['bonus'] == 0


def test_add_round_reward_failed_with_invalid_argument(validator_set):
    agents = accounts[1:4]
    rewards = [1e7, 1e8]
    round_tag = get_current_round()
    with brownie.reverts("the length of validators and rewardList should be equal"):
        validator_set.addRoundRewardMock(agents, rewards, round_tag)


def test_get_coin_score_success(candidate_hub, validator_set, stake_hub, btc_light_client, core_agent,
                                hash_power_agent, btc_agent):
    operators = []
    consensuses = []
    for operator in accounts[6:11]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for i in range(3):
        __delegate_coin_success(operators[i], accounts[i], 0, required_coin_deposit + i)
    turn_round()
    turn_round(consensuses, tx_fee=TX_FEE)
    for i in range(3, 5):
        __delegate_coin_success(operators[i], accounts[i], 0, required_coin_deposit + i)
    candidate_hub.getScoreMock(operators, get_current_round())
    scores = candidate_hub.getScores()

    discount = HardCap.CORE_HARD_CAP * sum(scores) * Utils.DENOMINATOR // (HardCap.SUM_HARD_CAP * sum(scores))
    assert len(scores) == 5
    for i in range(5):
        expected_score = required_coin_deposit + i
        assert expected_score == scores[i]
        assert stake_hub.candidateScoreMap(operators[i]) == scores[i]
    assert stake_hub.stateMap(core_agent.address)['discount'] == discount


def test_get_power_score_success(candidate_hub, validator_set, stake_hub, btc_light_client, hash_power_agent):
    operators = []
    consensuses = []
    for operator in accounts[6:11]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    power_value = 5
    for i in range(power_value):
        btc_light_client.setMiners(get_current_round() - power_value, operators[i], [accounts[i]])
    turn_round()
    turn_round(consensuses, tx_fee=TX_FEE)
    power_factor = 500
    candidate_hub.getScoreMock(operators, get_current_round())
    scores = candidate_hub.getScores()
    discount = HardCap.POWER_HARD_CAP * sum(scores) * Utils.DENOMINATOR // (HardCap.SUM_HARD_CAP * power_factor * power_value)
    assert len(scores) == power_value
    for i in range(power_value):
        assert power_factor == scores[i]
        assert stake_hub.candidateScoreMap(operators[i]) == scores[i]
    assert stake_hub.stateMap(hash_power_agent.address)['discount'] == discount


def test_get_coin_and_power_score_success(candidate_hub, validator_set, stake_hub, btc_light_client, hash_power_agent):
    operators = []
    consensuses = []
    for operator in accounts[6:11]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for i in range(3):
        __delegate_coin_success(operators[i], accounts[i], 0, required_coin_deposit + i)
    for i in range(5):
        btc_light_client.setMiners(get_current_round() - 5, operators[i], [accounts[i]])
    turn_round()
    turn_round(consensuses, tx_fee=TX_FEE)
    for i in range(3, 5):
        __delegate_coin_success(operators[i], accounts[i], 0, required_coin_deposit + i)
    power = 500
    candidate_hub.getScoreMock(operators, get_current_round())
    scores = candidate_hub.getScores()
    discount = HardCap.POWER_HARD_CAP * sum(scores) * Utils.DENOMINATOR // (HardCap.SUM_HARD_CAP * power * 5)
    assert len(scores) == 5
    for i in range(5):
        expected_score = (required_coin_deposit + i) + power
        assert expected_score == scores[i]
        assert stake_hub.candidateScoreMap(operators[i]) == scores[i]
    assert stake_hub.stateMap(hash_power_agent.address)['discount'] == discount


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
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], required_coin_deposit)],
        "btc": []

    }], actual_block_reward * 90 // 100)
    delegator_tracker = get_tracker(accounts[0])
    reward_amount_m = core_agent.collectCoinRewardMock(operators[0], accounts[0], {'from': accounts[0]}).return_value
    result = core_agent.getDelegator(operators[0], accounts[0]).dict()
    assert account_rewards[accounts[0]] * 4 == reward_amount_m
    assert delegator_tracker.delta() == 0
    assert result['stakedAmount'] == MIN_INIT_DELEGATE_VALUE
    assert required_coin_deposit == result['realtimeAmount']
    assert result['changeRound'] == get_current_round()


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


def test_delegate_coin_failed_with_invalid_candidate(core_agent):
    agent = accounts[1]
    delegator = accounts[2]

    error_msg = encode_args_with_signature("InactiveCandidate(address)", [agent.address])
    with brownie.reverts(f"{error_msg}"):
        core_agent.delegateCoin(agent, {'from': delegator, 'value': required_coin_deposit - 1})


def test_undelegate_coin_success(core_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    __delegate_coin_success(agent, delegator, 0, required_coin_deposit)
    round_tag = core_agent.roundTag()
    __check_coin_delegator(agent, delegator, 0, required_coin_deposit, round_tag, 0)

    turn_round()
    tx = core_agent.undelegateCoin(agent, required_coin_deposit, {'from': delegator})
    expect_event(tx, "undelegatedCoin", {
        'candidate': agent,
        'delegator': delegator,
        'amount': required_coin_deposit
    })
    __check_coin_delegator(agent, delegator, 0, 0, 0, 0)


def test_undelegate_coin_failed_with_no_delegate(core_agent):
    agent = accounts[1]
    delegator = accounts[2]
    __candidate_register(agent)

    with brownie.reverts("no delegator information found"):
        core_agent.undelegateCoin(agent, required_coin_deposit, {'from': delegator})


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


def test_transfer_coin_failed_with_no_delegator_in_source_agent(core_agent):
    agent_source = accounts[1]
    agent_target = accounts[3]
    __candidate_register(agent_source)
    __candidate_register(agent_target)
    delegator = accounts[2]

    with brownie.reverts("no delegator information found"):
        core_agent.transferCoin(agent_source, agent_target, required_coin_deposit, {'from': delegator})


def test_transfer_coin_failed_with_inactive_target_agent(core_agent):
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
    assert actual_block_reward * 2 * (denominator - commission) // denominator // 2 == tracker.delta()


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
    assert expect_reward // 2 == tracker.delta()


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
    assert (expect_reward1 + expect_reward2) // 2 == tracker.delta()


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_stake_and_revert_on_same_round_cancel_or_transfer(core_agent, validator_set, operate):
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': required_coin_deposit})
    if operate == 'undelegate':
        with brownie.reverts("Not enough staked tokens"):
            core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    else:
        with brownie.reverts("Not enough staked tokens"):
            core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_succeeds_after_round_switch(core_agent, validator_set, operate):
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': required_coin_deposit})
    turn_round()
    turn_round()
    if operate == 'undelegate':
        tx = core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
        event = 'undelegatedCoin'
    else:
        tx = core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
        event = 'transferredCoin'
    assert event in tx.events


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_with_same_round_additional_stake_reverts(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    undelegate_amount = delegate_amount + delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    if operate == 'undelegate':
        with brownie.reverts("Not enough staked tokens"):
            core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    else:
        with brownie.reverts("Not enough staked tokens"):
            core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_with_additional_stake_succeeds_after_round_switch(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    undelegate_amount = delegate_amount + delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    if operate == 'undelegate':
        tx = core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
        event = 'undelegatedCoin'
    else:
        tx = core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})
        event = 'transferredCoin'
    assert event in tx.events


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_remaining_stake_includes_current_round_stake(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    undelegate_amount = delegate_amount - required_coin_deposit + 1
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
        with brownie.reverts("Not enough staked tokens"):
            core_agent.undelegateCoin.call(operators[0], required_coin_deposit, {'from': accounts[0]})
        with brownie.reverts("undelegate amount is too small"):
            core_agent.undelegateCoin.call(operators[0], required_coin_deposit - 1, {'from': accounts[0]})
    else:
        tx = core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})
        event = 'transferredCoin'
        __check_coin_delegator(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE - 1,
                               delegate_amount * 2 - undelegate_amount,
                               get_current_round(), undelegate_amount)
        __check_coin_delegator(operators[1], accounts[0], 0, undelegate_amount,
                               get_current_round(), 0)
        with brownie.reverts("Not enough staked tokens"):
            core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
        with brownie.reverts("transfer amount is too small"):
            core_agent.transferCoin(operators[0], operators[1], required_coin_deposit - 1, {'from': accounts[0]})
    assert event in tx.events


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_stake_then_cancel_same_round_on_slashed_validator(core_agent, validator_set, slash_indicator, threshold_type):
    operators = []
    consensuses = []
    delegate_amount = required_coin_deposit * 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    tx = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
    turn_round()
    tx = core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    assert 'undelegatedCoin' in tx.events
    tx = core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
    assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_cancel_current_round_stake_on_validator_with_different_status(core_agent, validator_set, candidate_hub,
                                                                       validator_type):
    operators = []
    consensuses = []
    delegate_amount = required_coin_deposit * 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})


def test_cancel_current_round_stake_on_candidate(core_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    delegate_amount = required_coin_deposit * 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], required_coin_deposit, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
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


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_current_round_stake_and_transferred_amount(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    undelegate_amount = delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})
    if operate == 'undelegate':
        with brownie.reverts("Not enough staked tokens"):
            core_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    else:
        with brownie.reverts("Not enough staked tokens"):
            core_agent.transferCoin(operators[1], operators[2], undelegate_amount, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_amount_transferred_in_current_round(core_agent, validator_set, operate):
    delegate_amount = required_coin_deposit * 10
    undelegate_amount = delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    core_agent.delegateCoin(operators[1], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    core_agent.transferCoin(operators[0], operators[1], undelegate_amount, {'from': accounts[0]})
    if operate == 'undelegate':
        with brownie.reverts("Not enough staked tokens"):
            core_agent.undelegateCoin(operators[1], delegate_amount + 1, {'from': accounts[0]})
        tx = core_agent.undelegateCoin(operators[1], delegate_amount, {'from': accounts[0]})
        event = 'undelegatedCoin'
    else:
        with brownie.reverts("Not enough staked tokens"):
            core_agent.transferCoin(operators[1], operators[2], delegate_amount + 1, {'from': accounts[0]})
        tx = core_agent.transferCoin(operators[1], operators[2], undelegate_amount, {'from': accounts[0]})
        event = 'transferredCoin'
    assert event in tx.events


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
        with brownie.reverts("undelegate amount is too small"):
            core_agent.undelegateCoin(operators[1], 0, {'from': accounts[0]})
    else:
        with brownie.reverts("transfer amount is too small"):
            core_agent.transferCoin(operators[1], operators[2], 0, {'from': accounts[0]})


def test_current_delegate_map(core_agent, validator_set):
    turn_round()
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator_map(operators[0], accounts[0], 0, delegate_amount, get_current_round(), 0)
    turn_round()
    __check_coin_delegator_map(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator_map(operators[0], accounts[0], delegate_amount, delegate_amount * 2, get_current_round(), 0)
    core_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[0]})
    __check_coin_delegator_map(operators[0], accounts[0], 0, delegate_amount, get_current_round(), 0)
    turn_round()
    __check_coin_delegator_map(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    transfer_amount = delegate_amount // 2
    core_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    __check_coin_delegator_map(operators[0], accounts[0], transfer_amount, transfer_amount, get_current_round(),
                               transfer_amount)
    turn_round()
    __check_coin_delegator_map(operators[2], accounts[0], 0, transfer_amount, get_current_round() - 1, 0)
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    core_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    __check_coin_delegator_map(operators[2], accounts[0], transfer_amount - undelegate_amount,
                               transfer_amount - undelegate_amount, get_current_round(), 0)


def test_revert_on_cancel_amount_exceeding_stake(core_agent, validator_set):
    turn_round()
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    transfer_amount = delegate_amount // 2
    core_agent.transferCoin(operators[0], operators[1], delegate_amount, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], transfer_amount + MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})


def test_check_delegate_map_on_full_unstake(core_agent, validator_set):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    undelegate_amount = delegate_amount - required_coin_deposit
    core_agent.transferCoin(operators[0], operators[1], required_coin_deposit, {'from': accounts[0]})
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    __check_coin_delegator_map(operators[0], accounts[0], 0, 0, get_current_round(), required_coin_deposit)
    candidates_length = len(__get_candidate_list_by_delegator(accounts[0]))
    assert candidates_length == 2
    turn_round()
    stake_hub_claim_reward(accounts[0])
    core_agent.undelegateCoin(operators[1], required_coin_deposit, {'from': accounts[0]})
    candidates_length = len(__get_candidate_list_by_delegator(accounts[0]))
    assert candidates_length == 0


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


@pytest.mark.parametrize("operate", ['delegateCoin', 'undelegateCoin', 'transferCoin'])
def test_successful_proxy_method_call(core_agent, validator_set, operate, pledge_agent):
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    pledge_agent.delegateCoinOld(operators[1], {"value": Web3.to_wei(100000, 'ether')})
    tx = core_agent.proxyDelegate(operators[0], accounts[0], {'from': pledge_agent, 'value': delegate_amount})
    assert tx.events['delegatedCoin']['amount'] == delegate_amount
    coin_reward = COIN_REWARD
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


@pytest.mark.parametrize("operate", ['delegate', 'undelegate', 'transfer', 'claim'])
def test_change_round_success_after_additional_stake(core_agent, validator_set, operate):
    turn_round()
    delegate_amount = required_coin_deposit * 10
    operators, consensuses = __register_candidates(accounts[2:5])
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    turn_round()
    __check_coin_delegator_map(operators[0], accounts[0], 0, delegate_amount, get_current_round() - 1, 0)
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    core_agent.delegateCoin(operators[0], {'from': accounts[0], 'value': delegate_amount})
    __check_coin_delegator_map(operators[0], accounts[0], delegate_amount, delegate_amount * 3, get_current_round(), 0)
    turn_round(consensuses)
    __check_coin_delegator_map(operators[0], accounts[0], delegate_amount, delegate_amount * 3, get_current_round() - 1,
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
    __check_coin_delegator_map(operators[0], accounts[0], stake_amount, real_amount, get_current_round(),
                               transfer_amount)


def test_init_hard_fork_round_success(core_agent, pledge_agent):
    operators, consensuses = __register_candidates(accounts[2:5])
    pledge_agent.delegateCoinOld(operators[1], {"value": Web3.to_wei(100000, 'ether')})
    candidates = [accounts[0], accounts[1]]
    amounts = [1000, 2000]
    real_amounts = [4000, 5000]
    core_agent._initializeFromPledgeAgent(candidates, amounts, real_amounts, {'from': pledge_agent})
    for index, c in enumerate(candidates):
        assert core_agent.candidateMap(c)['amount'] == amounts[index]
        assert core_agent.candidateMap(c)['realtimeAmount'] == real_amounts[index]


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
    __check_coin_delegator_map(candidate, delegator0, real_amount, real_amount, get_current_round(), 0)
    assert __get_candidate_list_by_delegator(delegator0)[0] == candidate
    assert core_agent.delegatorMap(delegator0) == real_amount
    # scenario 2: No reward settlement
    staked_amount = MIN_INIT_DELEGATE_VALUE * 10 + 1
    transferred_amount = MIN_INIT_DELEGATE_VALUE * 5 + 1
    real_amount = MIN_INIT_DELEGATE_VALUE * 20 + 1

    core_agent.moveData(candidate, delegator1, staked_amount, transferred_amount, get_current_round(),
                        {'from': pledge_agent, 'value': real_amount})
    __check_coin_delegator_map(candidate, delegator1, staked_amount, real_amount, get_current_round() - 1,
                               transferred_amount)
    assert __get_candidate_list_by_delegator(delegator1)[0] == candidate
    assert core_agent.delegatorMap(delegator1) == real_amount


def test_function_call_access_control(core_agent):
    # Only the pledge agent can be called
    with brownie.reverts("the sender must be PledgeAgent contract"):
        core_agent._initializeFromPledgeAgent([], [], [], {'from': accounts[0]})
    with brownie.reverts("the sender must be PledgeAgent contract"):
        core_agent.moveData(accounts[0], accounts[0], 0, 0, 0, {'from': accounts[0], 'value': 1000})
    # Only the Stake Hub can be called
    with brownie.reverts("the msg sender must be stake hub contract"):
        core_agent.claimReward(accounts[0])
    with brownie.reverts("the msg sender must be stake hub contract"):
        core_agent.distributeReward([], [], 0)


def __get_delegator_info(candidate, delegator):
    delegator_info = CoreAgentMock[0].getDelegator(candidate, delegator)
    return delegator_info


def __get_candidate_list_by_delegator(delegator):
    candidate_info = CoreAgentMock[0].getCandidateListByDelegator(delegator)
    return candidate_info


def __check_coin_delegator_map(candidate, delegator, staked_amount, real_amount, change_round, transferred_amount):
    c_delegator = __get_delegator_info(candidate, delegator)
    assert c_delegator['stakedAmount'] == staked_amount
    assert c_delegator['realtimeAmount'] == real_amount
    assert c_delegator['changeRound'] == change_round
    assert c_delegator['transferredAmount'] == transferred_amount


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
