import brownie
import pytest
from web3 import Web3
from brownie import accounts, PledgeAgentProxy, DelegateReentry, UndelegateReentry, ClaimRewardReentry
from .common import register_candidate, turn_round
from .utils import get_tracker, expect_event, expect_query, encode_args_with_signature
from .calc_reward import parse_delegation, set_delegate, set_coin_delegator, calculate_rewards

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
    assert tracker.delta() == BLOCK_REWARD * 2.5


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
    assert tracker.delta() == BLOCK_REWARD * 3


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

    assert tracker1.delta() == delegator_reward1[clients[0]] + delegator_reward2[clients[0]]
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


def test_proxy_claim_reward_success(pledge_agent):
    pledge_agent_proxy = PledgeAgentProxy.deploy(pledge_agent.address, {'from': accounts[0]})
    pledge_agent_proxy.setReceiveState(True)
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
        "success": True
    })
    assert pledge_agent.rewardMap(pledge_agent_proxy.address) == 0


def test_claim_reward_failed(pledge_agent):
    pledge_agent_proxy = PledgeAgentProxy.deploy(pledge_agent.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    tx = pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "delegate", {"success": True})
    turn_round()
    turn_round([consensus])
    pledge_agent_proxy.setReceiveState(False)
    assert pledge_agent.rewardMap(pledge_agent_proxy.address) == 0
    with brownie.reverts("call to claimReward failed"):
        pledge_agent_proxy.claimReward.call([operator])


def test_delegate_coin_reentry(pledge_agent):
    pledge_agent_proxy = DelegateReentry.deploy(
        pledge_agent.address, {'from': accounts[0], 'value': MIN_INIT_DELEGATE_VALUE * 2})
    operators = accounts[1:3]
    consensus = []
    for _operator in operators:
        consensus.append(register_candidate(operator=_operator))
    pledge_agent_proxy.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensus)

    pledge_agent_proxy.setAgent(operators[0])
    tx = pledge_agent_proxy.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "proxyDelegate", {"success": True})
    assert pledge_agent_proxy.balance() == 0


def test_undelegate_coin_reentry(pledge_agent):
    pledge_agent_proxy = UndelegateReentry.deploy(pledge_agent.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round([consensus])
    pledge_agent_proxy.setAgent(operator)
    tx = pledge_agent_proxy.undelegateCoin(operator)
    expect_event(tx, "proxyUndelegate", {
        "success": False
    })


def test_undelegate_coin_partial_reentry(pledge_agent):
    pledge_agent_proxy = UndelegateReentry.deploy(pledge_agent.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE * 2})
    turn_round()
    turn_round([consensus])
    pledge_agent_proxy.setAgent(operator)
    tx = pledge_agent_proxy.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)
    expect_event(tx, "proxyUndelegatePartial", {
        "success": False
    })


