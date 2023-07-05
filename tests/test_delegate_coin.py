import random

import brownie
import pytest
import web3.contract
from web3 import Web3
from brownie import accounts, PledgeAgentProxy
from .common import register_candidate, turn_round
from .utils import get_tracker, expect_event, encode_args_with_signature
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


@pytest.fixture(scope="module", autouse=True)
def set_round_tag(candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)


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
    total_reward = BLOCK_REWARD // 2
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
    expect_reward = total_reward * 5
    assert tracker.delta() == expect_reward


def test_claim_reward_after_transfer_to_validator(pledge_agent, validator_set):
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2

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
    expect_reward = total_reward * 6
    assert tracker.delta() == expect_reward


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
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE),
                 set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE),
                 set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
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
        "coin": [set_delegate(clients[0], MIN_INIT_DELEGATE_VALUE * 2),
                 set_delegate(clients[1], MIN_INIT_DELEGATE_VALUE, True)],
        "power": []
    }], BLOCK_REWARD // 2)

    tracker1 = get_tracker(clients[0])
    tracker2 = get_tracker(clients[1])
    for client in clients:
        pledge_agent.claimReward(operators, {'from': client})

    assert tracker1.delta() == delegator_reward1[clients[0]] // 2 + delegator_reward2[clients[0]] + BLOCK_REWARD // 4
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


def test_claim_reward_failed(pledge_agent):
    pledge_agent_proxy = PledgeAgentProxy.deploy(pledge_agent.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    tx = pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "delegate", {"success": True})
    turn_round()
    turn_round([consensus])
    assert pledge_agent.rewardMap(pledge_agent_proxy.address) == 0
    reward = pledge_agent_proxy.claimReward.call([operator])
    assert reward == BLOCK_REWARD // 2
    tx = pledge_agent_proxy.claimReward([operator])
    expect_event(tx, "claim", {
        "reward": BLOCK_REWARD // 2,
        "allClaimed": True,
    })
    expect_event(tx, "claimedReward", {
        "delegator": pledge_agent_proxy.address,
        "operator": pledge_agent_proxy.address,
        "amount": BLOCK_REWARD // 2,
        "success": False
    })
    assert pledge_agent.rewardMap(pledge_agent_proxy.address) == BLOCK_REWARD // 2


def test_remain_amount_small(pledge_agent, validator_set):
    undelegate_value = MIN_INIT_DELEGATE_VALUE + 99
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensus in validator_set.getValidators()
    with brownie.reverts("remain amount is too small"):
        pledge_agent.undelegateCoin(operator, undelegate_value)


def test_undelegate_amount_small(pledge_agent, validator_set):
    undelegate_value = MIN_INIT_DELEGATE_VALUE - 1
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert consensus in validator_set.getValidators()
    with brownie.reverts("undelegate amount is too small"):
        pledge_agent.undelegateCoin(operator, undelegate_value)


def test_transfer_remain_amount_small(pledge_agent, validator_set):
    operators = []
    for operator in accounts[2:5]:
        operators.append(operator)
        register_candidate(operator=operator)
    operator = operators[0]
    undelegate_value = MIN_INIT_DELEGATE_VALUE + 99
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert len(validator_set.getValidators()) == 3
    with brownie.reverts("remain amount is too small"):
        pledge_agent.transferCoin(operators[0], operators[1], undelegate_value)


def test_transfer_undelegate_amount_small(pledge_agent, validator_set):
    undelegate_value = MIN_INIT_DELEGATE_VALUE - 1
    operators = []
    for operator in accounts[2:5]:
        operators.append(operator)
        register_candidate(operator=operator)
    operator = operators[0]
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    assert len(validator_set.getValidators()) == 3
    with brownie.reverts("undelegate amount is too small"):
        pledge_agent.transferCoin(operators[0], operators[1], undelegate_value)


def test_claim_reward_after_undelegate_one_round(pledge_agent, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, 0, {'from': accounts[1]})
    delegator_info0 = pledge_agent.getDelegator(operator, accounts[0])
    reward_info = pledge_agent.getReward(operator, delegator_info0['rewardIndex'])
    assert tracker0.delta() == undelegate_amount
    assert tracker1.delta() == delegate_amount
    remain_pledged_amount = delegate_amount - undelegate_amount
    total_pledged_amount = delegate_amount * 2
    assert reward_info['coin'] == remain_pledged_amount
    assert reward_info['score'] == total_pledged_amount
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    deduction_reward = total_reward * (delegate_amount * 2 - remain_pledged_amount) // (delegate_amount * 2)
    assert tracker0.delta() == total_reward - deduction_reward
    assert tracker1.delta() == 0


