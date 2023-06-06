import brownie
import pytest
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


@pytest.fixture()
def set_candidate():
    operator = accounts[1]
    consensus = operator
    register_candidate(consensus=consensus, operator=operator)
    return consensus, operator


@pytest.fixture(scope="module", autouse=True)
def set_round_tag(candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)


@pytest.fixture(scope="module", autouse=True)
def set_lock_turns(pledge_agent):
    pledge_agent.setUndelegateLockTurns(3)


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
        assert tracker.delta() == BLOCK_REWARD / 2
        pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
        assert tracker.delta() == 0
        turn_round([consensus], round_count=3)
        pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
        assert tracker.delta() == MIN_INIT_DELEGATE_VALUE
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
    tracker = get_tracker(accounts[0])
    turn_round()
    turn_round(consensuses)
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.transferCoin(operators[1], operators[2])
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators)
    assert tracker.delta() == BLOCK_REWARD // 2 * 5


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
    tracker = get_tracker(accounts[0])
    turn_round()
    turn_round(consensuses)
    pledge_agent.transferCoin(operators[1], operators[2])
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators)
    assert tracker.delta() == BLOCK_REWARD // 2 * 6


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
    assert reward_sum == BLOCK_REWARD // 2


def test_undelegate_coin_reward(pledge_agent, validator_set):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    pledge_agent.undelegateCoin(operator)
    tx = turn_round([consensus])
    assert "receiveDeposit" in tx.events
    event = tx.events['receiveDeposit'][-1]
    assert event['from'] == validator_set.address


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


def test_claim_rewards_each_round_during_lockup_period_after_undelegate(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    round_tag = pledge_agent.roundTag()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, 0, {'from': accounts[1]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0
    turn_round([consensus], round_count=1)
    assert round_tag + 1 == pledge_agent.roundTag()
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == total_reward // 2
    assert tracker1.delta() == total_reward - total_reward // 2
    turn_round([consensus], round_count=1)
    assert round_tag + 2 == pledge_agent.roundTag()
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == total_reward
    assert tracker1.delta() == 0
    turn_round([consensus], round_count=1)
    assert round_tag + 3 == pledge_agent.roundTag()
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == total_reward
    assert tracker1.delta() == 0
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    pledge_agent.claimUnlockedDeposit({'from': accounts[1]})
    assert tracker0.delta() == undelegate_amount
    assert tracker1.delta() == delegate_amount


def test_no_reward_generated_during_lockup_period(pledge_agent, validator_set, candidate_hub):
    operator = accounts[2]
    consensus = register_candidate(operator=operator)
    turn_round()
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    round_tag = pledge_agent.roundTag()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.undelegateCoin(operator, {'from': accounts[0]})
    turn_round([consensus], round_count=4)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == 0
    assert round_tag + 4 == pledge_agent.roundTag()
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE


def test_auto_reward_distribution_on_undelegate(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount0, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus])
    pledge_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, {'from': accounts[1]})
    account1_reward = total_reward * delegate_amount0 // (delegate_amount0 + MIN_INIT_DELEGATE_VALUE)
    assert tracker0.delta() == account1_reward
    assert tracker1.delta() == total_reward - account1_reward