def test_claim_reward_reentry(pledge_agent):
    pledge_agent_proxy = ClaimRewardReentry.deploy(pledge_agent.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round([consensus])
    pledge_agent_proxy.setAgents([operator])
    tracker = get_tracker(pledge_agent_proxy)
    tx = pledge_agent_proxy.claimReward([operator])
    expect_event(tx, "proxyClaim", {
        "success": True
    })
    assert tracker.delta() == BLOCK_REWARD // 2


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
    with brownie.reverts("remaining amount is too small"):
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


def test_undelegate_all_coins_on_validator_and_claim_rewards(pledge_agent, validator_set):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.undelegateCoin(operator, delegate_amount, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == 0


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
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tracker0.delta() == delegate_amount
    turn_round(consensuses, round_count=1)
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount * 5, 'from': accounts[0]})
    assert tracker0.delta() == 0 - delegate_amount * 5
    turn_round(consensuses, round_count=1)
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    total_delegate_amount = delegate_amount * 5
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
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operator = accounts[2]
    operator1 = accounts[3]
    tracker0 = get_tracker(accounts[0])
    consensus = register_candidate(operator=operator)
    register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
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
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    pledge_agent.undelegateCoin(operator, delegate_amount + MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round([consensus], round_count=2)
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0 - delegate_amount + delegate_amount + MIN_INIT_DELEGATE_VALUE
    turn_round([consensus])
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_transfer_with_partial_undelegate_and_claimed_rewards(pledge_agent, validator_set, candidate_hub,
                                                              undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    undelegate_amount = delegate_amount // 3
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
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
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount, {'from': accounts[2]})
    turn_round(consensuses, round_count=1)
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    remain_pledged_amount -= undelegate_amount
    expect_reward = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker1.delta() == expect_reward


def test_delegate_then_all_undelegate(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    additional_amount = MIN_INIT_DELEGATE_VALUE * 3
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operator, {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    tx = turn_round([consensus], round_count=1)
    assert tx.events['receiveDeposit'][1]['amount'] == total_reward // 2
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == total_reward - total_reward // 2 + MIN_INIT_DELEGATE_VALUE


def test_undelegate_transfer_input_and_deposit(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 5
    transfer_amount1 = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], {'from': accounts[0]})
    tx = turn_round(consensuses, round_count=1)
    deduct_reward0 = total_reward * (delegate_amount - transfer_amount) // delegate_amount
    deduct_reward2 = total_reward * (delegate_amount - transfer_amount1) // delegate_amount
    assert tx.events['receiveDeposit'][1]['amount'] == deduct_reward0
    assert tx.events['receiveDeposit'][2]['amount'] == deduct_reward2
    tracker0 = get_tracker(accounts[0])
    tx1 = pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tx1.events['receiveDeposit'][0]['amount'] == total_reward - deduct_reward0
    assert tx1.events['receiveDeposit'][1]['amount'] == total_reward - deduct_reward2
    assert tracker0.delta() == total_reward


def test_claim_rewards_after_transfers_undelegations_both_validators(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 5
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
    assert tracker0.delta() == expect_reward * 3


def test_all_validators_transfer_then_claim_reward(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 5
    undelegate_amount = transfer_amount + MIN_INIT_DELEGATE_VALUE
    undelegate_amount1 = transfer_amount + MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount1, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
    expect_reward2 = total_reward - total_reward * undelegate_amount1 // delegate_amount
    assert tracker0.delta() == expect_reward * 2 + expect_reward2


def test_order_of_claiming_affects_reward_deduction(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    total_pledged_amount = delegate_amount * 2
    undelegate_amount = transfer_amount0 // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    actual_debt_deposit = undelegate_amount
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount - transfer_amount0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_amount0,
                       total_pledged_amount + delegate_amount)
    rewards0 = calculate_rewards([operators[1], operators[0]], coin_delegator, actual_debt_deposit, accounts[0],
                                 total_reward)
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_amount0,
                       total_pledged_amount + delegate_amount)
    rewards1 = calculate_rewards([operators[0], operators[1]], coin_delegator, actual_debt_deposit, accounts[0],
                                 total_reward)
    turn_round(consensuses)
    expect_reward0 = pledge_agent.claimReward.call([operators[1], operators[0]])
    expect_reward1 = pledge_agent.claimReward.call([operators[0], operators[1]])
    assert sum(rewards0) == expect_reward0[0]
    assert sum(rewards1) == expect_reward1[0]


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_claim_undelegated_rewards_after_multiple_rounds(pledge_agent, validator_set, round_number):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = transfer_amount0 // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    remain_reward = total_reward - total_reward * undelegate_amount // delegate_amount
    turn_round(consensuses, round_count=round_number)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    reward_round = round_number - 1
    expect_reward = remain_reward + total_reward * 2 * reward_round
    assert tracker0.delta() == expect_reward


def test_transfer_auto_claim_rewards(pledge_agent, candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3
    total_reward = BLOCK_REWARD // 2
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    assert tracker0.delta() == total_reward // 2
    assert tracker1.delta() == 0
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[2], operators[1], 0)
    assert tracker0.delta() == 0
    pledge_agent.transferCoin(operators[0], operators[1], 0)
    assert tracker0.delta() == total_reward // 2
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[1], operators[2], 0)
    assert tracker0.delta() == total_reward


def test_claim_reward_after_transfer_coin(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    total_reward = BLOCK_REWARD // 2
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    remain_pledged_amount0 -= transfer_amount
    expect_query(delegator_info0,
                 {'deposit': remain_pledged_amount0, 'newDeposit': remain_pledged_amount0,
                  'transferOutDeposit': transfer_amount, 'transferInDeposit': 0})
    expect_query(delegator_info2,
                 {'newDeposit': transfer_amount, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount})
    debt_deposit = pledge_agent.getDebtDepositMap(1, accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    expect_reward0 = total_reward * delegate_amount // total_pledged_amount0
    expect_reward1 = total_reward - expect_reward0
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    turn_round(consensuses)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_transfer_coin_and_undelegate_to_active_validator(pledge_agent, validator_set, candidate_hub, validator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    total_reward = BLOCK_REWARD // 2
    operators = []
    consensuses = []
    validator_count = 2
    is_validator = False
    actual_debt_deposit = 0
    expect_reward = 0
    transfer_out_deposit = 0
    transfer_in_deposit = 0
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
        actual_debt_deposit = MIN_INIT_DELEGATE_VALUE
        transfer_out_deposit = transfer_amount
        transfer_in_deposit = transfer_amount - undelegate_amount
        expect_reward = total_reward - total_reward * MIN_INIT_DELEGATE_VALUE // delegate_amount
    turn_round()
    validators = validator_set.getValidators()
    assert validator_set.isValidator(consensuses[0]) == is_validator
    assert len(validators) == validator_count
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_out_deposit})
    expect_query(delegator_info2, {'transferInDeposit': transfer_in_deposit})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_transfer_coin_to_active_validator(pledge_agent, validator_set, candidate_hub, validator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    remain_pledged_amount = delegate_amount
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
    expect_query(delegator_info0, {'newDeposit': delegate_amount, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': 0, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    turn_round()
    out_deposit0 = 0
    in_deposit2 = 0
    expect_reward = 0
    if validator_type == 'active':
        out_deposit0 = transfer_amount
        in_deposit2 = transfer_amount
        expect_reward = BLOCK_REWARD // 2
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    remain_pledged_amount -= transfer_amount
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': remain_pledged_amount, 'transferOutDeposit': out_deposit0, 'transferInDeposit': 0})
    expect_query(delegator_info2,
                 {'newDeposit': transfer_amount, 'transferOutDeposit': 0, 'transferInDeposit': in_deposit2})
    pledge_agent.transferCoin(operators[0], operators[2], delegate_amount - transfer_amount)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    if validator_type == 'active':
        out_deposit0 += delegate_amount - transfer_amount
        in_deposit2 += delegate_amount - transfer_amount
    expect_query(delegator_info0,
                 {'deposit': 0, 'newDeposit': 0, 'transferOutDeposit': out_deposit0, 'transferInDeposit': 0})
    expect_query(delegator_info2,
                 {'newDeposit': delegate_amount, 'transferOutDeposit': 0, 'transferInDeposit': in_deposit2})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'deposit': 0, 'newDeposit': 0, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': delegate_amount, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    assert tracker0.delta() == expect_reward


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


def test_transfer_multiple_times_and_claim_rewards(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2

    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {"from": accounts[0]})
    turn_round(consensuses)
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info1,
                 {'newDeposit': transfer_amount, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount})
    tracker0 = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {"from": accounts[0]})
    assert tracker0.delta() == total_reward // 2
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info1,
                 {'deposit': transfer_amount, 'newDeposit': transfer_amount * 2, 'transferOutDeposit': 0,
                  'transferInDeposit': transfer_amount})
    expect_query(delegator_info0,
                 {'deposit': delegate_amount - transfer_amount * 2, 'newDeposit': delegate_amount - transfer_amount * 2,
                  'transferOutDeposit': transfer_amount, 'transferInDeposit': 0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    remain_pledged_amount = delegate_amount - transfer_amount
    total_pledged_amount = delegate_amount * 2 - transfer_amount
    expect_reward = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker0.delta() == expect_reward + total_reward


@pytest.mark.parametrize("undelegate_amount", [700, 900, 1000, 1400])
def test_claim_rewards_after_additional_cancel_delegate_and_transfer(pledge_agent, validator_set, candidate_hub,
                                                                     undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    additional_amount = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount * 2, 'from': accounts[3]})
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})

    effective_transfer = transfer_amount0
    remain_pledged_amount0 = delegate_amount * 2 - undelegate_amount - transfer_amount0
    if remain_pledged_amount0 > delegate_amount:
        remain_pledged_amount0 = delegate_amount
    if additional_amount - undelegate_amount >= 0:
        effective_transfer = transfer_amount0 - (additional_amount - undelegate_amount)
        if effective_transfer < 0:
            effective_transfer = 0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': effective_transfer, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': effective_transfer})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    expect_reward0 = total_reward * (effective_transfer + remain_pledged_amount0) // total_pledged_amount0
    assert tracker0.delta() == expect_reward0