def test_claim_reward_after_undelegate_multiple_round(pledge_agent, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    undelegate_amount1 = undelegate_amount // 2
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[1]})
    delegator_info0 = pledge_agent.getDelegator(operator, accounts[0])
    reward_info = pledge_agent.getReward(operator, delegator_info0['rewardIndex'])
    assert tracker0.delta() == undelegate_amount
    assert tracker1.delta() == undelegate_amount1
    remain_pledged_amount0 = delegate_amount - undelegate_amount
    remain_pledged_amount1 = delegate_amount - undelegate_amount1
    total_pledged_amount = delegate_amount * 2
    total_undelegate_amount = undelegate_amount + undelegate_amount1
    assert reward_info['coin'] == total_pledged_amount - total_undelegate_amount
    assert reward_info['score'] == total_pledged_amount
    turn_round([consensus], round_count=1)
    deduction_reward = total_reward * total_undelegate_amount // total_pledged_amount
    distributed_reward = total_reward - deduction_reward
    expect_reward0 = total_reward * remain_pledged_amount0 // total_pledged_amount
    expect_reward1 = distributed_reward - expect_reward0
    pledge_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, 0, {'from': accounts[1]})
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    remain_pledged_amount0 -= undelegate_amount1
    total_pledged_amount -= total_undelegate_amount
    deduction_reward0 = total_reward * (undelegate_amount1 + remain_pledged_amount1) // total_pledged_amount
    distributed_reward0 = total_reward - deduction_reward0
    expect_reward0 += distributed_reward0
    expect_reward1 += 0
    assert tracker0.delta() == expect_reward0 + undelegate_amount1
    assert tracker1.delta() == expect_reward1 + remain_pledged_amount1