def test_claim_rewards_each_round_after_repeated_undelegate(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    consensus = register_candidate(operator=operator)
    tracker0 = get_tracker(accounts[0])
    turn_round()
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    pledge_agent.undelegateCoin(operator, undelegate_amount * 3 + 10, {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == 0 - delegate_amount
    turn_round()
    pledge_agent.undelegateCoin(operator, undelegate_amount * 2 + 10, {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == 0
    turn_round([consensus])
    remain_pledged_amount -= undelegate_amount * 3 + 10
    total_pledged_amount -= undelegate_amount * 3 + 10
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount * 3 // 2, {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == 0

    turn_round([consensus])
    remain_pledged_amount -= undelegate_amount * 2 + 10
    total_pledged_amount -= undelegate_amount * 2 + 10
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount * 3 + 10

    turn_round([consensus])
    remain_pledged_amount -= undelegate_amount * 3 // 2
    total_pledged_amount -= undelegate_amount * 3 // 2
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount * 2 + 10
    turn_round([consensus])
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount * 3 // 2


def test_withdraw_cancelled_delegated_amount_multiple_rounds(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    consensus = register_candidate(operator=operator)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    assert tracker0.delta() == 0 - delegate_amount
    turn_round()
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == 0
    turn_round([consensus])
    current_round_reward1 = total_reward * remain_pledged_amount // total_pledged_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward1
    delegator_info0 = pledge_agent.getDelegator(operator, accounts[0])
    assert delegator_info0['newDeposit'] == 0
    turn_round([consensus], round_count=4)
    remain_pledged_amount -= undelegate_amount
    total_pledged_amount -= undelegate_amount
    current_round_reward2 = total_reward * remain_pledged_amount // total_pledged_amount
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward2
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount * 2


def test_withdraw_principal_after_partial_undelegate_in_same_round(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    consensus = register_candidate(operator=operator)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    assert tracker0.delta() == 0 - delegate_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    turn_round([consensus], round_count=3)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == delegate_amount


def test_undelegate_and_claiming_multiple_rounds(pledge_agent, validator_set, candidate_hub):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    consensus = register_candidate(operator=operator)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    assert tracker0.delta() == 0 - delegate_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == 0
    turn_round([consensus])
    pledge_agent.undelegateCoin(operator, undelegate_amount // 2, {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2
    remain_pledged_amount -= undelegate_amount
    total_pledged_amount -= undelegate_amount
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    turn_round([consensus], round_count=2)
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount
    pledge_agent.undelegateCoin(operator, undelegate_amount // 2, {'from': accounts[0]})
    remain_pledged_amount -= undelegate_amount // 2
    total_pledged_amount -= undelegate_amount // 2
    current_round_reward1 = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker0.delta() == current_round_reward + current_round_reward1
    turn_round([consensus], round_count=3)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == current_round_reward1
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount


def test_claim_rewards_each_round_after_undelegate_transfer_delegate(pledge_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 5
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
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount, {'from': accounts[0]})
    remain_pledged_amount2 = transfer_amount
    total_pledged_amount2 = transfer_amount + delegate_amount
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = pledge_agent.getDelegator(operators[1], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount * 2 - transfer_amount
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    account1_reward = total_reward - current_round_reward
    assert delegator_info1['newDeposit'] == transfer_amount
    assert tracker0.delta() == current_round_reward
    assert tracker1.delta() == account1_reward + total_reward
    turn_round(consensuses)
    remain_pledged_amount += delegate_amount
    total_pledged_amount += delegate_amount
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount
    account1_reward = total_reward - current_round_reward
    assert tracker0.delta() == current_round_reward
    assert tracker1.delta() == account1_reward + total_reward

    turn_round(consensuses, round_count=4)
    remain_pledged_amount -= transfer_amount
    total_pledged_amount -= transfer_amount
    account0_current_round_reward = total_reward * remain_pledged_amount // total_pledged_amount + total_reward * remain_pledged_amount2 // total_pledged_amount2
    remain_pledged_amount -= undelegate_amount
    total_pledged_amount -= undelegate_amount
    account0_current_round_reward2 = total_reward * remain_pledged_amount // total_pledged_amount + total_reward * remain_pledged_amount2 // total_pledged_amount2
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    account1_reward = (total_reward * 2 - account0_current_round_reward) + (
            total_reward * 6 - account0_current_round_reward2 * 3)
    assert tracker0.delta() == account0_current_round_reward + account0_current_round_reward2 * 3
    assert tracker1.delta() == account1_reward
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount


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
    validators = validator_set.getValidators()
    assert len(validators) == 2
    assert operators[2] not in validators
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round(consensuses, round_count=3)
    delegator_info0 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == MIN_INIT_DELEGATE_VALUE
    pledge_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == 0
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    turn_round(consensuses, round_count=3)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == 0
    delegator_info0 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == 0
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.delegateCoin(operators[2], {"value": DELEGATE_VALUE, 'from': accounts[0]})
    assert tracker0.delta() == 0 - DELEGATE_VALUE
    turn_round(consensuses, round_count=1)
    candidate_hub.refuseDelegate({'from': operators[2]})
    pledge_agent.undelegateCoin(operators[2], DELEGATE_VALUE, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    pledge_agent.claimReward([operators[2]], {'from': accounts[0]})
    assert tracker0.delta() == BLOCK_REWARD // 2
    turn_round(consensuses, round_count=2)
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == DELEGATE_VALUE


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
    pledge_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    tracker0.update_height()
    turn_round([consensus], round_count=3)
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": DELEGATE_VALUE, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    pledge_agent.undelegateCoin(operator, DELEGATE_VALUE + MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round([consensus], round_count=2)
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0 - DELEGATE_VALUE
    turn_round([consensus])
    pledge_agent.claimReward([consensus], {'from': accounts[0]})
    assert tracker0.delta() == 0
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == DELEGATE_VALUE + MIN_INIT_DELEGATE_VALUE


def test_withdraw_principal_from_multiple_validators(pledge_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
    total_reward = BLOCK_REWARD // 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amout = delegate_amount // 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    pledge_agent.undelegateCoin(operators[0], undelegate_amout, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], undelegate_amout, {'from': accounts[0]})
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amout * 2
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    assert tracker0.delta() == total_reward * 6


def test_undelgate_and_withdraw_principal_after_changing_locking_round(pledge_agent, validator_set, candidate_hub):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount // 4
    remain_pledged_amount = delegate_amount
    consensus = register_candidate(operator=operator)
    turn_round()
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.undelegateCoin(operator, delegate_amount // 5, {'from': accounts[0]})
    turn_round([consensus])
    pledge_agent.undelegateCoin(operator, delegate_amount // 6, {'from': accounts[0]})
    pledge_agent.setUndelegateLockTurns(1)
    pledge_agent.undelegateCoin(operator, undelegate_amount // 2, {'from': accounts[0]})
    turn_round([consensus])
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount // 2
    delegator_info0 = pledge_agent.getDelegator(operator, accounts[0])
    assert delegator_info0['newDeposit'] == remain_pledged_amount - delegate_amount \
           // 5 - delegate_amount // 6 - undelegate_amount // 2
    turn_round([consensus], round_count=2)
    pledge_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    turn_round([consensus])
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == delegate_amount // 5 + delegate_amount // 6 + MIN_INIT_DELEGATE_VALUE


def test_transfer_preserve_rewards_in_same_round(pledge_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount
    assert delegator_info2['newDeposit'] == 0
    turn_round()
    candidate_hub.acceptDelegate({'from': operators[2]})
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount - transfer_amount
    assert delegator_info2['newDeposit'] == transfer_amount
    total_reward = BLOCK_REWARD // 2
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    assert tracker0.delta() == total_reward // 2
    assert tracker1.delta() == total_reward - total_reward // 2
    pledge_agent.transferCoin(operators[0], operators[2], 0)
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == 0
    assert pledge_agent.getDelegator(operators[2], accounts[0])['newDeposit'] == delegate_amount
    turn_round(consensuses)
    pledge_agent.claimReward([operators[0]], {'from': accounts[0]})
    pledge_agent.claimReward([operators[0]], {'from': accounts[1]})
    remain_pledged_amount = delegate_amount - transfer_amount
    total_pledged_amount = delegate_amount * 2 - transfer_amount
    actual_reward = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker0.delta() == actual_reward
    assert tracker1.delta() == total_reward - actual_reward


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


def test_claim_reward_after_partially_transfer_to_candidate(pledge_agent, candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 2
    assert operators[2] not in validators
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    delegator_info0 = pledge_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = pledge_agent.getDelegator(operators[2], accounts[0])
    assert delegator_info0['newDeposit'] == delegate_amount
    assert delegator_info2['newDeposit'] == 0
    turn_round()
    total_reward = BLOCK_REWARD // 2
    candidate_hub.acceptDelegate({'from': operators[2]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount)
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_amount - transfer_amount
    assert pledge_agent.getDelegator(operators[2], accounts[0])['newDeposit'] == transfer_amount
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    remain_pledged_amount = delegate_amount - transfer_amount
    total_pledged_amount = delegate_amount * 2 - transfer_amount
    actual_reward = total_reward * remain_pledged_amount // total_pledged_amount
    assert tracker0.delta() == total_reward // 2 + actual_reward
    assert tracker1.delta() == total_reward * 2 - (actual_reward + total_reward // 2)


def test_claim_reward_after_partially_transfer_to_validator(pledge_agent, candidate_hub, validator_set):
    operators = []
    consensuses = []
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    transfer_amount0 = delegate_amount // 3
    transfer_amount1 = delegate_amount // 2
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 3
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_amount
    assert pledge_agent.getDelegator(operators[0], accounts[1])['newDeposit'] == delegate_amount
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == 0
    assert pledge_agent.getDelegator(operators[1], accounts[1])['newDeposit'] == 0
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount1, {'from': accounts[1]})
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_amount - transfer_amount0
    assert pledge_agent.getDelegator(operators[0], accounts[1])['newDeposit'] == delegate_amount - transfer_amount1
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == transfer_amount0
    assert pledge_agent.getDelegator(operators[1], accounts[1])['newDeposit'] == transfer_amount1

    total_reward = BLOCK_REWARD // 2
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    expected_reward0 = total_reward * remain_pledged_amount // total_pledged_amount
    expected_reward1 = total_reward - expected_reward0

    operator1_reward0 = total_reward * transfer_amount0 // (transfer_amount0 + transfer_amount1)
    operator1_reward1 = total_reward - operator1_reward0
    remain_pledged_amount = delegate_amount - transfer_amount0
    total_pledged_amount = delegate_amount * 2 - transfer_amount0 - transfer_amount1
    operator0_reward0 = total_reward * remain_pledged_amount // total_pledged_amount
    operator0_reward1 = total_reward - operator0_reward0
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == expected_reward0 + operator1_reward0 + operator0_reward0
    assert tracker1.delta() == expected_reward1 + operator1_reward1 + operator0_reward1


def test_claim_reward_after_full_transfer_to_validator(pledge_agent, candidate_hub, validator_set):
    operators = []
    consensuses = []
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    transfer_amount1 = delegate_amount
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_amount
    assert pledge_agent.getDelegator(operators[0], accounts[1])['newDeposit'] == delegate_amount
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == 0
    assert pledge_agent.getDelegator(operators[1], accounts[1])['newDeposit'] == 0
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.transferCoin(operators[0], operators[1], 0, {'from': accounts[0]})
    pledge_agent.transferCoin(operators[0], operators[1], transfer_amount1, {'from': accounts[1]})
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == 0
    assert pledge_agent.getDelegator(operators[0], accounts[1])['newDeposit'] == 0
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == delegate_amount
    assert pledge_agent.getDelegator(operators[1], accounts[1])['newDeposit'] == delegate_amount
    total_reward = BLOCK_REWARD // 2
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    expected_reward0 = total_reward * remain_pledged_amount // total_pledged_amount
    turn_round(consensuses, round_count=2)
    pledge_agent.claimReward(operators, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})

    assert tracker0.delta() == expected_reward0 * 2
    assert tracker1.delta() == total_reward * 2 - expected_reward0 * 2


def test_claim_reward_after_partially_transfer_to_duplicated_validator(pledge_agent, candidate_hub, validator_set):
    operators = []
    consensuses = []
    clients = accounts[:2]
    delegate_value = MIN_INIT_DELEGATE_VALUE * 5
    transfer_value0 = delegate_value // 3
    for operator in accounts[2:4]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
        for client in clients:
            pledge_agent.delegateCoin(operator, {"value": delegate_value, "from": client})
    turn_round()
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_value
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == delegate_value
    pledge_agent.transferCoin(operators[0], operators[1], transfer_value0, {"from": clients[0]})
    assert pledge_agent.getDelegator(operators[0], accounts[0])['newDeposit'] == delegate_value - transfer_value0
    assert pledge_agent.getDelegator(operators[1], accounts[0])['newDeposit'] == delegate_value + transfer_value0
    total_reward = BLOCK_REWARD // 2
    expected_reward0 = total_reward // 2
    expected_reward1 = total_reward - expected_reward0
    turn_round(consensuses, round_count=2)
    operator1_reward0 = total_reward // 2
    operator1_reward1 = total_reward - operator1_reward0
    operator0_round2_reward0 = total_reward * (delegate_value - transfer_value0) // (
            delegate_value - transfer_value0 + delegate_value)
    operator0_round2_reward1 = total_reward - operator0_round2_reward0
    operator1_round2_reward0 = total_reward * (delegate_value + transfer_value0) // (
            delegate_value + transfer_value0 + delegate_value)
    operator1_round2_reward1 = total_reward - operator1_round2_reward0
    tracker0 = get_tracker(clients[0])
    tracker1 = get_tracker(clients[1])
    for client in clients:
        pledge_agent.claimReward(operators, {'from': client})
    assert tracker0.delta() == expected_reward0 + operator1_reward0 + operator0_round2_reward0 + operator1_round2_reward0
    assert tracker1.delta() == expected_reward1 + operator1_reward1 + operator0_round2_reward1 + operator1_round2_reward1


def test_partially_transfer_to_unregister(pledge_agent, candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    operator = accounts[2]
    operator1 = accounts[3]
    register_candidate(operator=operator)
    register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator1})
    turn_round()
    error_msg = encode_args_with_signature("InactiveAgent(address)", [operator1.address])
    print(operator1.address)
    print(error_msg)
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.transferCoin(operator, operator1, transfer_amount, {"from": accounts[0]})


def test_unregister_validator_partially_transfer_to_validator(pledge_agent, candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    operator = accounts[2]
    operator1 = accounts[3]
    consensus = register_candidate(operator=operator)
    consensus1 = register_candidate(operator=operator1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    assert pledge_agent.getDelegator(operator, accounts[0])['newDeposit'] == delegate_amount
    candidate_hub.unregister({'from': operator})
    turn_round()
    pledge_agent.transferCoin(operator, operator1, transfer_amount, {"from": accounts[0]})
    assert pledge_agent.getDelegator(operator, accounts[0])['newDeposit'] == delegate_amount - transfer_amount
    turn_round([consensus, consensus1], round_count=2)
    pledge_agent.claimReward([operator, operator1], {'from': accounts[0]})
    assert tracker0.delta() == BLOCK_REWARD // 2


def test_withdraw_principal_after_redelegate(pledge_agent, candidate_hub, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.undelegateCoin(operator, {'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus], round_count=3)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == total_reward // 2 * 3
    assert tracker1.delta() == total_reward * 3 - (total_reward // 2 * 3)
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == delegate_amount


def test_withdraw_principal_after_redelegate_second_round(pledge_agent, candidate_hub, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.undelegateCoin(operator, {'from': accounts[0]})
    turn_round()
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus], round_count=2)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == total_reward // 2
    assert tracker1.delta() == total_reward * 2 - (total_reward // 2)
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == delegate_amount


def test_withdraw_principal_after_redelegate_alternate_rounds(pledge_agent, candidate_hub, validator_set):
    total_reward = BLOCK_REWARD // 2
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.undelegateCoin(operator, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 2
    turn_round([consensus], round_count=1)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    assert tracker0.delta() == 0 - delegate_amount
    turn_round([consensus], round_count=1)
    pledge_agent.claimReward([operator], {'from': accounts[0]})
    pledge_agent.claimReward([operator], {'from': accounts[1]})
    assert tracker0.delta() == 0
    assert tracker1.delta() == total_reward * 3 - (total_reward // 2)
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == delegate_amount


@pytest.mark.parametrize("round", [1, 2, 3, 4, 5])
def test_withdraw_principal_after_lock_duration_update(pledge_agent, candidate_hub, validator_set, round):
    pledge_agent.setUndelegateLockTurns(round)
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})

    turn_round()
    pledge_agent.undelegateCoin(operator, delegate_amount // 3, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operator, {'from': accounts[1]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    for r in range(round):
        turn_round([consensus])
        if r != round - 1:
            pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
            pledge_agent.claimUnlockedDeposit({'from': accounts[1]})
            locked = pledge_agent.getLockingDeposit(accounts[0])
            assert locked == delegate_amount // 3
            assert tracker0.delta() == 0
            assert tracker1.delta() == 0
        else:
            locked = pledge_agent.getLockingDeposit(accounts[0])
            assert locked == 0
            pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
            pledge_agent.claimUnlockedDeposit({'from': accounts[1]})
            assert tracker0.delta() == delegate_amount // 3
            assert tracker1.delta() == delegate_amount


@pytest.mark.parametrize("round", [1, 2, 3, 4, 5])
def test_claim_reward_after_lock_duration_update(pledge_agent, candidate_hub, validator_set, round):
    pledge_agent.setUndelegateLockTurns(round)
    operators = []
    consensuses = []
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    pledge_agent.undelegateCoin(operators[0], delegate_amount // 3, {'from': accounts[0]})
    pledge_agent.undelegateCoin(operators[1], 0, {'from': accounts[1]})
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    for r in range(round):
        turn_round(consensuses)
        pledge_agent.claimReward(operators, {'from': accounts[0]})
        pledge_agent.claimReward(operators, {'from': accounts[1]})
        assert tracker0.delta() == BLOCK_REWARD // 2
        if r == 0:
            assert tracker1.delta() == BLOCK_REWARD // 2
        else:
            assert tracker1.delta() == 0


def test_get_principal_during_lock_period(pledge_agent, candidate_hub, validator_set):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount0 = delegate_amount // 4
    undelegate_amount1 = delegate_amount // 3
    consensus = register_candidate(operator=operator)
    pledge_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    locked = pledge_agent.getLockingDeposit(accounts[0])
    assert locked == 0
    pledge_agent.undelegateCoin(operator, undelegate_amount0, {'from': accounts[0]})
    locked = pledge_agent.getLockingDeposit(accounts[0])
    assert locked == undelegate_amount0
    turn_round([consensus], round_count=1)
    pledge_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[0]})
    locked = pledge_agent.getLockingDeposit(accounts[0])
    assert locked == undelegate_amount0 + undelegate_amount1
    turn_round([consensus], round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimUnlockedDeposit({'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount0
    locked = pledge_agent.getLockingDeposit(accounts[0])
    assert locked == undelegate_amount1