@pytest.mark.parametrize("undelegate_amount", [400, 500, 100])
def test_transfer_to_new_validator_and_undelegate_claim_rewards(pledge_agent, validator_set, undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    actual_debt_deposit = undelegate_amount
    assert delegator_info2['transferInDeposit'] == transfer_out_deposit0 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount
    if remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0,
                       total_pledged_amount + delegate_amount)
    rewards = calculate_rewards([operators[1], operators[0]], coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward([operators[1], operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward
    assert tracker1.delta() == total_reward - total_reward // 2 + total_reward - total_reward // 3


@pytest.mark.parametrize("undelegate_amount", [400, 800, 1100, 2000])
def test_transfer_to_existing_validator_and_undelegate_claim_rewards(pledge_agent, validator_set, undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    new_deposit = delegate_amount
    if undelegate_amount > new_deposit:
        actual_debt_deposit = undelegate_amount - new_deposit
    else:
        actual_debt_deposit = 0
    assert delegator_info2['transferInDeposit'] == transfer_out_deposit0 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount - undelegate_amount
    if remain_coin1 < 0:
        remain_coin1 = 0
    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin1, 0, total_pledged_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward
    assert tracker1.delta() == (total_reward - total_reward // 2) * 2


def test_transfer_to_queued_validator_and_undelegate_claim_rewards(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = transfer_amount1 - MIN_INIT_DELEGATE_VALUE
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.setValidatorCount(2)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_out_deposit1 = 0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': delegate_amount - transfer_amount0, 'transferOutDeposit': transfer_out_deposit0})
    expect_query(delegator_info1,
                 {'newDeposit': transfer_out_deposit0 - transfer_amount1, 'transferOutDeposit': transfer_out_deposit1,
                  'transferInDeposit': transfer_out_deposit0 - transfer_amount1})
    expect_query(delegator_info2, {'newDeposit': transfer_amount1 - undelegate_amount, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount1 - undelegate_amount})
    actual_debt_deposit = undelegate_amount
    assert delegator_info2['transferInDeposit'] == transfer_amount1 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operation_amount", [[500, 1100, 2000], [500, 900, 1100], [500, 1400, 2100],
                                              [500, 900, 700], [500, 900, 1900], [500, 1500, 2300]])
def test_transfer_to_already_delegate_validator_in_queue(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    transfer_amount1 = operation_amount[1]
    undelegate_amount = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.setValidatorCount(2)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_out_deposit1 = 0
    effective_transfer = 0
    transfer_in_deposit1 = transfer_out_deposit0
    if transfer_amount1 > delegate_amount:
        effective_transfer = transfer_amount1 - delegate_amount
        transfer_in_deposit1 = transfer_amount0 - effective_transfer
    transfer_in_deposit2 = effective_transfer
    new_deposit2 = delegate_amount + transfer_amount1 - effective_transfer
    if undelegate_amount > new_deposit2:
        actual_debt_deposit = undelegate_amount - new_deposit2
    else:
        actual_debt_deposit = 0
    transfer_in_deposit2 -= actual_debt_deposit
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': delegate_amount - transfer_amount0, 'transferOutDeposit': transfer_out_deposit0})
    expect_query(delegator_info1, {'newDeposit': delegate_amount + transfer_out_deposit0 - transfer_amount1,
                                   'transferOutDeposit': transfer_out_deposit1,
                                   'transferInDeposit': transfer_in_deposit1})
    expect_query(delegator_info2,
                 {'newDeposit': delegate_amount + transfer_amount1 - undelegate_amount, 'transferOutDeposit': 0,
                  'transferInDeposit': transfer_in_deposit2})

    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin2 = new_deposit2 - undelegate_amount
    if remain_coin2 > delegate_amount:
        remain_coin2 = delegate_amount
    if remain_coin2 < 0:
        remain_coin2 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, 0, total_pledged_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operation_amount", [[500, 400], [500, 500]])
def test_single_transfer_to_queued_validator(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    undelegate_amount = operation_amount[1]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.setValidatorCount(2)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_in_deposit1 = transfer_out_deposit0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': delegate_amount - transfer_amount0, 'transferOutDeposit': transfer_out_deposit0})
    expect_query(delegator_info1, {'newDeposit': transfer_out_deposit0 - undelegate_amount, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_in_deposit1 - undelegate_amount})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    actual_debt_deposit = undelegate_amount
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operation_amount", [[500, 400], [500, 1200]])
def test_single_transfer_to_already_delegate_queued_validator(pledge_agent, validator_set, candidate_hub,
                                                              operation_amount):
    print(operation_amount)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    undelegate_amount = operation_amount[1]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.setValidatorCount(2)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_in_deposit1 = transfer_out_deposit0
    actual_debt_deposit = 0
    if undelegate_amount > delegate_amount:
        actual_debt_deposit = undelegate_amount - delegate_amount
        transfer_in_deposit1 = transfer_in_deposit1 - actual_debt_deposit
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': delegate_amount - transfer_amount0, 'transferOutDeposit': transfer_out_deposit0})
    expect_query(delegator_info1,
                 {'newDeposit': delegate_amount + transfer_out_deposit0 - undelegate_amount, 'transferOutDeposit': 0,
                  'transferInDeposit': transfer_in_deposit1})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin2 = delegate_amount
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, 0, delegate_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operation_amount",
                         [[500, 900, 900], [500, 1000, 900], [1000, 1100, 900],
                          [500, 900, 1000], [500, 1000, 1000], [500, 1100, 1000], [1000, 1100, 2100],
                          [500, 900, 1100], [500, 1000, 1100], [500, 1100, 1100], [500, 1100, 2100], [500, 900, 1800]])
def test_multiple_transfers_and_undelegate_claim_rewards(pledge_agent, validator_set, candidate_hub, operation_amount):
    candidate_hub.setValidatorCount(21)
    coin_delegator = {}
    print(operation_amount)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    transfer_amount1 = operation_amount[1]
    undelegate_amount = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    actual_debt_deposit = 0
    if undelegate_amount > delegate_amount:
        actual_debt_deposit = undelegate_amount - delegate_amount
    actual_in_deposit2 = transfer_amount1 - actual_debt_deposit
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': actual_in_deposit2})
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount - transfer_amount1
    remain_coin2 = delegate_amount - undelegate_amount
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    if transfer_amount1 > delegate_amount:
        transfer_amount1 = delegate_amount
    if remain_coin1 < 0:
        remain_coin1 = 0
    if remain_coin2 < 0:
        remain_coin2 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_amount1, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, 0, total_pledged_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    expect_reward = sum(rewards)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operation_amount",
                         [[500, 300, 300], [500, 300, 400], [500, 500, 300], [500, 500, 500],
                          [500, 500, 800], [500, 800, 100], [500, 800, 800], [500, 800, 1700], [500, 800, 1800]
                          ])
def test_claim_rewards_after_additional_and_transfer(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    additional_amount = operation_amount[0]
    transfer_amount1 = operation_amount[1]
    undelegate_amount = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    remain_coin0 = delegate_amount + additional_amount - transfer_amount1
    if remain_coin0 > delegate_amount:
        remain_coin0 = delegate_amount
    if transfer_amount1 > additional_amount:
        transfer_out_deposit0 = transfer_amount1 - additional_amount
    else:
        transfer_out_deposit0 = 0
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    invalid_transfer = transfer_amount1 - transfer_out_deposit0
    if undelegate_amount > (delegate_amount + invalid_transfer):
        actual_debt_deposit = undelegate_amount - (delegate_amount + invalid_transfer)
    else:
        actual_debt_deposit = 0
    assert delegator_info1['transferInDeposit'] == transfer_out_deposit0 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin1 = delegate_amount + invalid_transfer - undelegate_amount
    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    elif remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0, total_pledged_amount)
    rewards = calculate_rewards([operators[0], operators[1]], coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(rewards) + total_reward // 2


@pytest.mark.parametrize("operation_amount",
                         [[500, 300, 300], [500, 500, 300], [500, 800, 1200], [1000, 300, 1400],
                          [500, 800, 2300],
                          [500, 800, 2100]
                          ])
def test_transfer_and_delegate_with_reward_claim(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    additional_amount = operation_amount[1]
    undelegate_amount = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    remain_coin0 = delegate_amount - transfer_amount0
    transfer_out_deposit0 = transfer_amount0
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    new_deposit = delegate_amount + additional_amount
    if undelegate_amount > new_deposit:
        actual_debt_deposit = undelegate_amount - new_deposit
    else:
        actual_debt_deposit = 0
    assert delegator_info1['transferInDeposit'] == transfer_out_deposit0 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin1 = new_deposit - undelegate_amount
    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    elif remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0, total_pledged_amount)
    rewards = calculate_rewards([operators[0], operators[1]], coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(rewards) + total_reward // 2


@pytest.mark.parametrize("operation_amount",
                         [[500, 300, 600], [500, 1500, 400], [600, 1000, 400], [500, 1200, 800], [1000, 1200, 800]])
def test_undelegate_and_transfer_with_rewards(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    transfer_amount1 = operation_amount[2]
    undelegate_amount = operation_amount[1]
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount * 2, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount1, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_out_deposit2 = transfer_amount1
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    assert delegator_info2['transferOutDeposit'] == transfer_out_deposit2
    new_deposit = delegate_amount
    if undelegate_amount > new_deposit:
        actual_debt_deposit = undelegate_amount - new_deposit
    else:
        actual_debt_deposit = 0
    assert delegator_info1['transferInDeposit'] == transfer_out_deposit0 - actual_debt_deposit + transfer_out_deposit2
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = new_deposit - undelegate_amount
    remain_coin2 = delegate_amount - transfer_amount1

    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    elif remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, transfer_out_deposit2,
                       total_pledged_amount + delegate_amount)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(rewards)


@pytest.mark.parametrize("operation_amount",
                         [[500, 300, 500], [1000, 300, 800], [400, 300, 1600], [1000, 400, 2400], [400, 400, 1800]])
def test_transfer_to_same_validator_and_undelegate(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    transfer_amount1 = operation_amount[1]
    undelegate_amount = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    total_pledged_amount2 = delegate_amount
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    transfer_out_deposit1 = transfer_amount1
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['transferOutDeposit'] == transfer_out_deposit0
    assert delegator_info2['transferOutDeposit'] == transfer_out_deposit1
    new_deposit = delegate_amount
    if undelegate_amount > new_deposit:
        actual_debt_deposit = undelegate_amount - new_deposit
    else:
        actual_debt_deposit = 0
    assert delegator_info1['transferInDeposit'] == transfer_out_deposit0 + transfer_out_deposit1 - actual_debt_deposit
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = new_deposit - undelegate_amount
    remain_coin2 = delegate_amount - transfer_amount1
    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    elif remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0, total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, transfer_out_deposit1,
                       total_pledged_amount2)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(rewards)


@pytest.mark.parametrize("operation_amount", [[500, 600, 1000], [500, 600, 500], [500, 600, 1800], [500, 600, 1500]])
def test_transfer_and_delegate_and_then_transfer(pledge_agent, validator_set, candidate_hub, operation_amount):
    print(operation_amount)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = operation_amount[0]
    additional_amount = operation_amount[1]
    transfer_amount1 = operation_amount[2]
    total_pledged_amount = delegate_amount * 2
    total_pledged_amount2 = delegate_amount
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    transfer_out_deposit0 = transfer_amount0
    if transfer_amount1 > additional_amount:
        transfer_out_deposit1 = transfer_amount1 - additional_amount
    else:
        transfer_out_deposit1 = 0
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == transfer_out_deposit1
    if transfer_out_deposit1 > delegate_amount:
        transfer_out_deposit1 = delegate_amount
    actual_debt_deposit = 0
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    assert delegator_info1['transferOutDeposit'] == transfer_out_deposit1
    new_deposit = delegate_amount + additional_amount
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == actual_debt_deposit
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = new_deposit - transfer_amount1
    remain_coin2 = delegate_amount
    if remain_coin1 > delegate_amount:
        remain_coin1 = delegate_amount
    if remain_coin1 < 0:
        remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_out_deposit0,
                       total_pledged_amount2)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_out_deposit1,
                       total_pledged_amount)
    set_coin_delegator(coin_delegator, operators[2], accounts[1], remain_coin2, transfer_out_deposit1,
                       total_pledged_amount2)
    rewards = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0],
                                total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(rewards)


def test_claim_reward_in_no_transfer_validator(pledge_agent, validator_set, candidate_hub):
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    round_value = pledge_agent.roundTag()
    debt_deposit = pledge_agent.getDebtDepositMap(round_value, accounts[0])
    assert debt_deposit == undelegate_amount
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(round_value, accounts[0])
    assert debt_deposit == undelegate_amount
    assert tracker0.delta() == 0
    expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward
    debt_deposit = pledge_agent.getDebtDepositMap(round_value, accounts[0])
    assert debt_deposit == 0


def test_transfer_then_validator_refuses_delegate(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    total_reward = BLOCK_REWARD // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    candidate_hub.refuseDelegate({'from': operators[2]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == MIN_INIT_DELEGATE_VALUE
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward - total_reward * undelegate_amount // delegate_amount


def test_transfer_and_delegate_to_queued_validator(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    additional_amount = MIN_INIT_DELEGATE_VALUE * 6
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 7
    total_pledged_amount = delegate_amount * 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.setValidatorCount(2)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    actual_debt_deposit = MIN_INIT_DELEGATE_VALUE
    assert debt_deposit == actual_debt_deposit
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    expect_reward = total_reward * (delegate_amount - actual_debt_deposit) // total_pledged_amount
    assert tracker0.delta() == expect_reward


def test_claim_rewards_after_mutual_transfers(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 11
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    transfer_amount2 = MIN_INIT_DELEGATE_VALUE * 4
    operators = []
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[0], transfer_amount2, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], transfer_amount2, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[0], {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == 0


def test_additional_transfer_and_undelegate(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    additional_amount = MIN_INIT_DELEGATE_VALUE * 6
    transfer_amount1 = delegate_amount + additional_amount + MIN_INIT_DELEGATE_VALUE
    undelegate_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount1 = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    actual_debt_deposit = MIN_INIT_DELEGATE_VALUE * 6
    assert debt_deposit == actual_debt_deposit
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0})
    expect_query(delegator_info1, {'transferOutDeposit': delegate_amount,
                                   'transferInDeposit': transfer_amount0 - undelegate_amount0 - MIN_INIT_DELEGATE_VALUE})
    expect_query(delegator_info2, {'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount1 - undelegate_amount1 - MIN_INIT_DELEGATE_VALUE})
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, delegate_amount * 2)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, delegate_amount, delegate_amount * 2)
    expect_reward = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses)
    reward0 = pledge_agent.claimReward.call([operators[0]], {'from': accounts[0]})[0]
    reward1 = pledge_agent.claimReward.call([operators[0], operators[1]], {'from': accounts[0]})[0] - reward0
    reward2 = pledge_agent.claimReward.call([operators[0], operators[1], operators[2]], {'from': accounts[0]})[
                  0] - reward1 - reward0
    assert expect_reward[0] == reward0
    assert expect_reward[1] == reward1
    assert expect_reward[2] == reward2


def test_multiple_operations_in_current_rounds(pledge_agent, validator_set):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 7
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount1 = transfer_amount0 // 2
    undelegate_amount = delegate_amount
    operators = []
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": additional_delegate, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info2, {'newDeposit': transfer_amount0, 'transferInDeposit': 0})
    expect_query(delegator_info0, {'newDeposit': additional_delegate - transfer_amount0, 'transferOutDeposit': 0})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount1, {'from': accounts[0]})
    turn_round(consensuses)
    total_reward = BLOCK_REWARD // 2
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == 0
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_transfer_and_check_transfer_info(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    transfer_amount2 = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    tx = pledge_agent.transferCoin(operators[2], operators[0], transfer_amount2, {'from': accounts[0]})
    expect_event(tx, "transferredCoin", {
        "sourceAgent": operators[2],
        "targetAgent": operators[0],
        "delegator": accounts[0],
        "amount": transfer_amount1,
        "totalAmount": delegate_amount - transfer_amount0 + transfer_amount1,
    })
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'newDeposit': delegate_amount - transfer_amount0 + transfer_amount2,
                                   'transferOutDeposit': transfer_amount0, 'transferInDeposit': transfer_amount2})
    expect_query(delegator_info1, {'newDeposit': delegate_amount + transfer_amount0 - transfer_amount1,
                                   'transferOutDeposit': transfer_amount1, 'transferInDeposit': transfer_amount0})
    expect_query(delegator_info2, {'newDeposit': delegate_amount + transfer_amount1 - transfer_amount2,
                                   'transferOutDeposit': transfer_amount2, 'transferInDeposit': transfer_amount1})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2 * 2


def test_multiple_transfers_and_check_transfer_info(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    total_pledged_amount1 = delegate_amount * 2
    total_pledged_amount2 = delegate_amount
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    transfer_amount2 = delegate_amount // 4
    undelegate_amount = transfer_amount1 + MIN_INIT_DELEGATE_VALUE
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit1 = delegate_amount - transfer_amount1
    new_deposit2 = delegate_amount + transfer_amount0 + transfer_amount1
    expect_query(delegator_info0,
                 {'newDeposit': delegate_amount - transfer_amount0, 'transferOutDeposit': transfer_amount0,
                  'transferInDeposit': 0})
    expect_query(delegator_info1,
                 {'newDeposit': new_deposit1, 'transferOutDeposit': transfer_amount1, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': new_deposit2, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount0 + transfer_amount1})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit2 -= undelegate_amount
    new_deposit1 -= transfer_amount2
    expect_query(delegator_info2, {'newDeposit': new_deposit2, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount0 + transfer_amount1})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount2, {'from': accounts[0]})
    new_deposit2 += transfer_amount2
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info1,
                 {'newDeposit': new_deposit1, 'transferOutDeposit': transfer_amount1 + transfer_amount2,
                  'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': new_deposit2, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount0 + transfer_amount1 + transfer_amount2})
    coin_delegator = {}
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount - transfer_amount1 - transfer_amount2
    remain_coin2 = delegate_amount - undelegate_amount
    actual_debt_deposit = 0
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, total_pledged_amount2)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_amount0, total_pledged_amount1)
    set_coin_delegator(coin_delegator, operators[2], accounts[0], remain_coin2, 0, total_pledged_amount1)
    expect_reward = calculate_rewards(operators, coin_delegator, actual_debt_deposit, accounts[0], total_reward)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == sum(expect_reward)


def test_transfer_info_accumulation(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    new_deposit0 = delegate_amount
    new_deposit2 = delegate_amount
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    new_deposit0 -= transfer_amount0
    new_deposit2 += transfer_amount0
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': new_deposit0, 'transferOutDeposit': transfer_amount0, 'transferInDeposit': 0})
    expect_query(delegator_info2,
                 {'newDeposit': new_deposit2, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount1, {'from': accounts[0]})
    new_deposit0 -= transfer_amount1
    new_deposit2 += transfer_amount1
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'newDeposit': new_deposit0, 'transferOutDeposit': transfer_amount0 + transfer_amount1,
                  'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': new_deposit2, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount0 + transfer_amount1})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    new_deposit2 += transfer_amount1 * 2
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info1,
                 {'newDeposit': delegate_amount - transfer_amount1 * 2, 'transferOutDeposit': transfer_amount1 * 2,
                  'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': new_deposit2, 'transferOutDeposit': 0,
                                   'transferInDeposit': transfer_amount0 + transfer_amount1 * 3})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    expect_reward = total_reward
    assert tracker0.delta() == expect_reward
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 2