def test_claim_reward_after_undelegate_coin_partially(pledge_agent, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 8
    undelegate_amount = delegate_amount // 5
    undelegate_amount1 = delegate_amount // 7
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount
    remain_pledged_amount = delegate_amount - undelegate_amount
    total_pledged_amount = delegate_amount
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    deduction_reward = total_reward * (total_pledged_amount - remain_pledged_amount) // total_pledged_amount
    assert tracker0.delta() == total_reward - deduction_reward
    pledge_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    remain_pledged_amount -= undelegate_amount1
    total_pledged_amount -= undelegate_amount
    delegator_info0 = pledge_agent.getDelegator(operator, accounts[0])
    reward_info = pledge_agent.getReward(operator, delegator_info0['rewardIndex'])
    assert reward_info['coin'] == remain_pledged_amount
    assert reward_info['score'] == total_pledged_amount
    assert delegator_info0['newDeposit'] == remain_pledged_amount
    tracker0.update_height()
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    deduction_reward = total_reward * (total_pledged_amount - remain_pledged_amount) // total_pledged_amount
    assert tracker0.delta() == total_reward - deduction_reward
    pledge_agent.undelegateCoin(operator, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == remain_pledged_amount


def test_multi_delegators_claim_reward_after_undelegate_coin_partially(pledge_agent, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount0 = delegate_amount // 2
    undelegate_amount1 = undelegate_amount0 // 2
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.undelegateCoin(operator, undelegate_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[1]})
    total_pledged_amount = delegate_amount * 2
    turn_round([consensus], round_count=1)
    tracker0.update_height()
    tracker1.update_height()
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    deduction_reward = total_reward * (undelegate_amount0 + undelegate_amount1) // total_pledged_amount
    actual_reward0 = total_reward * undelegate_amount0 // total_pledged_amount
    total_reward -= deduction_reward
    assert tracker0.delta() == actual_reward0
    assert tracker1.delta() == total_reward - actual_reward0


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_withdraw_principal(pledge_agent, validator_set, undelegate_type):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 8
    undelegate_amount = delegate_amount // 5
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
    register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount


def test_claim_rewards_for_multiple_validators(pledge_agent, validator_set):
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount // 3
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], 0, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    deduction_reward = total_reward * undelegate_amount // delegate_amount
    actual_reward = total_reward - deduction_reward + total_reward
    assert tracker0.delta() == actual_reward


def test_claim_rewards_each_round_after_undelegate_or_delegate(pledge_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    assert tracker0.delta() == 0 - delegate_amount
    assert tracker1.delta() == 0 - delegate_amount * 2
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == 0 - delegate_amount
    assert tracker1.delta() == 0
    turn_round(consensuses)
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == total_reward // 2 + undelegate_amount
    assert tracker1.delta() == total_reward - total_reward // 2 + total_reward
    remain_pledged_amount = delegate_amount * 2 - undelegate_amount
    total_pledged_amount = delegate_amount * 3
    turn_round(consensuses)
    deduction_reward0 = total_reward * undelegate_amount // total_pledged_amount
    distributed_reward = total_reward - deduction_reward0
    actual_reward0 = total_reward * remain_pledged_amount // total_pledged_amount
    actual_reward1 = distributed_reward - actual_reward0
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == actual_reward0
    assert tracker1.delta() == actual_reward1 + total_reward


def test_auto_reward_distribution_on_undelegate(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    operator1 = accounts[4]
    delegate_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    consensus = register_candidate(operator=operator)
    consensus1 = register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount0, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator1, {"value": delegate_amount0, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus1, consensus])
    pledge_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, {'from': accounts[1]})
    account1_reward = total_reward * delegate_amount0 // (delegate_amount0 + MIN_INIT_DELEGATE_VALUE)
    assert tracker0.delta() == account1_reward + MIN_INIT_DELEGATE_VALUE
    assert tracker1.delta() == total_reward - account1_reward + MIN_INIT_DELEGATE_VALUE


def test_undelegate_claim_principal_for_candidate_node(pledge_agent, validator_set, candidate_hub):
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[2], {"value": DELEGATE_VALUE, 'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tracker0.delta() == DELEGATE_VALUE
    turn_round(consensuses, round_count=1)
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.delegateCoin(operators[2], {"value": DELEGATE_VALUE * 5, 'from': accounts[0]})
    assert tracker0.delta() == 0 - DELEGATE_VALUE * 5
    turn_round(consensuses, round_count=1)
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    total_delegate_amount = DELEGATE_VALUE * 5
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    total_reward = BLOCK_REWARD // 2
    expect_reward = total_reward - total_reward * undelegate_amount // total_delegate_amount
    tracker0.update_height()
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == expect_reward
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round(consensuses, round_count=1)
    tracker0.update_height()
    total_delegate_amount -= undelegate_amount
    expect_reward = total_reward * (total_delegate_amount - MIN_INIT_DELEGATE_VALUE) // total_delegate_amount
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == expect_reward


def test_undelegate_claim_principal_for_unregister_node(pledge_agent, validator_set, candidate_hub):
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 2
    operator = accounts[2]
    operator1 = accounts[3]
    tracker0 = get_tracker(accounts[0])
    consensus = register_candidate(operator=operator)
    register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": DELEGATE_VALUE, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 1
    assert operator not in validators
    tracker0.update_height()
    pledge_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    turn_round([consensus], round_count=3)
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": DELEGATE_VALUE, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    pledge_agent.undelegateCoin(operator, DELEGATE_VALUE + MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round([consensus], round_count=2)
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0 - DELEGATE_VALUE + DELEGATE_VALUE + MIN_INIT_DELEGATE_VALUE
    turn_round([consensus])
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_transfer_with_partial_undelegate_and_claimed_rewards(pledge_agent, validator_set, candidate_hub,
                                                              undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    undelegate_amont = delegate_amount // 3
    if undelegate_type == 'all':
        undelegate_amont = delegate_amount
    operators = []
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    operator = operators[0]
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[2]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amont, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount, {'from': accounts[2]})
    turn_round(consensuses, round_count=1)
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    remain_pledged_amount -= undelegate_amont
    expect_reward = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker1.delta() == expect_reward


def test_transfer_auto_claim_rewards(pledge_agent, candidate_hub, validator_set):
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 5
    TRANSFER_VALUE = DELEGATE_VALUE // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3
    pledge_agent.delegateCoin(operators[0], {"value": DELEGATE_VALUE, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": DELEGATE_VALUE, 'from': accounts[1]})
    turn_round()
    total_reward = BLOCK_REWARD // 2
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[0], operators[2], TRANSFER_VALUE)
    assert tracker0.delta() == total_reward // 2
    assert tracker1.delta() == 0
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[0], operators[2], 0)
    assert tracker0.delta() == total_reward // 2


def test_transfer_with_auto_claim_of_previous_rewards(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 4
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 4
    total_pledged_amount1 = delegate_amount
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 3, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})

    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[0], delegate_amount, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount, {'from': accounts[0]})
    operation_total_amount0 = transfer_amount + transfer_amount
    operation_total_amount1 = delegate_amount
    remain_pledged_amount0 -= transfer_amount * 2
    operation_transfer_reward0 = total_reward * operation_total_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward - total_reward * (
            total_pledged_amount1 - operation_total_amount1) // total_pledged_amount1
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1
    assert tracker0.delta() == total_transfer_reward


