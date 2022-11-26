import pytest
from web3 import Web3
from brownie import accounts
from .common import register_candidate, turn_round
from .utils import get_tracker
from .calc_reward import parse_delegation, set_delegate


MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0

ONE_ETHER = Web3.toWei(1, 'ether')
TX_FEE = 100


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-2].transfer(validator_set.address, Web3.toWei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_min_init_delegate_value(min_init_delegate_value):
    global MIN_INIT_DELEGATE_VALUE
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set):
    global BLOCK_REWARD
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)


@pytest.fixture()
def set_candidate():
    operator = accounts[1]
    consensus = operator
    register_candidate(consensus=consensus, operator=operator)
    return consensus, operator


@pytest.mark.parametrize("claim_type", ["claim", "delegate", "undelegate", "transfer"])
def test_delegate_once(pledge_agent, validator_set, claim_type):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensus in validator_set.getValidators()

    turn_round([consensus])
    tracker = get_tracker(accounts[0])

    if claim_type == "claim":
        pledge_agent.claimReward([operator])
        assert tracker.delta() == BLOCK_REWARD / 2
    elif claim_type == "delegate":
        pledge_agent.delegateCoin(operator, {"value": 100})
        assert tracker.delta() == (BLOCK_REWARD / 2 - 100)
    elif claim_type == "undelegate":
        pledge_agent.undelegateCoin(operator)
        assert tracker.delta() == (BLOCK_REWARD / 2 + MIN_INIT_DELEGATE_VALUE)
    elif claim_type == "transfer":
        register_candidate(operator=accounts[2])
        pledge_agent.transferCoin(operator, accounts[2])
        assert tracker.delta() == BLOCK_REWARD / 2


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2one_agent_twice_in_different_rounds(pledge_agent, set_candidate, internal):
    consensus, operator = set_candidate
    turn_round()

    for _ in range(2):
        pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round(round_count=internal)
    if internal == 0:
        turn_round()
    turn_round([consensus])

    tracker = get_tracker(accounts[0])
    pledge_agent.claimReward([operator])
    assert tracker.delta() == BLOCK_REWARD / 2


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2two_agents_in_different_rounds(pledge_agent, internal):
    operators = []
    consensuses = []

    for operator in accounts[1:3]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))

    turn_round()

    for operator in operators:
        pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round(round_count=internal)

    if internal == 0:
        turn_round()

    turn_round(consensuses)

    tracker = get_tracker(accounts[0])
    pledge_agent.claimReward(operators)
    assert tracker.delta() == BLOCK_REWARD


def test_claim_reward_after_transfer_to_candidate(pledge_agent, candidate_hub, validator_set):
    operators = []
    consensuses = []

    for operator in accounts[1:4]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.refuseDelegate({'from': operators[2]})

    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 2
    assert operators[2] not in validators

    pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    pledge_agent.delegateCoin(operators[1], {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)

    tracker = get_tracker(accounts[0])

    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.transferCoin(operators[1], operators[2])
    candidate_hub.refuseDelegate({'from': operators[2]})

    turn_round(consensuses, round_count=2)

    pledge_agent.claimReward(operators)
    assert tracker.delta() == BLOCK_REWARD * 2


def test_claim_reward_after_transfer_to_validator(pledge_agent, validator_set):
    operators = []
    consensuses = []

    for operator in accounts[1:4]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))

    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3

    pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    pledge_agent.delegateCoin(operators[1], {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)

    tracker = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[1], operators[2])
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators)
    assert tracker.delta() == BLOCK_REWARD * 5 / 2


def test_claim_reward_after_transfer_to_duplicated_validator(pledge_agent):
    operators = []
    consensuses = []
    clients = accounts[:2]

    for operator in accounts[2:4]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
        for client in clients:
            pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, "from": client})

    turn_round()

    pledge_agent.transferCoin(operators[0], operators[1], {"from": clients[0]})
    turn_round(consensuses, round_count=2)

    _, delegator_reward1 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE), set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE), set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }], BLOCK_REWARD // 2)

    _, delegator_reward2 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE * 2), set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }], BLOCK_REWARD // 2)

    tracker1 = get_tracker(clients[0])
    tracker2 = get_tracker(clients[1])
    for client in clients:
        pledge_agent.claimReward(operators, {'from': client})

    assert tracker1.delta() == delegator_reward1[clients[0]] // 2 + delegator_reward2[clients[0]]
    assert tracker2.delta() == delegator_reward1[clients[1]] + delegator_reward2[clients[1]]


def test_undelegate_coin_next_round(pledge_agent):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    pledge_agent.undelegateCoin(operator)
    turn_round([consensus])

    reward_sum, _ = pledge_agent.claimReward.call([operator])
    assert reward_sum == 0


def test_undelegate_coin_reward(pledge_agent):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    pledge_agent.undelegateCoin(operator)
    tx = turn_round([consensus])
    assert "receiveDeposit" in tx.events
    event = tx.events['receiveDeposit'][-1]
    assert event['from'] == pledge_agent.address
    assert event['amount'] == BLOCK_REWARD // 2