def test_batch_transfer_to_multiple_validators(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[0], transfer_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount0, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit0 = delegate_amount - transfer_amount0 + transfer_amount1
    new_deposit1 = delegate_amount - transfer_amount1 + transfer_amount0
    new_deposit2 = delegate_amount + transfer_amount0 + transfer_amount1 - transfer_amount0 - transfer_amount1
    expect_query(delegator_info0, {'newDeposit': new_deposit0, 'transferOutDeposit': transfer_amount0,
                                   'transferInDeposit': transfer_amount1})
    expect_query(delegator_info1, {'newDeposit': new_deposit1, 'transferOutDeposit': transfer_amount1,
                                   'transferInDeposit': transfer_amount0})
    expect_query(delegator_info2,
                 {'newDeposit': new_deposit2, 'transferOutDeposit': transfer_amount1 + transfer_amount0,
                  'transferInDeposit': transfer_amount0 + transfer_amount1})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[1]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 2


def test_single_transfer_and_check_transfer_info(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 3


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_reward_claim_after_slash(pledge_agent, validator_set, slash_indicator, threshold_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tx = None
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = total_reward
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': transfer_amount})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['transferOutDeposit'] == 0
    assert delegator_info2['transferInDeposit'] == 0
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_reward_after_slash_and_transfer(pledge_agent, validator_set, slash_indicator, threshold_type, candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tx0 = None
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = total_reward
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': transfer_amount})
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': transfer_amount})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == 0
    assert tracker0.delta() == expect_reward
    required_margin = 1000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=2)
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == 0


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_post_transfer_major_slash(pledge_agent, validator_set, slash_indicator, threshold_type, candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    input_deposit = transfer_amount - undelegate_amount
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tx0 = None
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
        expect_reward1 = total_reward * 3
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
        expect_reward1 = total_reward
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': input_deposit})
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': input_deposit})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == undelegate_amount
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == 0
    assert tracker0.delta() == expect_reward
    required_margin = 100000000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=3)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward1
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == 0


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_major_violation_followed_by_reward_claim(pledge_agent, validator_set, slash_indicator, threshold_type, candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators = []
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    total_reward = BLOCK_REWARD // 2
    transfer_amount = delegate_amount // 3
    consensuses = []
    input_deposit = transfer_amount - undelegate_amount
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tx0 = None
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
        expect_reward1 = total_reward * 3
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount
        expect_reward1 = total_reward
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferOutDeposit': 0, 'transferInDeposit': input_deposit})
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == undelegate_amount
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == input_deposit
    required_margin = 100000000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=3)
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward1 + expect_reward + total_reward * 3
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['transferInDeposit'] == 0


def test_undelegate_then_transfer(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    undelegate_amount = delegate_amount // 6
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit = transfer_amount0
    expect_query(delegator_info0, {'newDeposit': delegate_amount - undelegate_amount - transfer_amount0,
                                   'transferOutDeposit': transfer_amount0, 'transferInDeposit': 0})
    expect_query(delegator_info2,
                 {'newDeposit': new_deposit, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward([operators[2], operators[0]], {'from': accounts[0]})
    transfer_reward = total_reward * transfer_amount0 // delegate_amount
    remain_reward = total_reward - (total_reward * undelegate_amount // delegate_amount) - transfer_reward
    assert tracker0.delta() == transfer_reward + remain_reward


def test_batch_transfer_to_one_validator(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    transfer_amount2 = transfer_amount0 // 2
    transfer_amount3 = transfer_amount1 // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    new_deposit2 = transfer_amount0 + transfer_amount1
    pledge_agent.transferCoin(operators[2], operators[3], transfer_amount2, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[3], transfer_amount3, {'from': accounts[0]})
    new_deposit3 = transfer_amount2 + transfer_amount3
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'newDeposit': new_deposit2 - new_deposit3, 'transferOutDeposit': 0,
                                   'transferInDeposit': new_deposit2 - new_deposit3})
    delegator_info3 = pledge_agent.getDelegator(operators[3], accounts[0])
    expect_query(delegator_info3,
                 {'newDeposit': new_deposit3, 'transferOutDeposit': 0, 'transferInDeposit': new_deposit3})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 2


def test_claim_rewards_after_transfer_and_delegate_and_undelegate(pledge_agent, validator_set, candidate_hub):
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    additional_amount = MIN_INIT_DELEGATE_VALUE * 3
    transfer_amount1 = transfer_amount0 // 3
    undelegate_amount = transfer_amount1
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": additional_amount, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[3], transfer_amount1, {'from': accounts[0]})
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info3 = pledge_agent.getDelegator(operators[3], accounts[0])
    new_deposit1 = transfer_amount0 + additional_amount - transfer_amount1
    expect_query(delegator_info1,
                 {'newDeposit': new_deposit1, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    expect_query(delegator_info3, {'newDeposit': transfer_amount1, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    pledge_agent.undelegateCoin(operators[3], undelegate_amount, {'from': accounts[0]})
    delegator_info3 = pledge_agent.getDelegator(operators[3], accounts[0])
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    assert delegator_info3['transferInDeposit'] == 0
    assert delegator_info3['newDeposit'] == 0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_transfer_after_claim_reward(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    turn_round(consensuses)
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit0 = transfer_amount0
    expect_query(delegator_info2,
                 {'newDeposit': new_deposit0, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == 0
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_reward_claim_midway_doesnt_affect_current_round(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0})
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0 - undelegate_amount})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == undelegate_amount
    expect_reward = total_reward * (delegate_amount - undelegate_amount) // delegate_amount
    tracker0 = get_tracker(accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    reward_info = pledge_agent.getReward(operators[0], delegator_info0['rewardIndex'])
    assert reward_info['score'] == delegate_amount
    assert reward_info['coin'] == delegate_amount
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("undelegate_amount", [400, 800])
def test_transfer_and_undelegate_in_different_rounds(pledge_agent, validator_set, undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2 + undelegate_amount
    turn_round(consensuses)
    remain_reward = total_reward * (delegate_amount - transfer_amount0) // (delegate_amount * 2 - transfer_amount0)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2 + remain_reward


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operations_in_next_round_after_transfer(pledge_agent, validator_set, operator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    if operator_type == 'undelegate':
        pledge_agent.undelegateCoin(operators[2], operation_amount, {'from': accounts[0]})
        expect_reward0 = total_reward
        expect_reward2 = operation_amount
        remain_reward = total_reward - total_reward // 2
    elif operator_type == 'transfer':
        pledge_agent.transferCoin(operators[2], operators[1], operation_amount, {'from': accounts[0]})
        expect_reward0 = total_reward
        expect_reward2 = 0
        remain_reward = total_reward
    elif operator_type == 'claim':
        pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
        expect_reward0 = total_reward
        expect_reward2 = 0
        remain_reward = total_reward
    else:
        pledge_agent.delegateCoin(operators[2], {"value": operation_amount, 'from': accounts[0]})
        expect_reward0 = total_reward
        expect_reward2 = -operation_amount
        remain_reward = total_reward
    assert tracker0.delta() == expect_reward2
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward0
    turn_round(consensuses)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == remain_reward


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_next_round_operations_on_sender_post_transfer(pledge_agent, validator_set, operator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    reward = 0
    if operator_type == 'undelegate':
        pledge_agent.undelegateCoin(operators[0], operation_amount, {'from': accounts[0]})
        reward = operation_amount
    elif operator_type == 'transfer':
        pledge_agent.transferCoin(operators[0], operators[1], operation_amount, {'from': accounts[0]})
    elif operator_type == 'claim':
        pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    else:
        pledge_agent.delegateCoin(operators[0], {"value": operation_amount, 'from': accounts[0]})
        reward = -operation_amount
    assert tracker0.delta() == total_reward + reward


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operations_in_current_round_after_transfer(pledge_agent, validator_set, operator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    effective_amount = delegate_amount
    if operator_type == 'undelegate':
        pledge_agent.undelegateCoin(operators[0], operation_amount, {'from': accounts[0]})
        effective_amount = delegate_amount - operation_amount
        expect_reward = total_reward - total_reward * (delegate_amount - effective_amount) // delegate_amount
    elif operator_type == 'transfer':
        pledge_agent.transferCoin(operators[0], operators[1], operation_amount, {'from': accounts[0]})
        expect_reward = total_reward
    elif operator_type == 'claim':
        pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
        expect_reward = total_reward
    else:
        pledge_agent.delegateCoin(operators[0], {"value": operation_amount, 'from': accounts[0]})
        expect_reward = total_reward
    tracker0 = get_tracker(accounts[0])
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    reward_info = pledge_agent.getReward(operators[0], delegator_info0['rewardIndex'])
    assert reward_info['score'] == delegate_amount
    assert reward_info['coin'] == effective_amount
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == expect_reward


def test_transfer_to_validator_with_existing_transfers(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[1], operators[2], operation_amount, {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 2
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operation_on_validator_with_no_transfer(pledge_agent, validator_set, operator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[3], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    if operator_type == 'undelegate':
        pledge_agent.undelegateCoin(operators[3], operation_amount, {'from': accounts[0]})
        remain_reward = total_reward + operation_amount
    elif operator_type == 'transfer':
        pledge_agent.transferCoin(operators[3], operators[4], operation_amount, {'from': accounts[0]})
        remain_reward = total_reward
    elif operator_type == 'claim':
        pledge_agent.claimReward([operators[3]], {'from': accounts[0]})
        remain_reward = total_reward
    else:
        pledge_agent.delegateCoin(operators[3], {"value": operation_amount, 'from': accounts[0]})
        remain_reward = total_reward - operation_amount
    assert tracker0.delta() == remain_reward
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0})
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0], operators[2]], {'from': accounts[0]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2, {'transferInDeposit': 0})
    expect_query(delegator_info0, {'transferOutDeposit': 0})
    assert tracker0.delta() == total_reward * 3


def test_transfer_and_delegate_in_different_rounds(pledge_agent, validator_set):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 4
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operators[0], {"value": additional_delegate, 'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2 - additional_delegate
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info2,
                 {'newDeposit': transfer_amount0, 'transferOutDeposit': 0, 'transferInDeposit': transfer_amount0})
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount1, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[1], operators[2], transfer_amount1, {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info1, {'newDeposit': 0, 'transferOutDeposit': 0, 'transferInDeposit': 0})
    expect_query(delegator_info2, {'newDeposit': transfer_amount0, 'transferOutDeposit': transfer_amount1,
                                   'transferInDeposit': transfer_amount1})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == 0
    turn_round(consensuses)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_transfer_and_undelegate_and_delegate_in_different_rounds(pledge_agent, validator_set):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 3 / 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    turn_round(consensuses)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount0})
    expect_query(delegator_info2, {'transferInDeposit': transfer_amount0})
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == total_reward + undelegate_amount
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'newDeposit': transfer_amount0 - undelegate_amount, 'transferOutDeposit': 0})
    pledge_agent.delegateCoin(operators[2], {"value": additional_delegate, 'from': accounts[0]})
    pledge_agent.transferCoin(operators[2], operators[1], transfer_amount1, {'from': accounts[0]})
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    new_deposit2 = transfer_amount0 + additional_delegate - transfer_amount1
    expect_query(delegator_info2,
                 {'newDeposit': new_deposit2, 'transferOutDeposit': transfer_amount1 - additional_delegate})
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info1,
                 {'newDeposit': transfer_amount1, 'transferInDeposit': transfer_amount1 - additional_delegate})
    turn_round(consensuses)
    tracker0.update_height()
    pledge_agent.transferCoin(operators[2], operators[1], new_deposit2, {'from': accounts[0]})
    assert tracker0.delta() == total_reward
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info2['newDeposit'] == 0
    expect_query(delegator_info1, {'newDeposit': transfer_amount1 + new_deposit2, 'transferInDeposit': new_deposit2})
    turn_round(consensuses)
    pledge_agent.claimReward([operators[1]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


def test_multiple_operations_in_different_rounds(pledge_agent, validator_set):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 3 / 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 2.5
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operators[0], {"value": additional_delegate, 'from': accounts[0]})
    assert tracker0.delta() == total_reward - total_reward * undelegate_amount // delegate_amount - additional_delegate
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount1, {'from': accounts[0]})
    turn_round(consensuses)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info0, {'transferOutDeposit': transfer_amount1 - additional_delegate})
    expect_query(delegator_info1,
                 {'newDeposit': transfer_amount1, 'transferInDeposit': transfer_amount1 - additional_delegate})
    tracker0.update_height()
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == total_reward + undelegate_amount
    turn_round(consensuses)
    pledge_agent.claimReward([operators[1]], {'from': accounts[0]})
    assert tracker0.delta() == total_reward


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_transfer_rewards_and_claim_after_multiple_rounds(pledge_agent, validator_set, round_number):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=round_number)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    reward_round = round_number - 1
    expect_reward = total_reward + total_reward * 2 * reward_round
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_claim_rewards_after_transfer_and_undelegate_in_multiple_rounds(pledge_agent, validator_set, round_number):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:7]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=round_number)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    reward_round = round_number - 1
    expect_reward = total_reward - total_reward * undelegate_amount // delegate_amount + total_reward * 2 * reward_round
    assert tracker0.delta() == expect_reward


def test_claim_reward_after_accumulating_debt_deposit(pledge_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount1 = MIN_INIT_DELEGATE_VALUE * 4
    operators = []
    total_reward = BLOCK_REWARD // 2
    consensuses = []
    for operator in accounts[4:14]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    coin_delegator = {}
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount0, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount0, {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == undelegate_amount0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.transferCoin(operators[1], operators[3], transfer_amount0, {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2
    pledge_agent.undelegateCoin(operators[3], undelegate_amount1, {'from': accounts[0]})
    debt_deposit = pledge_agent.getDebtDepositMap(pledge_agent.roundTag(), accounts[0])
    assert debt_deposit == undelegate_amount1
    remain_coin0 = delegate_amount - transfer_amount0
    remain_coin1 = delegate_amount - transfer_amount0
    total_pledged_amount = delegate_amount * 2
    actual_debt_deposit0 = undelegate_amount0
    actual_debt_deposit1 = undelegate_amount1
    turn_round(consensuses)
    actual_reward0 = pledge_agent.claimReward.call([operators[0], operators[1]], {'from': accounts[0]})
    actual_reward1 = pledge_agent.claimReward.call([operators[1], operators[0]], {'from': accounts[0]})
    assert actual_reward0 == actual_reward1
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, transfer_amount0, delegate_amount)
    rewards0 = calculate_rewards([operators[0]], coin_delegator, actual_debt_deposit0, accounts[0], total_reward)
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, transfer_amount0, total_pledged_amount)
    rewards1 = calculate_rewards([operators[1]], coin_delegator, actual_debt_deposit1, accounts[0], total_reward)
    expect_reward0 = total_reward + sum(rewards0) + sum(rewards1)
    assert actual_reward0[0] == expect_reward0
    turn_round(consensuses, round_count=3)
    actual_reward0 = pledge_agent.claimReward.call([operators[0], operators[1]], {'from': accounts[0]})
    actual_reward1 = pledge_agent.claimReward.call([operators[1], operators[0]], {'from': accounts[0]})
    assert actual_reward0 == actual_reward1
    set_coin_delegator(coin_delegator, operators[0], accounts[0], remain_coin0, 0, remain_coin0)
    rewards0 = calculate_rewards([operators[0]], coin_delegator, actual_debt_deposit0, accounts[0], total_reward)
    total_pledged_amount -= transfer_amount0
    set_coin_delegator(coin_delegator, operators[1], accounts[0], remain_coin1, 0, total_pledged_amount)
    rewards1 = calculate_rewards([operators[1]], coin_delegator, actual_debt_deposit1, accounts[0], total_reward)
    remain_reward = sum(rewards0) * 3 + sum(rewards1) * 3
    assert remain_reward + expect_reward0 == actual_reward0[0]