def test_claim_reward_after_transfer_coin(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    total_reward = BLOCK_REWARD // 2
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    total_pledged_amount = delegate_amount * 3
    transfer_expect_reward0 = total_reward * transfer_amount // total_pledged_amount
    expect_reward0 = transfer_expect_reward0 + total_reward * (
            delegate_amount - transfer_amount) // total_pledged_amount
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == total_reward - expect_reward0


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_transfer_coin_to_active_validator(pledge_agent, validator_set, candidate_hub, validator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    consensuses = []
    validator_count = 2
    is_validator = False
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    else:
        validator_count = 3
        is_validator = True
    turn_round()
    validators = validator_set.getValidators()
    assert validator_set.isValidator(consensuses[0]) == is_validator
    assert len(validators) == validator_count
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount
    assert delegator_info2['newDeposit'] == 0
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount - transfer_amount
    assert delegator_info2['newDeposit'] == transfer_amount
    pledge_agent.transferCoin(operators[0], operators[2], delegate_amount - transfer_amount)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == 0
    assert delegator_info2['newDeposit'] == delegate_amount


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister'])
def test_transfer_to_unregister_and_candidate_validator(pledge_agent, candidate_hub, validator_set, validator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    operator = accounts[2]
    operator1 = accounts[3]
    register_candidate(operator=operator)
    register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operator1})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operator1})
    turn_round()
    error_msg = encode_args_with_signature("InactiveAgent(address)", [operator1.address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.transferCoin(operator, operator1, transfer_amount, {"from": accounts[0]})


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_transfer_and_undelegate_within_validator(pledge_agent, candidate_hub, validator_set, undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    delegate_amount1 = delegate_amount * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount1
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    operator = operators[0]
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount1, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses, round_count=1)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    operation_total_amount = transfer_amount + undelegate_amount
    remain_pledged_amount -= transfer_amount
    transfer_expect_reward0 = total_reward * operation_total_amount // total_pledged_amount
    expect_reward0 = transfer_expect_reward0 * transfer_amount // operation_total_amount + total_reward * remain_pledged_amount // total_pledged_amount
    expect_reward1 = 0
    if undelegate_type == 'part':
        deduction_reward = total_reward * undelegate_amount // total_pledged_amount
        expect_reward1 = total_reward - deduction_reward - expect_reward0
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1


@pytest.mark.parametrize("transfer_type", ['all', 'part'])
def test_transfer_coin_within_validator(pledge_agent, candidate_hub, validator_set, transfer_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 4
    if transfer_type == 'all':
        transfer_amount0 = delegate_amount
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    operator = operators[0]
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0)
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount1, {'from': accounts[1]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses, round_count=1)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    operation_total_amount = transfer_amount0 + transfer_amount1
    remain_pledged_amount0 -= transfer_amount0
    transfer_reward = total_reward * operation_total_amount // total_pledged_amount
    transfer_expect_reward0 = transfer_reward * transfer_amount0 // operation_total_amount
    transfer_expect_reward1 = transfer_reward * transfer_amount1 // operation_total_amount
    remain_expect_reward0 = total_reward * remain_pledged_amount0 // total_pledged_amount
    expect_reward1 = total_reward - transfer_reward - remain_expect_reward0 + transfer_expect_reward1
    assert tracker0.delta() == remain_expect_reward0 + transfer_expect_reward0
    assert tracker1.delta() == expect_reward1


def test_transfer_and_undelegate_multiple_validators(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 4
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 4
    total_pledged_amount1 = delegate_amount * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 3, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[2]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[1], operators[0], delegate_amount, {'from': accounts[2]})
    pledge_agent.undelegateCoin(operators[1], delegate_amount, {'from': accounts[1]})
    turn_round(consensuses, round_count=1)

    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    transfer_reward = pledge_agent.getTransferReward(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward(operators, {'from': accounts[2]})
    operation_total_amount0 = transfer_amount + delegate_amount
    operation_total_amount1 = delegate_amount + delegate_amount
    operation_amount = operation_total_amount0 + operation_total_amount1
    remain_pledged_amount0 -= transfer_amount
    operation_transfer_reward0 = total_reward * operation_total_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward - total_reward * (
            total_pledged_amount1 - operation_total_amount1) // total_pledged_amount1
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1
    transfer_reward0 = total_transfer_reward * transfer_amount // operation_amount
    remain_reward0 = total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert transfer_reward == transfer_reward0
    assert pledge_agent.getTransferReward(accounts[0]) == 0
    expect_reward0 = transfer_reward0 + remain_reward0
    expect_reward1 = total_reward - operation_transfer_reward0 - remain_reward0 + total_reward - \
                     operation_transfer_reward1
    expect_reward2 = total_transfer_reward * delegate_amount // operation_amount
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    assert tracker2.delta() == expect_reward2


def test_transfer_coin_multiple_validators(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 8
    transfer_amount1 = delegate_amount // 4
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    total_pledged_amount1 = delegate_amount * 2.5
    total_pledged_amount2 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[2]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 1.5, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[0], delegate_amount // 2, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount1, {'from': accounts[2]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    transfer_reward = pledge_agent.getTransferReward(accounts[0])

    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward(operators, {'from': accounts[2]})
    operation_amount = transfer_amount0 + delegate_amount // 2 + transfer_amount1
    remain_pledged_amount0 -= transfer_amount0
    operation_transfer_reward0 = total_reward * transfer_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward * delegate_amount // 2 // total_pledged_amount1
    operation_transfer_reward2 = total_reward * transfer_amount1 // total_pledged_amount2
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1 + operation_transfer_reward2
    transfer_reward0 = total_transfer_reward * transfer_amount0 // operation_amount
    remain_reward0 = total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert transfer_reward == transfer_reward0
    expect_reward0 = transfer_reward0 + remain_reward0
    expect_reward1 = total_transfer_reward * delegate_amount // 2 // operation_amount + total_reward * delegate_amount // 2 // total_pledged_amount1
    expect_reward2 = total_transfer_reward * transfer_amount1 // operation_amount + total_reward * (
            delegate_amount - transfer_amount1) // total_pledged_amount2
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    assert tracker2.delta() == expect_reward2


@pytest.mark.parametrize("operator_info,",
                         [['part_transfer', 'transfer', 'undelegate'],
                          ['transfer', 'transfer', 'part_undelegate'],
                          ['transfer', 'part_undelegate', 'undelegate'],
                          ['part_transfer', 'transfer', 'transfer'],
                          ['part_transfer', 'undelegate', 'part_transfer'],
                          ['undelegate', 'undelegate', 'undelegate'],
                          ])
def test_claim_reward_after_transfer_and_undelegate(pledge_agent, validator_set, candidate_hub, operator_info):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10

    total_pledged_amount0 = delegate_amount * 3
    total_pledged_amount1 = delegate_amount * 2.5
    total_pledged_amount2 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[2]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 1.5, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    operator_amount_list = []
    for index, operator in enumerate(operator_info):
        operator_amount = delegate_amount
        if 'part' in operator:
            operator_amount = delegate_amount // 6
        if 'transfer' in operator:
            pledge_type = 'transfer'
            pledge_agent.transferCoin(operators[index], operators[3], operator_amount, {'from': accounts[index]})
        else:
            pledge_type = 'undelegate'
            pledge_agent.undelegateCoin(operators[index], operator_amount, {'from': accounts[index]})
        operator_amount_list.append({
            'operator_amount': operator_amount,
            'pledge_type': pledge_type
        })
    operator_amount0 = operator_amount_list[0].get('operator_amount')
    operator_amount1 = operator_amount_list[1].get('operator_amount')
    operator_amount2 = operator_amount_list[2].get('operator_amount')
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward(operators, {'from': accounts[2]})
    operation_amount = operator_amount0 + operator_amount1 + operator_amount2
    operation_transfer_reward0 = total_reward * operator_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward * operator_amount1 // total_pledged_amount1
    operation_transfer_reward2 = total_reward * operator_amount2 // total_pledged_amount2
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1 + operation_transfer_reward2
    expect_reward0 = total_transfer_reward * operator_amount0 // operation_amount + total_reward * (
            delegate_amount - operator_amount0) // total_pledged_amount0
    expect_reward1 = total_transfer_reward * operator_amount1 // operation_amount + total_reward * (
            delegate_amount - operator_amount1) // total_pledged_amount1
    expect_reward2 = total_transfer_reward * operator_amount2 // operation_amount + total_reward * (
            delegate_amount - operator_amount2) // total_pledged_amount2
    if operator_amount_list[0].get('pledge_type') == 'undelegate':
        expect_reward0 = total_reward * (delegate_amount - operator_amount1) // total_pledged_amount1
    if operator_amount_list[1].get('pledge_type') == 'undelegate':
        expect_reward1 = total_reward * (delegate_amount - operator_amount1) // total_pledged_amount1
    if operator_amount_list[2].get('pledge_type') == 'undelegate':
        expect_reward2 = total_reward * (delegate_amount - operator_amount2) // total_pledged_amount2
    print(operator_amount_list)
    print('expect_reward0,expect_reward1,expect_reward2', expect_reward0, expect_reward1, expect_reward2)
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    assert tracker2.delta() == expect_reward2


@pytest.mark.parametrize("additional_amount", [100, 250, 500])
def test_claim_rewards_after_additional_delegate_and_transfer(pledge_agent, validator_set, candidate_hub,
                                                              additional_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    transfer_amount1 = delegate_amount // 2
    transfer_amount2 = delegate_amount // 8
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    total_pledged_amount1 = delegate_amount * 2.5
    total_pledged_amount2 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[2]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 1.5, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[0], transfer_amount1, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount2, {'from': accounts[2]})
    transfer_amount0 = transfer_amount0 - additional_amount
    if transfer_amount0 < 0:
        transfer_amount0 = 0
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    operation_amount = transfer_amount0 + transfer_amount1 + transfer_amount2
    remain_pledged_amount0 -= transfer_amount0
    total_transfer_reward = total_reward * transfer_amount0 // total_pledged_amount0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1 + total_reward * transfer_amount2 // total_pledged_amount2
    expect_reward0 = total_transfer_reward * transfer_amount0 // operation_amount \
                     + total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert tracker0.delta() == expect_reward0


@pytest.mark.parametrize("undelegate_amount", [750, 800, 1000, 1400, 1750])
def test_claim_rewards_after_additional_cancel_delegate_and_transfer(pledge_agent, validator_set, candidate_hub,
                                                                     undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    transfer_amount1 = delegate_amount // 2
    transfer_amount2 = delegate_amount // 8
    additional_amount = delegate_amount
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    total_pledged_amount1 = delegate_amount * 2.5
    total_pledged_amount2 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[2]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 1.5, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    if additional_amount - undelegate_amount > 0:
        transfer_amount0 = transfer_amount0 - (additional_amount - undelegate_amount)
        actual_undelegate_amount = 0
    else:
        actual_undelegate_amount = abs(additional_amount - undelegate_amount)

    operation_total_amount0 = transfer_amount0 + actual_undelegate_amount
    pledge_agent.transferCoin(operators[1], operators[0], transfer_amount1, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount2, {'from': accounts[2]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    operation_amount = transfer_amount0 + transfer_amount1 + transfer_amount2 + actual_undelegate_amount
    remain_pledged_amount0 = remain_pledged_amount0 - transfer_amount0 - actual_undelegate_amount
    total_transfer_reward = total_reward * operation_total_amount0 // total_pledged_amount0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1 + total_reward * transfer_amount2 // total_pledged_amount2
    expect_reward0 = total_transfer_reward * transfer_amount0 // operation_amount \
                     + total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert tracker0.delta() == expect_reward0


def test_claim_reward_after_transfer_and_claim(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 4
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 4
    total_pledged_amount1 = delegate_amount * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 3, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[2]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[1], operators[0], delegate_amount, {'from': accounts[2]})
    pledge_agent.undelegateCoin(operators[1], delegate_amount, {'from': accounts[1]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward(operators, {'from': accounts[2]})
    turn_round(consensuses, round_count=1)

    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward(operators, {'from': accounts[2]})
    operation_total_amount0 = transfer_amount + delegate_amount
    operation_total_amount1 = delegate_amount + delegate_amount
    operation_amount = operation_total_amount0 + operation_total_amount1
    remain_pledged_amount0 -= transfer_amount
    operation_transfer_reward0 = total_reward * operation_total_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward - total_reward * (
            total_pledged_amount1 - operation_total_amount1) // total_pledged_amount1
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1
    transfer_reward0 = total_transfer_reward * transfer_amount // operation_amount
    remain_reward0 = total_reward * remain_pledged_amount0 // total_pledged_amount0

    expect_reward0 = transfer_reward0 + remain_reward0
    expect_reward1 = total_reward - operation_transfer_reward0 - remain_reward0 + total_reward - operation_transfer_reward1
    expect_reward2 = total_transfer_reward * delegate_amount // operation_amount
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    assert tracker2.delta() == expect_reward2


def test_get_delegate_transfer_rewards(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 4
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 4
    total_pledged_amount1 = delegate_amount * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 3, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], delegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], delegate_amount, {'from': accounts[1]})
    pledge_agent.undelegateCoin(operators[1], delegate_amount, {'from': accounts[1]})
    turn_round(consensuses, round_count=1)
    transfer_reward = pledge_agent.getTransferReward(accounts[0])
    operation_total_amount0 = transfer_amount + delegate_amount
    operation_total_amount1 = delegate_amount + delegate_amount
    operation_amount = operation_total_amount0 + operation_total_amount1
    remain_pledged_amount0 -= transfer_amount
    operation_transfer_reward0 = total_reward * operation_total_amount0 // total_pledged_amount0
    operation_transfer_reward1 = total_reward - total_reward * (
            total_pledged_amount1 - operation_total_amount1) // total_pledged_amount1
    total_transfer_reward = operation_transfer_reward0 + operation_transfer_reward1
    transfer_reward0 = total_transfer_reward * transfer_amount // operation_amount
    transfer_reward1 = total_transfer_reward * delegate_amount // operation_amount
    expect_reward0 = transfer_reward0 + transfer_reward1
    assert expect_reward0 == transfer_reward


def test_reward_claim_after_major_slash(pledge_agent, validator_set, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})

    turn_round()
    tx = None
    for count in range(slash_indicator.felonyThreshold()):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker3 = get_tracker(accounts[3])
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {'from': accounts[3]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount, {'from': accounts[1]})
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[3]})
    assert tracker0.delta() == 0
    assert tracker3.delta() == 0
    pledge_agent.claimReward([operators[1]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    pledge_agent.claimReward([operators[2]], {'from': accounts[1]})
    assert tracker1.delta() == total_reward
    assert len(validator_set.getValidators()) == 2


def test_reward_claim_after_minor_slash(pledge_agent, validator_set, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    tx = None
    for count in range(slash_indicator.misdemeanorThreshold()):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    tracker0 = get_tracker(accounts[0])
    tracker3 = get_tracker(accounts[3])
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount, {'from': accounts[1]})
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[3]})
    expect_reward0 = total_reward * (delegate_amount - transfer_amount) // (delegate_amount * 2)
    expect_reward1 = total_reward - (total_reward * transfer_amount // (delegate_amount * 2)) - expect_reward0
    assert tracker0.delta() == expect_reward0
    assert tracker3.delta() == expect_reward1
    pledge_agent.claimReward([operators[1]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    assert len(validator_set.getValidators()) == 3


@pytest.mark.parametrize('slash_count', [1, 2, 3, 4])
def test_reward_claim_after_attenuation_slash(pledge_agent, validator_set, slash_indicator, slash_count):
    misdemeanor_threshold = 10
    attenuation_threshold = misdemeanor_threshold / 5
    slash_indicator.setThreshold(misdemeanor_threshold, 35)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 6
    transfer_amount1 = delegate_amount // 5
    total_pledged_amount0 = delegate_amount * 2
    total_pledged_amount1 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[3]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    for count in range(slash_count):
        slash_indicator.slash(consensuses[0])
        count += 1
    tracker0 = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0)
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {"from": accounts[1]})
    turn_round(consensuses)
    tracker0.update_height()
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    exceed_attenuation = slash_count - attenuation_threshold
    if exceed_attenuation < 0:
        exceed_attenuation = 0
    transfer_attenuation = exceed_attenuation * 10000 // (
            misdemeanor_threshold - attenuation_threshold)
    deducted_deposit = transfer_amount0 * (10000 - transfer_attenuation) // 10000
    operation_amount = transfer_amount0 + transfer_amount1
    remain_pledged_amount0 = delegate_amount - transfer_amount0
    total_transfer_reward = total_reward * transfer_amount0 // total_pledged_amount0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1
    expect_reward0 = total_transfer_reward * deducted_deposit // operation_amount \
                     + total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert tracker0.delta() == expect_reward0
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_reward_claim_after_transfer_and_reach_attenuation_threshold(pledge_agent, validator_set, slash_indicator):
    slash_count = 3
    misdemeanor_threshold = 10
    attenuation_threshold = misdemeanor_threshold / 5
    slash_indicator.setThreshold(misdemeanor_threshold, 35)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount
    transfer_amount1 = delegate_amount
    total_pledged_amount0 = delegate_amount * 2
    total_pledged_amount1 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[3]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    for count in range(slash_count):
        slash_indicator.slash(consensuses[0])
        count += 1
    tracker0 = get_tracker(accounts[0])
    tracker3 = get_tracker(accounts[3])
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0)
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {"from": accounts[1]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount1, {"from": accounts[3]})
    turn_round(consensuses)
    tracker0.update_height()
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[3]})
    transfer_attenuation = (slash_count - attenuation_threshold) * 10000 // (
            misdemeanor_threshold - attenuation_threshold)
    deducted_deposit = transfer_amount0 * (10000 - transfer_attenuation) // 10000
    operation_amount = transfer_amount0 + transfer_amount1 + transfer_amount1
    remain_pledged_amount0 = delegate_amount - transfer_amount0
    total_transfer_reward = total_reward * transfer_amount0 // total_pledged_amount0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1 + total_reward * transfer_amount1 // total_pledged_amount0
    expect_reward0 = total_transfer_reward * deducted_deposit // operation_amount \
                     + total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert tracker0.delta() == expect_reward0
    assert tracker3.delta() == expect_reward0


@pytest.mark.parametrize('slash_type', ['felony', 'misdemeanor'])
def test_transfer_before_slash_claim_reward(pledge_agent, validator_set, slash_indicator, slash_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    threshold = slash_indicator.misdemeanorThreshold()
    total_pledged_amount0 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    transfer_amount0 = delegate_amount // 3
    transfer_amount1 = delegate_amount // 6
    transfer_amount2 = delegate_amount // 2
    total_pledged_amount1 = delegate_amount
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    tx = None
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0)
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[3]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount2, {'from': accounts[1]})
    event_name = 'validatorMisdemeanor'
    if slash_type == 'felony':
        threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    operation_amount = transfer_amount0 + transfer_amount1 + transfer_amount2
    operation_reward0 = 0
    remain_part_reward = 0
    if slash_type == 'misdemeanor':
        operation_reward0 = total_reward * transfer_amount0 // total_pledged_amount0
        remain_part_reward = total_reward * (delegate_amount - transfer_amount0) // total_pledged_amount0
    total_transfer_reward = operation_reward0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1 + total_reward * \
                            transfer_amount2 // delegate_amount
    expect_reward0 = total_transfer_reward * transfer_amount0 // operation_amount
    expect_reward1 = total_transfer_reward * transfer_amount2 // operation_amount
    assert tracker0.delta() == expect_reward0 + remain_part_reward
    assert tracker1.delta() == expect_reward1 + total_reward - total_reward * transfer_amount2 // delegate_amount


@pytest.mark.parametrize('slash_count', [1, 2, 3, 4])
def test_transfer_before_decay_claim_reward(pledge_agent, validator_set, slash_indicator, slash_count):
    misdemeanor_threshold = 10
    slash_indicator.setThreshold(misdemeanor_threshold, 35)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 6
    transfer_amount1 = delegate_amount // 5
    total_pledged_amount0 = delegate_amount * 2
    total_pledged_amount1 = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[3]})

    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[3]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[3]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0)
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {"from": accounts[1]})
    for count in range(slash_count):
        slash_indicator.slash(consensuses[0])
        count += 1
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses)
    tracker0.update_height()
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    operation_amount = transfer_amount0 + transfer_amount1
    remain_pledged_amount0 = delegate_amount - transfer_amount0
    total_transfer_reward = total_reward * transfer_amount0 // total_pledged_amount0 + total_reward * \
                            transfer_amount1 // total_pledged_amount1
    expect_reward0 = total_transfer_reward * transfer_amount0 // operation_amount \
                     + total_reward * remain_pledged_amount0 // total_pledged_amount0
    assert tracker0.delta() == expect_reward0

def test_claim_reward_after_transfer_coin_undelegate(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.undelegateCoin(operators[0],(delegate_amount - transfer_amount) , {'from': accounts[0]})

    total_reward = BLOCK_REWARD // 2
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    total_pledged_amount = delegate_amount * 3
    transfer_undelegate_reward0 = total_reward * delegate_amount // total_pledged_amount
    transfer_expect_reward0  = transfer_undelegate_reward0 * transfer_amount // delegate_amount
    expect_reward0 = transfer_expect_reward0
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == total_reward - transfer_undelegate_reward0



