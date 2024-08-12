import brownie
import pytest
from .common import register_candidate, turn_round, stake_hub_claim_reward
from .delegate import *
from .utils import *
from .calc_reward import parse_delegation, set_delegate, calculate_coin_rewards

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
TOTAL_REWARD = 0
COIN_REWARD = 0
TX_FEE = 100


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[-11].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_min_init_delegate_value(min_init_delegate_value):
    global MIN_INIT_DELEGATE_VALUE
    MIN_INIT_DELEGATE_VALUE = min_init_delegate_value


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, core_agent):
    global BLOCK_REWARD, TOTAL_REWARD
    global COIN_REWARD, CORE_AGENT
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    COIN_REWARD = TOTAL_REWARD
    CORE_AGENT = core_agent


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


@pytest.mark.parametrize("claim_type", ["claim", "delegate", "undelegate", "transfer"])
def test_delegate_once(core_agent, validator_set, claim_type, stake_hub):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    # Core staking can earn up to 50% of the total rewards
    assert consensus in validator_set.getValidators()

    turn_round([consensus])
    tracker = get_tracker(accounts[0])

    if claim_type == "claim":
        stake_hub.claimReward()
        assert tracker.delta() == COIN_REWARD
    elif claim_type == "delegate":
        # delegate do not automatically method historical rewards
        core_agent.delegateCoin(operator, {"value": 100})
        assert tracker.delta() == -100
    elif claim_type == "undelegate":
        # undelegate do not automatically method historical rewards
        core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)
        assert tracker.delta() == MIN_INIT_DELEGATE_VALUE
    elif claim_type == "transfer":
        register_candidate(operator=accounts[2])
        # transfer do not automatically method historical rewards
        core_agent.transferCoin(operator, accounts[2], MIN_INIT_DELEGATE_VALUE)
        assert tracker.delta() == 0


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2one_agent_twice_in_different_rounds(core_agent, set_candidate, internal, stake_hub):
    operators, consensuses = set_candidate
    turn_round()
    for _ in range(2):
        core_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round(round_count=internal)
    if internal == 0:
        turn_round()
    turn_round(consensuses)

    tracker = get_tracker(accounts[0])
    stake_hub.claimReward()
    assert tracker.delta() == COIN_REWARD


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2two_agents_in_different_rounds(core_agent, internal, stake_hub):
    operators = []
    consensuses = []
    for operator in accounts[1:3]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    for operator in operators:
        core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
        turn_round(round_count=internal)
    if internal == 0:
        turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == COIN_REWARD * 2


def test_claim_reward_after_transfer_to_refuse_candidate(core_agent, candidate_hub, validator_set, set_candidate):
    operators, consensuses = set_candidate
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 2
    assert operators[2] not in validators
    core_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE})
    core_agent.delegateCoin(operators[1], {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    candidate_hub.acceptDelegate({'from': operators[2]})
    core_agent.transferCoin(operators[1], operators[2], MIN_INIT_DELEGATE_VALUE)
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 5


def test_claim_reward_after_transfer_to_duplicated_validator(core_agent, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    clients = accounts[:2]
    for operator in operators:
        for client in clients:
            core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, "from": client})
    turn_round()
    core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE, {"from": clients[0]})
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(clients[0])
    tracker1 = get_tracker(clients[1])
    stake_hub_claim_reward(clients)
    account_reward0 = TOTAL_REWARD * 3 // 2 + TOTAL_REWARD // 2 + (TOTAL_REWARD * 200 / 300)
    account_reward1 = TOTAL_REWARD * 3 // 2 + TOTAL_REWARD + TOTAL_REWARD // 2 + (TOTAL_REWARD * 100 / 300)
    assert tracker0.delta() == account_reward0
    assert tracker1.delta() == account_reward1


def test_undelegate_coin_next_round(core_agent, stake_hub):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round()
    core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE)
    turn_round([consensus])
    reward_sum = stake_hub.claimReward.call()
    assert reward_sum == [0, 0, 0]


def test_proxy_claim_reward_success(core_agent, stake_hub):
    pledge_agent_proxy = delegateCoinProxy.deploy(core_agent.address, stake_hub.address, {'from': accounts[0]})
    pledge_agent_proxy.setReceiveState(True)
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    tx = pledge_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "delegate", {"success": True})
    assert tx.events['delegatedCoin']['delegator'] == pledge_agent_proxy.address
    turn_round()
    turn_round([consensus])
    tx = pledge_agent_proxy.claimReward()
    expect_event(tx, "claim", {
        "allClaimed": True,
        "delegator": accounts[0],
        "rewards": [COIN_REWARD, 0, 0],
    })
    expect_event(tx, "claimedReward", {
        "delegator": pledge_agent_proxy.address,
        "amount": COIN_REWARD
    })
    assert core_agent.rewardMap(pledge_agent_proxy.address) == (0, 0)


def test_proxy_claim_reward_failed(core_agent, stake_hub):
    core_agent_proxy = delegateCoinProxy.deploy(core_agent.address, stake_hub.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    tx = core_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "delegate", {"success": True})
    turn_round()
    turn_round([consensus])
    core_agent_proxy.setReceiveState(False)
    assert core_agent.rewardMap(core_agent_proxy.address) == (0, 0)
    with brownie.reverts("call to claimReward failed"):
        core_agent_proxy.claimReward.call()


def test_delegate_coin_reentry(core_agent, stake_hub):
    core_agent_proxy = DelegateReentry.deploy(
        core_agent.address, stake_hub, {'from': accounts[0], 'value': MIN_INIT_DELEGATE_VALUE * 2})
    operators = accounts[1:3]
    consensus = []
    for _operator in operators:
        consensus.append(register_candidate(operator=_operator))
    core_agent_proxy.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    turn_round()
    turn_round(consensus)
    core_agent_proxy.setAgent(operators[0])
    tx = core_agent_proxy.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE})
    expect_event(tx, "proxyDelegate", {"success": True})
    assert core_agent_proxy.balance() == MIN_INIT_DELEGATE_VALUE * 2


def test_claim_reward_reentry(core_agent, stake_hub):
    core_agent_proxy = ClaimRewardReentry.deploy(core_agent.address, stake_hub.address, {'from': accounts[0]})
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    tx = core_agent_proxy.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    assert tx.events['delegatedCoin']['delegator'] == core_agent_proxy.address
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})
    turn_round()
    turn_round([consensus])
    assert stake_hub.balance() == COIN_REWARD
    tracker = get_tracker(core_agent_proxy)
    tx = core_agent_proxy.claimRewardNew()
    expect_event(tx, "proxyClaim", {
        "success": True
    })
    assert tracker.delta() == COIN_REWARD // 2


def test_claim_reward_after_undelegate_one_round(core_agent, validator_set, stake_hub):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    core_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    core_agent.undelegateCoin(operator, delegate_amount, {'from': accounts[1]})
    assert core_agent.rewardMap(accounts[0]) == [0, 0]
    assert tracker0.delta() == undelegate_amount
    assert tracker1.delta() == delegate_amount
    turn_round([consensus], round_count=1)
    delegator_map = core_agent.getDelegatorMap(accounts[0])
    assert delegator_map[1] == undelegate_amount
    delegator_info0 = core_agent.getDelegator(operator, accounts[0])
    assert delegator_info0[0] == delegate_amount // 2
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 4
    assert tracker1.delta() == 0


def test_claim_reward_after_undelegate_multiple_round(core_agent, validator_set, stake_hub):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount = delegate_amount // 2
    undelegate_amount1 = undelegate_amount // 2
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    core_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    core_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[1]})
    assert tracker0.delta() == undelegate_amount
    assert tracker1.delta() == undelegate_amount1
    remain_pledged_amount0 = delegate_amount - undelegate_amount
    remain_pledged_amount1 = delegate_amount - undelegate_amount1
    turn_round([consensus], round_count=1)
    _, _, account_rewards0, _ = parse_delegation([{
        "address": operator,
        "active": True,
        "coin": [set_delegate(accounts[0], delegate_amount, undelegate_amount),
                 set_delegate(accounts[1], delegate_amount, undelegate_amount1)],
        "power": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    core_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[0]})
    core_agent.undelegateCoin(operator, delegate_amount - undelegate_amount1, {'from': accounts[1]})
    _, _, account_rewards1, _ = parse_delegation([{
        "address": operator,
        "active": True,
        "coin": [set_delegate(accounts[0], remain_pledged_amount0, undelegate_amount1),
                 set_delegate(accounts[1], remain_pledged_amount1, delegate_amount - undelegate_amount1)],
        "power": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    turn_round([consensus], round_count=1)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == account_rewards0[accounts[0]] + account_rewards1[accounts[0]] + undelegate_amount1
    assert tracker1.delta() == account_rewards0[accounts[1]] + account_rewards1[
        accounts[1]] + delegate_amount - undelegate_amount1


def test_undelegate_all_coins_on_validator_and_claim_rewards(core_agent, validator_set):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    core_agent.undelegateCoin(operator, delegate_amount, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


def test_claim_reward_after_undelegate_coin_partially(core_agent, validator_set):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 8
    undelegate_amount = delegate_amount // 5
    undelegate_amount1 = delegate_amount // 7
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    core_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount
    remain_pledged_amount = delegate_amount - undelegate_amount
    total_pledged_amount = delegate_amount
    turn_round([consensus], round_count=1)
    _, _, account_rewards0, _ = parse_delegation([{
        "address": operator,
        "active": True,
        "coin": [set_delegate(accounts[0], delegate_amount, undelegate_amount)],
        "power": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == account_rewards0[accounts[0]]
    core_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    remain_pledged_amount -= undelegate_amount1
    total_pledged_amount -= undelegate_amount
    delegator_info0 = core_agent.getDelegator(operator, accounts[0])
    assert delegator_info0['stakedAmount'] == remain_pledged_amount
    assert delegator_info0['realtimeAmount'] == remain_pledged_amount
    assert delegator_info0['changeRound'] == get_current_round() - 1
    tracker0.update_height()
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards1, _ = parse_delegation([{
        "address": operator,
        "active": True,
        "coin": [set_delegate(accounts[0], total_pledged_amount, undelegate_amount1)],
        "power": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards1[accounts[0]]
    core_agent.undelegateCoin(operator, remain_pledged_amount, {'from': accounts[0]})
    turn_round([consensus], round_count=1)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == remain_pledged_amount


def test_multi_delegators_claim_reward_after_undelegate_coin_partially(core_agent, validator_set):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    undelegate_amount0 = delegate_amount // 2
    undelegate_amount1 = undelegate_amount0 // 2
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    core_agent.undelegateCoin(operator, undelegate_amount0, {'from': accounts[0]})
    core_agent.undelegateCoin(operator, undelegate_amount1, {'from': accounts[1]})
    total_pledged_amount = delegate_amount * 2
    turn_round([consensus], round_count=1)
    tracker0.update_height()
    tracker1.update_height()
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    actual_reward0 = COIN_REWARD * undelegate_amount0 // total_pledged_amount
    actual_reward1 = COIN_REWARD * (delegate_amount - undelegate_amount1) // total_pledged_amount
    assert tracker0.delta() == actual_reward0
    assert tracker1.delta() == actual_reward1


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_withdraw_principal(core_agent, validator_set, undelegate_type):
    operator = accounts[2]
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 8
    undelegate_amount = delegate_amount // 5
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
    register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    core_agent.undelegateCoin(operator, undelegate_amount, {'from': accounts[0]})
    assert tracker0.delta() == undelegate_amount


def test_claim_rewards_each_round_after_undelegate_or_delegate(core_agent, validator_set, candidate_hub):
    operators = []
    consensuses = []
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
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[1]})
    core_agent.delegateCoin(operators[1], {"value": delegate_amount, 'from': accounts[1]})
    turn_round()
    assert tracker0.delta() == 0 - delegate_amount
    assert tracker1.delta() == 0 - delegate_amount * 2
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, 'from': accounts[0]})
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == 0 - delegate_amount
    assert tracker1.delta() == 0
    turn_round(consensuses)
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == COIN_REWARD // 2 + undelegate_amount
    assert tracker1.delta() == COIN_REWARD // 2 + COIN_REWARD
    remain_pledged_amount = delegate_amount * 2 - undelegate_amount
    total_pledged_amount = delegate_amount * 3
    turn_round(consensuses)
    actual_reward0 = COIN_REWARD * remain_pledged_amount // total_pledged_amount
    actual_reward1 = COIN_REWARD * delegate_amount // total_pledged_amount + COIN_REWARD
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == actual_reward0
    assert tracker1.delta() == actual_reward1


def test_auto_reward_distribution_on_undelegate(core_agent, validator_set, candidate_hub):
    operator = accounts[2]
    operator1 = accounts[4]
    delegate_amount0 = MIN_INIT_DELEGATE_VALUE * 2
    consensus = register_candidate(operator=operator)
    consensus1 = register_candidate(operator=operator1)
    core_agent.delegateCoin(operator, {"value": delegate_amount0, 'from': accounts[0]})
    core_agent.delegateCoin(operator1, {"value": delegate_amount0, 'from': accounts[0]})
    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round([consensus1, consensus])
    core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[1]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    assert tracker1.delta() == MIN_INIT_DELEGATE_VALUE


def test_undelegate_claim_principal_for_candidate_node(core_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    core_agent.delegateCoin(operators[2], {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round()
    tracker0 = get_tracker(accounts[0])
    core_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    core_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tracker0.delta() == delegate_amount
    turn_round(consensuses, round_count=1)
    candidate_hub.acceptDelegate({'from': operators[2]})
    core_agent.delegateCoin(operators[2], {"value": delegate_amount * 5, 'from': accounts[0]})
    assert tracker0.delta() == 0 - delegate_amount * 5
    turn_round(consensuses, round_count=1)
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    total_delegate_amount = delegate_amount * 5
    core_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[0]})
    turn_round(consensuses, round_count=1)
    expect_reward = calculate_coin_rewards(total_delegate_amount - undelegate_amount, total_delegate_amount,
                                           COIN_REWARD)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + undelegate_amount
    core_agent.undelegateCoin(operators[2], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operators[2]})
    turn_round(consensuses, round_count=1)
    tracker0.update_height()
    total_delegate_amount -= undelegate_amount
    expect_reward = calculate_coin_rewards(total_delegate_amount - MIN_INIT_DELEGATE_VALUE, total_delegate_amount,
                                           COIN_REWARD)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


def test_undelegate_claim_principal_for_unregister_node(core_agent, validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operator = accounts[2]
    operator1 = accounts[3]
    tracker0 = get_tracker(accounts[0])
    consensus = register_candidate(operator=operator)
    register_candidate(operator=operator1)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == 1
    assert operator not in validators
    tracker0.update_height()
    core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tracker0.delta() == MIN_INIT_DELEGATE_VALUE
    turn_round([consensus], round_count=3)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    consensus = register_candidate(operator=operator)
    core_agent.delegateCoin(operator, {"value": delegate_amount, 'from': accounts[0]})
    candidate_hub.unregister({'from': operator})
    tx = core_agent.undelegateCoin(operator, MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    assert tx.events['undelegatedCoin']['amount'] == MIN_INIT_DELEGATE_VALUE
    turn_round([consensus], round_count=2)
    tx = core_agent.transferCoin(operator, operator1, delegate_amount, {'from': accounts[0]})
    assert tx.events['transferredCoin']['amount'] == MIN_INIT_DELEGATE_VALUE * 2
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == -100
    turn_round([consensus])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_transfer_with_partial_undelegate_and_claimed_rewards(core_agent, validator_set, candidate_hub,
                                                              undelegate_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    undelegate_amount = delegate_amount // 3
    if undelegate_type == 'all':
        undelegate_amount = delegate_amount
    operators = []
    remain_pledged_amount = delegate_amount
    total_pledged_amount = delegate_amount * 2
    consensuses = []
    for operator in accounts[3:6]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    operator = operators[0]
    delegate_coin_success(operator, accounts[0], delegate_amount)
    delegate_coin_success(operator, accounts[1], delegate_amount)
    delegate_coin_success(operators[1], accounts[2], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[0], accounts[1], undelegate_amount)
    transfer_coin_success(operators[1], operators[2], accounts[2], transfer_amount)
    turn_round(consensuses, round_count=1)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[1])
    remain_pledged_amount -= undelegate_amount
    expect_reward = COIN_REWARD * remain_pledged_amount // total_pledged_amount
    assert tracker1.delta() == expect_reward


def test_delegate_then_all_undelegate(core_agent, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    additional_amount = MIN_INIT_DELEGATE_VALUE * 3
    operator = accounts[2]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], delegate_amount)
    turn_round()
    delegate_coin_success(operator, accounts[0], additional_amount)
    tracker0 = get_tracker(accounts[0])
    undelegate_coin_success(operator, accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round([consensus], round_count=1)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD // 2 + MIN_INIT_DELEGATE_VALUE


def test_cancel_and_transfer_pledge_in_same_round(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 5
    transfer_amount1 = delegate_amount // 4
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount1)
    tx = undelegate_coin_success(operators[0], accounts[0], delegate_amount - transfer_amount)
    assert tx.events['undelegatedCoin']['amount'] == delegate_amount - transfer_amount
    tx = undelegate_coin_success(operators[2], accounts[0], delegate_amount - transfer_amount1)
    assert tx.events['undelegatedCoin']['amount'] == delegate_amount - transfer_amount1
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount - transfer_amount)],
        "power": [],
        "btc": []
    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(accounts[0], delegate_amount)],
        "power": [],
        "btc": []
    }, {
        "address": operators[2],
        "active": True,
        "coin": [set_delegate(accounts[0], delegate_amount, delegate_amount - transfer_amount1)],
        "power": [],
        "btc": []
    }], BLOCK_REWARD // 2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_all_validators_transfer_then_claim_reward(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 5
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount)
    for op in operators[:2]:
        undelegate_coin_success(op, accounts[0], undelegate_amount)
    undelegate_amount1 = transfer_amount + MIN_INIT_DELEGATE_VALUE * 2
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount1)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = COIN_REWARD * (delegate_amount - undelegate_amount) // delegate_amount
    expect_reward2 = COIN_REWARD * (delegate_amount - undelegate_amount1) // delegate_amount

    assert tracker0.delta() == expect_reward * 2 + expect_reward2


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_claim_undelegated_rewards_after_multiple_rounds(core_agent, validator_set, set_candidate, round_number):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = transfer_amount0 // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    core_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[0]})
    tracker0 = get_tracker(accounts[0])
    remain_reward = COIN_REWARD * (delegate_amount - undelegate_amount) // delegate_amount
    turn_round(consensuses, round_count=round_number)
    stake_hub_claim_reward(accounts[0])
    reward_round = round_number - 1
    expect_reward = remain_reward + COIN_REWARD * 2 * reward_round
    assert tracker0.delta() == expect_reward


def test_transfer_auto_claim_rewards(core_agent, candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 2
    operators = []
    consensuses = []
    for operator in accounts[2:5]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    assert tracker0.delta() == 0
    assert tracker1.delta() == 0


def test_claim_reward_after_transfer_coin(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    remain_pledged_amount0 = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount * 2)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    remain_pledged_amount0 -= transfer_amount

    expect_query(delegator_info0, {'stakedAmount': remain_pledged_amount0,
                                   'realtimeAmount': remain_pledged_amount0,
                                   'changeRound': 8, 'transferredAmount': transfer_amount})
    expect_query(delegator_info2, {'stakedAmount': 0,
                                   'realtimeAmount': transfer_amount,
                                   'changeRound': 8, 'transferredAmount': 0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    expect_reward0 = calculate_coin_rewards(delegate_amount, total_pledged_amount0, COIN_REWARD)
    expect_reward1 = calculate_coin_rewards(delegate_amount * 2, total_pledged_amount0, COIN_REWARD)
    assert tracker0.delta() == expect_reward0
    assert tracker1.delta() == expect_reward1
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    expect_reward0 = calculate_coin_rewards(delegate_amount - transfer_amount, total_pledged_amount0 - transfer_amount,
                                            COIN_REWARD)
    assert tracker0.delta() == expect_reward0 + COIN_REWARD


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_transfer_coin_and_undelegate_to_active_validator(core_agent, validator_set, candidate_hub, validator_type,
                                                          set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    validator_count = 2
    is_validator = False
    operators, consensuses = set_candidate
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount, COIN_REWARD)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    else:
        validator_count = 3
        is_validator = True
        expect_reward += COIN_REWARD
    turn_round()
    validators = validator_set.getValidators()
    assert validator_set.isValidator(consensuses[0]) == is_validator
    assert len(validators) == validator_count
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_transfer_coin_to_active_validator(core_agent, validator_set, candidate_hub, validator_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    expect_reward = 0
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    else:
        expect_reward = COIN_REWARD
    turn_round()
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'stakedAmount': 0,
                                   'realtimeAmount': delegate_amount, 'transferredAmount': 0})
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount - transfer_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister'])
def test_transfer_to_unregister_and_candidate_validator(core_agent, candidate_hub, validator_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = delegate_amount // 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[1]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[1]})
    turn_round()
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [operators[1].address])
    with brownie.reverts(f"{error_msg}"):
        transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)


def test_transfer_multiple_times_and_claim_rewards(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    turn_round(consensuses)
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    expect_query(delegator_info1, {'stakedAmount': 0, 'realtimeAmount': transfer_amount, 'transferredAmount': 0})
    tracker0 = get_tracker(accounts[0])
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD // 2
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info1,
                 {'stakedAmount': transfer_amount, 'realtimeAmount': transfer_amount * 2, 'transferredAmount': 0})
    expect_query(delegator_info0,
                 {'stakedAmount': delegate_amount - transfer_amount * 2,
                  'realtimeAmount': delegate_amount - transfer_amount * 2,
                  'transferredAmount': transfer_amount})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    remain_pledged_amount = delegate_amount - transfer_amount
    total_pledged_amount = delegate_amount * 2 - transfer_amount
    expect_reward = COIN_REWARD * remain_pledged_amount // total_pledged_amount
    assert tracker0.delta() == expect_reward + COIN_REWARD


@pytest.mark.parametrize("undelegate_amount", [400, 800, 900])
def test_transfer_to_existing_agent_and_cancel(core_agent, set_candidate, validator_set, undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    transfer_out_deposit0 = transfer_amount0
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    assert delegator_info0['transferredAmount'] == transfer_out_deposit0
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == expect_reward + COIN_REWARD // 2
    assert tracker1.delta() == calculate_coin_rewards(delegate_amount, delegate_amount * 2, COIN_REWARD) * 2


def test_transfer_to_queued_validator_and_cancel(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = transfer_amount0 - MIN_INIT_DELEGATE_VALUE
    operators, consensuses = set_candidate
    candidate_hub.setValidatorCount(2)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    turn_round(consensuses)
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    assert tracker0.delta() == expect_reward


def test_transfer_to_already_delegate_validator_in_queue(core_agent, validator_set, set_candidate, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = 500
    transfer_amount1 = 700
    undelegate_amount = 900
    operators, consensuses = set_candidate
    candidate_hub.setValidatorCount(2)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    delegate_coin_success(operators[1], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[1], delegate_amount)
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[1] not in validators
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    undelegate_coin_success(operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    # operators[1] are not rewarded
    assert tracker0.delta() == expect_reward + COIN_REWARD // 2


def test_multiple_transfers_and_undelegate_claim_rewards(core_agent, validator_set, candidate_hub, set_candidate):
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 9
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators:
            delegate_coin_success(op, accounts[i], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    for index, op in enumerate(operators):
        undelegate_amount = MIN_INIT_DELEGATE_VALUE * 5
        if index == 1:
            undelegate_amount = MIN_INIT_DELEGATE_VALUE
        undelegate_coin_success(op, accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward0 = calculate_coin_rewards(transfer_amount1, delegate_amount * 2, COIN_REWARD)
    expect_reward1 = calculate_coin_rewards(transfer_amount0, delegate_amount * 2, COIN_REWARD)
    assert tracker0.delta() == expect_reward0 + expect_reward1 * 2


@pytest.mark.parametrize("undelegate_amount", [500, 600, 650, 700, 750])
def test_add_cancel_transfer_then_claim_reward(core_agent, validator_set, candidate_hub, set_candidate,
                                               undelegate_amount):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    additional_amount = delegate_amount
    total_pledged_amount0 = delegate_amount * 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[3], delegate_amount * 2)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], additional_amount)
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward0 = calculate_coin_rewards(delegate_amount - undelegate_amount, total_pledged_amount0, COIN_REWARD)
    assert tracker0.delta() == expect_reward0


def test_claim_rewards_after_additional_and_transfer(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    additional_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 3
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], additional_amount)
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount1)
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    assert tracker0.delta() == reward + COIN_REWARD // 2


def test_transfer_and_delegate_with_reward_claim(core_agent, validator_set, candidate_hub, set_candidate):
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    additional_amount = MIN_INIT_DELEGATE_VALUE * 3
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    delegate_coin_success(operators[1], accounts[0], additional_amount)
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    assert tracker0.delta() == reward + COIN_REWARD // 2


def test_undelegate_and_transfer_with_rewards(core_agent, validator_set, candidate_hub, set_candidate):
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 3
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 6
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[1], delegate_amount * 2)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount1)
    expect_reward0 = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    expect_reward1 = calculate_coin_rewards(delegate_amount, delegate_amount * 3, COIN_REWARD)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward0 + expect_reward1 + COIN_REWARD // 2


def test_transfer_to_same_validator_and_undelegate(core_agent, validator_set, candidate_hub, set_candidate):
    candidate_hub.setValidatorCount(21)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 3
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 8
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount1)
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    assert tracker0.delta() == COIN_REWARD + expect_reward + COIN_REWARD // 2


def test_transfer_and_delegate_and_then_transfer(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = MIN_INIT_DELEGATE_VALUE * 5
    additional_amount = MIN_INIT_DELEGATE_VALUE * 6
    transfer_amount1 = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    for op in operators[:2]:
        delegate_coin_success(op, accounts[0], delegate_amount)
    for op in operators[1:3]:
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    delegate_coin_success(operators[1], accounts[0], additional_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD + COIN_REWARD // 2


def test_transfer_then_validator_refuses_delegate(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 5
    transfer_amount = MIN_INIT_DELEGATE_VALUE * 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    candidate_hub.refuseDelegate({'from': operators[2]})
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount, COIN_REWARD)
    assert tracker0.delta() == expect_reward + COIN_REWARD


def test_unstake_except_transfer_then_claim_reward(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 11
    transfer_amount = MIN_INIT_DELEGATE_VALUE
    transfer_amount2 = MIN_INIT_DELEGATE_VALUE * 4
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    for i in range(2):
        # 0 tr 1 & 1 tr 0
        # 0 tr 2 & 2 tr 0
        transfer_coin_success(operators[0], operators[i + 1], accounts[0], transfer_amount)
        transfer_coin_success(operators[i + 1], operators[0], accounts[0], transfer_amount2)
    for index, op in enumerate(operators):
        undelegate_amount = delegate_amount - transfer_amount2
        if index == 0:
            undelegate_amount = delegate_amount - transfer_amount * 2
        undelegate_coin_success(op, accounts[0], undelegate_amount)
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0,
                 {'stakedAmount': 0, 'realtimeAmount': transfer_amount2 * 2, 'transferredAmount': transfer_amount * 2})
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    expect_reward0 = calculate_coin_rewards(transfer_amount * 2, delegate_amount, COIN_REWARD)
    expect_reward1 = calculate_coin_rewards(transfer_amount2, delegate_amount, COIN_REWARD)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward0 + expect_reward1 * 2


def test_transfer_and_check_transfer_info(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    transfer_amount2 = delegate_amount // 4
    operators, consensuses = set_candidate
    for i in range(2):
        for index, op in enumerate(operators[1:3]):
            delegate_coin_success(op, accounts[i], delegate_amount)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    tx = transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount2)
    expect_event(tx, "transferredCoin", {
        "sourceCandidate": operators[2],
        "targetCandidate": operators[0],
        "delegator": accounts[0],
        "amount": transfer_amount1,
        "realtimeAmount": delegate_amount - transfer_amount0 + transfer_amount1,
    })
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'realtimeAmount': delegate_amount - transfer_amount0 + transfer_amount2,
                                   'transferredAmount': transfer_amount0})
    expect_query(delegator_info1, {'realtimeAmount': delegate_amount + transfer_amount0 - transfer_amount1,
                                   'transferredAmount': transfer_amount1})
    expect_query(delegator_info2, {'realtimeAmount': delegate_amount + transfer_amount1 - transfer_amount2,
                                   'transferredAmount': transfer_amount2})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD + COIN_REWARD // 2 * 2


def test_multiple_transfers_and_check_transfer_info(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    transfer_amount2 = delegate_amount // 3
    undelegate_amount = transfer_amount1 + MIN_INIT_DELEGATE_VALUE
    operators, consensuses = set_candidate
    for i in range(2):
        for index, op in enumerate(operators[1:3]):
            delegate_coin_success(op, accounts[i], delegate_amount)
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    new_deposit1 = delegate_amount - transfer_amount1
    new_deposit2 = delegate_amount + transfer_amount0 + transfer_amount1
    expect_query(delegator_info0,
                 {'stakedAmount': transfer_amount0, 'realtimeAmount': delegate_amount - transfer_amount0,
                  'transferredAmount': transfer_amount0})
    expect_query(delegator_info1,
                 {'realtimeAmount': new_deposit1, 'transferredAmount': transfer_amount1})
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    new_deposit2 -= undelegate_amount
    new_deposit1 -= transfer_amount2
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount2)
    new_deposit2 += transfer_amount2
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info1,
                 {'realtimeAmount': new_deposit1, 'transferredAmount': transfer_amount1 + transfer_amount2})
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2, COIN_REWARD)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + COIN_REWARD + COIN_REWARD // 2


def test_transfer_info_accumulation(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    new_deposit0 = delegate_amount
    new_deposit2 = delegate_amount
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    new_deposit0 -= transfer_amount0
    new_deposit2 += transfer_amount0
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0, {'realtimeAmount': new_deposit0, 'transferredAmount': transfer_amount0})
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount1)
    new_deposit0 -= transfer_amount1
    new_deposit2 += transfer_amount1
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info0,
                 {'realtimeAmount': new_deposit0, 'transferredAmount': transfer_amount0 + transfer_amount1})
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    new_deposit2 += transfer_amount1 * 2
    delegator_info1 = core_agent.getDelegator(operators[1], accounts[0])
    delegator_info2 = core_agent.getDelegator(operators[2], accounts[0])
    expect_query(delegator_info1,
                 {'realtimeAmount': delegate_amount - transfer_amount1 * 2, 'transferredAmount': transfer_amount1 * 2})
    expect_query(delegator_info2, {'realtimeAmount': new_deposit2, 'transferredAmount': 0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 3


def test_batch_transfer_to_multiple_validators(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    for i in range(2):
        transfer_coin_success(operators[i], operators[2], accounts[0], transfer_amount0)
        transfer_coin_success(operators[2], operators[i], accounts[0], transfer_amount1)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 3


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_reward_claim_after_slash(core_agent, validator_set, slash_indicator, threshold_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx = None
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = COIN_REWARD
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'transferredAmount': transfer_amount})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    assert delegator_info0['transferredAmount'] == 0
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_reward_after_slash_and_transfer(core_agent, slash_indicator, threshold_type, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount = delegate_amount // 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx0 = None
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = COIN_REWARD
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward
    required_margin = 1000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=2)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_post_transfer_major_slash(core_agent, slash_indicator, threshold_type, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    transfer_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    tx0 = None
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount, COIN_REWARD)
        expect_reward1 = COIN_REWARD * 6
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = 0
        expect_reward1 = COIN_REWARD
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward
    required_margin = 100000000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=3)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward1


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_major_violation_followed_by_reward_claim(core_agent, slash_indicator, threshold_type, candidate_hub,
                                                  set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = MIN_INIT_DELEGATE_VALUE
    transfer_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[2], accounts[0], delegate_amount)
    turn_round()
    v1 = COIN_REWARD * Utils.CORE_STAKE_DECIMAL // (delegate_amount - transfer_amount)
    v2 = COIN_REWARD * Utils.CORE_STAKE_DECIMAL // (delegate_amount + transfer_amount - undelegate_amount)
    tx1 = None
    if threshold_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        expect_reward = COIN_REWARD + calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount,
                                                             COIN_REWARD)
        v1r = (delegate_amount - transfer_amount) * (v1 * 3) // Utils.CORE_STAKE_DECIMAL
        v2r = (delegate_amount + transfer_amount - undelegate_amount) * (v2 * 3) // Utils.CORE_STAKE_DECIMAL
        expect_reward1 = v1r + v2r
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
        expect_reward = COIN_REWARD
        v1r = (delegate_amount - transfer_amount) * (v1 * 3) // Utils.CORE_STAKE_DECIMAL
        v2r = (delegate_amount + transfer_amount - undelegate_amount) * v2 // Utils.CORE_STAKE_DECIMAL
        expect_reward1 = v1r + v2r
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[2], accounts[0], undelegate_amount)
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[2])
    assert event_name in tx1.events
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward
    required_margin = 100000000001
    candidate_hub.addMargin({'value': required_margin, 'from': operators[2]})
    turn_round(consensuses, round_count=3)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward1


def test_claim_rewards_for_one_rounds(core_agent, validator_set, slash_indicator, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    delegate_amount0 = delegate_amount // 3
    delegate_amount1 = delegate_amount - delegate_amount // 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount0)
    delegate_coin_success(operators[1], accounts[0], delegate_amount1)
    turn_round()
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount0)],
        "btc": []
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount1)],
        "btc": []
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_claim_rewards_for_three_rounds(core_agent, validator_set, slash_indicator, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    delegate_amount0 = delegate_amount // 3
    delegate_amount1 = delegate_amount - delegate_amount // 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount0)
    delegate_coin_success(operators[1], accounts[0], delegate_amount1)
    turn_round()
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    v1 = COIN_REWARD * Utils.CORE_STAKE_DECIMAL // delegate_amount0
    v2 = COIN_REWARD * Utils.CORE_STAKE_DECIMAL // delegate_amount1
    v1r = delegate_amount0 * v1 // Utils.CORE_STAKE_DECIMAL
    v2r = delegate_amount1 * v2 // Utils.CORE_STAKE_DECIMAL
    assert tracker0.delta() == v1r + v2r
    turn_round(consensuses, round_count=3)
    v1r = delegate_amount0 * (v1 * 3) // Utils.CORE_STAKE_DECIMAL
    v2r = delegate_amount1 * (v2 * 3) // Utils.CORE_STAKE_DECIMAL
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == v1r + v2r


def test_undelegate_then_transfer(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 4
    undelegate_amount = delegate_amount // 6
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'realtimeAmount': delegate_amount - undelegate_amount - transfer_amount0,
                                   'transferredAmount': transfer_amount0})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount, COIN_REWARD)
    assert tracker0.delta() == expect_reward


def test_batch_transfer_to_one_validator(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = delegate_amount // 4
    operators, consensuses = set_candidate
    for op in operators[:2]:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount1)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 2


def test_transfer_after_claim_reward(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD


def test_reward_claim_midway_doesnt_affect_current_round(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'transferredAmount': transfer_amount0})
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount, COIN_REWARD)
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("undelegate_amount", [400, 800])
def test_transfer_and_undelegate_in_different_rounds(core_agent, validator_set, undelegate_amount, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators, consensuses = set_candidate
    for i in range(2):
        for op in operators[:2]:
            delegate_coin_success(op, accounts[i], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    undelegate_coin_success(operators[1], accounts[0], undelegate_amount)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD // 2 * 2 + undelegate_amount
    turn_round(consensuses)
    expect_reward0 = calculate_coin_rewards(delegate_amount - transfer_amount0, delegate_amount * 2 - transfer_amount0,
                                            COIN_REWARD)
    expect_reward1 = calculate_coin_rewards(delegate_amount + transfer_amount0 - undelegate_amount,
                                            delegate_amount * 2 + transfer_amount0, COIN_REWARD)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward0 + expect_reward1


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operations_in_next_round_after_transfer(core_agent, validator_set, operator_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    if operator_type == 'undelegate':
        undelegate_coin_success(operators[2], accounts[0], operation_amount)
        expect_reward0 = operation_amount
        expect_reward1 = calculate_coin_rewards(delegate_amount - operation_amount, transfer_amount0,
                                                COIN_REWARD) + COIN_REWARD
    elif operator_type == 'transfer':
        transfer_coin_success(operators[2], operators[1], accounts[0], operation_amount)
        expect_reward0 = 0
        expect_reward1 = COIN_REWARD * 3
    elif operator_type == 'claim':
        stake_hub_claim_reward(accounts[0])
        expect_reward0 = COIN_REWARD
        expect_reward1 = COIN_REWARD * 2
    else:
        delegate_coin_success(operators[2], accounts[0], operation_amount)
        expect_reward0 = -operation_amount
        expect_reward1 = COIN_REWARD * 3
    assert tracker0.delta() == expect_reward0
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward1


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operations_in_current_round_after_transfer(core_agent, validator_set, operator_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    if operator_type == 'undelegate':
        undelegate_coin_success(operators[0], accounts[0], operation_amount)
        expect_reward = calculate_coin_rewards(delegate_amount - operation_amount, delegate_amount, COIN_REWARD)
    elif operator_type == 'transfer':
        transfer_coin_success(operators[0], operators[1], accounts[0], operation_amount)
        expect_reward = COIN_REWARD
    elif operator_type == 'claim':
        tx = stake_hub_claim_reward(accounts[0])
        assert 'claimedReward' not in tx.events
        expect_reward = COIN_REWARD
    else:
        delegate_coin_success(operators[0], accounts[0], operation_amount)
        expect_reward = COIN_REWARD
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


def test_transfer_to_validator_with_existing_transfers(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators, consensuses = set_candidate
    for op in operators[:2]:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    transfer_coin_success(operators[1], operators[2], accounts[0], operation_amount)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 2
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 3


@pytest.mark.parametrize("operator_type", ['undelegate', 'delegate', 'transfer', 'claim'])
def test_operation_on_validator_with_no_transfer(core_agent, validator_set, operator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operation_amount = delegate_amount // 4
    operators = []
    consensuses = []
    for operator in accounts[4:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for op in operators[:2]:
        delegate_coin_success(op, accounts[0], delegate_amount)
    delegate_coin_success(operators[3], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'transferredAmount': transfer_amount0})
    expect_reward = COIN_REWARD * 4
    if operator_type == 'undelegate':
        undelegate_coin_success(operators[3], accounts[0], operation_amount)
        remain_reward = COIN_REWARD * 3 + operation_amount
        expect_reward = COIN_REWARD * 3 + calculate_coin_rewards(delegate_amount - operation_amount, delegate_amount,
                                                                 COIN_REWARD)
    elif operator_type == 'transfer':
        transfer_coin_success(operators[3], operators[4], accounts[0], operation_amount)
        remain_reward = COIN_REWARD * 3
    elif operator_type == 'claim':
        tx = stake_hub_claim_reward(accounts[0])
        assert 'claimedReward' in tx.events
        assert tx.events['claimedReward']['amount'] == COIN_REWARD * 3
        remain_reward = COIN_REWARD * 3
    else:
        delegate_coin_success(operators[3], accounts[0], operation_amount)
        remain_reward = COIN_REWARD * 3 - operation_amount
    stake_hub_claim_reward(accounts[0])
    delegator_info0 = core_agent.getDelegator(operators[0], accounts[0])
    expect_query(delegator_info0, {'transferredAmount': 0})
    assert tracker0.delta() == remain_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


def test_transfer_and_delegate_in_different_rounds(core_agent, validator_set, set_candidate):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 4
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD // 2
    delegate_coin_success(operators[0], accounts[0], additional_delegate)
    turn_round(consensuses)
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount1)
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - transfer_amount0, delegate_amount * 2 - transfer_amount0,
                                           COIN_REWARD) + COIN_REWARD - additional_delegate
    assert tracker0.delta() == expect_reward
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    expect_reward = COIN_REWARD + calculate_coin_rewards(delegate_amount - transfer_amount0 + additional_delegate,
                                                         delegate_amount * 2 - transfer_amount0 + additional_delegate,
                                                         COIN_REWARD)
    assert tracker0.delta() == expect_reward


def test_transfer_and_undelegate_and_delegate_in_different_rounds(core_agent, validator_set, set_candidate):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 3 / 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 3
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD + undelegate_amount
    delegate_coin_success(operators[2], accounts[0], additional_delegate)
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount1)
    new_deposit2 = transfer_amount0 + additional_delegate - transfer_amount1
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - transfer_amount0 - undelegate_amount,
                                           delegate_amount - transfer_amount0, COIN_REWARD) + COIN_REWARD
    assert tracker0.delta() == expect_reward - additional_delegate
    tracker0.update_height()
    transfer_coin_success(operators[2], operators[1], accounts[0], new_deposit2)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 3


def test_multiple_operations_in_different_rounds(core_agent, validator_set, set_candidate):
    additional_delegate = MIN_INIT_DELEGATE_VALUE * 3 / 2
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    transfer_amount1 = transfer_amount0 // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 2.5
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    delegate_coin_success(operators[0], accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    delegate_coin_success(operators[0], accounts[0], additional_delegate)
    stake_hub_claim_reward(accounts[0])
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount * 2,
                                           COIN_REWARD)
    assert tracker0.delta() == expect_reward - additional_delegate
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount1)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    tx = undelegate_coin_success(operators[0], accounts[0], additional_delegate)
    assert tx.events['undelegatedCoin']['amount'] == additional_delegate
    expect_reward = calculate_coin_rewards(delegate_amount - transfer_amount0 - undelegate_amount,
                                           delegate_amount * 2 - transfer_amount0 - undelegate_amount,
                                           COIN_REWARD)
    assert tracker0.delta() == expect_reward + COIN_REWARD + additional_delegate
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == COIN_REWARD * 2


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_transfer_rewards_and_claim_after_multiple_rounds(core_agent, validator_set, round_number, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=round_number)
    stake_hub_claim_reward(accounts[0])
    reward_round = round_number - 1
    expect_reward = COIN_REWARD + COIN_REWARD * 2 * reward_round
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_claim_rewards_after_transfer_and_undelegate_in_multiple_rounds(core_agent, validator_set, round_number,
                                                                        set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    transfer_amount0 = delegate_amount // 2
    undelegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount0)
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    tracker0 = get_tracker(accounts[0])
    turn_round(consensuses, round_count=round_number)
    stake_hub_claim_reward(accounts[0])
    reward_round = round_number - 1
    expect_reward = calculate_coin_rewards(delegate_amount - undelegate_amount, delegate_amount,
                                           COIN_REWARD) + COIN_REWARD * 2 * reward_round
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_succeeds_after_round_switch(core_agent, validator_set, operate, set_candidate):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round()
    turn_round()
    if operate == 'undelegate':
        tx = undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
        event = 'undelegatedCoin'
    else:
        tx = transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
        event = 'transferredCoin'
    assert event in tx.events


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_with_same_round_additional_stake_reverts(core_agent, validator_set, operate, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount + delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    if operate == 'undelegate':
        undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    else:
        transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_with_additional_stake_succeeds_after_round_switch(core_agent, validator_set, operate, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount + delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    if operate == 'undelegate':
        tx = undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
        event = 'undelegatedCoin'
    else:
        tx = transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)
        event = 'transferredCoin'
    assert event in tx.events


@pytest.mark.parametrize("threshold_type", ['minor', 'major'])
def test_stake_then_cancel_same_round_on_slashed_validator(core_agent, slash_indicator, threshold_type, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 4
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
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
    undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    turn_round()
    tx = undelegate_coin_success(operators[0], accounts[0], MIN_INIT_DELEGATE_VALUE)
    assert 'undelegatedCoin' in tx.events
    tx = transfer_coin_success(operators[0], operators[1], accounts[0], MIN_INIT_DELEGATE_VALUE)
    assert 'transferredCoin' in tx.events


@pytest.mark.parametrize("validator_type", ['candidate', 'unregister', 'active'])
def test_cancel_current_round_stake_on_validator_with_different_status(core_agent, candidate_hub, set_candidate,
                                                                       validator_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    if validator_type == 'candidate':
        candidate_hub.refuseDelegate({'from': operators[0]})
    elif validator_type == 'unregister':
        candidate_hub.unregister({'from': operators[0]})
    core_agent.undelegateCoin(operators[0], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})
    core_agent.transferCoin(operators[0], operators[1], MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_current_round_stake_and_transferred_amount(core_agent, validator_set, operate, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)
    if operate == 'undelegate':
        core_agent.undelegateCoin(operators[1], undelegate_amount, {'from': accounts[0]})
    else:
        core_agent.transferCoin(operators[1], operators[2], undelegate_amount, {'from': accounts[0]})


@pytest.mark.parametrize("operate", ['undelegate', 'transfer'])
def test_cancel_amount_transferred_in_current_round(core_agent, validator_set, operate, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    for op in operators[:2]:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], undelegate_amount)
    if operate == 'undelegate':
        tx = core_agent.undelegateCoin(operators[1], delegate_amount + 1, {'from': accounts[0]})
        event = 'undelegatedCoin'
    else:
        tx = core_agent.transferCoin(operators[1], operators[2], delegate_amount + 1, {'from': accounts[0]})
        event = 'transferredCoin'
    assert event in tx.events


def test_revert_on_cancel_amount_exceeding_stake(core_agent, validator_set, set_candidate):
    turn_round()
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_amount = delegate_amount // 2
    core_agent.transferCoin(operators[0], operators[1], delegate_amount, {'from': accounts[0]})
    with brownie.reverts("Not enough staked tokens"):
        core_agent.undelegateCoin(operators[0], transfer_amount + MIN_INIT_DELEGATE_VALUE, {'from': accounts[0]})


def test_register_new_validator_after_pledge(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    new_agent = accounts[8]
    consensus = register_candidate(operator=new_agent)
    operators.append(accounts[8])
    consensuses.append(consensus)
    transfer_amount = delegate_amount // 2
    transfer_coin_success(operators[0], operators[3], accounts[0], transfer_amount)
    delegate_coin_success(operators[3], accounts[0], delegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 2


def test_cancel_stake_immediately_after_transfer(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    turn_round()
    transfer_amount = delegate_amount // 2
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[2], accounts[0], transfer_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 2


@pytest.mark.parametrize("round_count", [0, 1, 2])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'candidate': 0, 'amount': 500, 'expect_reward': 3386, 'tow_round_reward': 13545 + 3386},
    {'transfer': 500, 'candidate': 2, 'amount': 500, 'expect_reward': 3386, 'tow_round_reward': 13545 // 3 + 3386},
    {'transfer': 500, 'candidate': 0, 'amount': 250, 'expect_reward': 13545 * 750 // 2000,
     'tow_round_reward': 13545 + 13545 * 750 // 2000 + 13545 * 250 // 1250},
    {'transfer': 500, 'candidate': 2, 'amount': 250, 'expect_reward': 13545 * 750 // 2000,
     'tow_round_reward': 13545 + 13545 * 750 // 2000 + 13545 * 500 // 1500}
])
def test_claim_reward_after_cancel_coin_transfer(core_agent, validator_set, set_candidate, tests, round_count):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['candidate']
    operators, consensuses = set_candidate
    for i in range(2):
        delegate_coin_success(operators[0], accounts[i], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses, round_count=round_count)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    if round_count == 0:
        expect_reward = 0
    elif round_count > 1:
        expect_reward = tests['tow_round_reward']
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("inter_round_cancel", [True, False])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 2, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 0, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_reward': 6772 + 13545 * 500 // 2000},
])
def test_cancel_stake_after_transfer_with_validator(core_agent, validator_set, set_candidate, tests,
                                                    inter_round_cancel):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    if inter_round_cancel:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        expect_reward += TOTAL_REWARD // 2 * 3
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + undelegate_amount


@pytest.mark.parametrize("inter_round_claim", [True, False])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386 + 6772 + 13545 * 1500 // 2500},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_reward': 13545 // 4 + 6772 + 13545 // 3 + 6772}
])
def test_claim_after_cancel_stake_transfer_skip_round(core_agent, validator_set, set_candidate, tests,
                                                      inter_round_claim):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    tracker0 = get_tracker(accounts[0])
    if inter_round_claim:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        turn_round(consensuses)
        adjustment_amount = 0
    else:
        turn_round(consensuses, round_count=2)
        adjustment_amount = 1
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + adjustment_amount


def test_cancel_after_skip_round(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_amount // 2)
    undelegate_coin_success(operators[2], accounts[0], delegate_amount + delegate_amount // 2)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    one_round_reward = 6772500
    tow_round_reward = 13545000
    # the reward that is settled when the stake is transferred
    actual_reward = delegate_amount * one_round_reward // Utils.CORE_STAKE_DECIMAL * 2
    # validators who have not performed any operations will receive 2 rounds of rewards
    actual_reward += delegate_amount * tow_round_reward // Utils.CORE_STAKE_DECIMAL
    # transfer rewards
    actual_reward += delegate_amount // 2 * one_round_reward // Utils.CORE_STAKE_DECIMAL
    assert tracker0.delta() == actual_reward


@pytest.mark.parametrize("tests", [
    {'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'undelagate': 0, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'undelagate': 2, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'undelagate': 1, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'undelagate': 2, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'undelagate': 0, 'amount': 1000, 'expect_reward': 13544},
    {'undelagate': 0, 'amount': 1500, 'expect_reward': 13544},
])
def test_cancel_stake_after_adding_stake(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 2, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 0, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 250, 'expect_reward': 13544 + 13545 * 750 // 2000},
    {'transfer': 500, 'undelagate': 2, 'amount': 750, 'expect_reward': 13544 + 13545 * 250 // 2000},
    {'transfer': 500, 'undelagate': 1, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_reward': 6772 + 13545 * 500 // 2000},
    {'transfer': 500, 'undelagate': 0, 'amount': 1500, 'expect_reward': 13544},
])
def test_cancel_stake_after_adding_transfer(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    delegate_coin_success(operators[0], accounts[0], delegate_amount)
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 2, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 2, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 0, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 1000, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 1000, 'undelagate': 1, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 1000, 'undelagate': 2, 'amount': 1000, 'expect_reward': 13544}
])
def test_cancel_stake_after_repeat_transfer(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[0], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[1], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward


@pytest.mark.parametrize("add", [True, False, None])
@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 0, 'amount': 1000, 'expect_reward': 13544},
    {'transfer': 500, 'undelagate': 0, 'amount': 1500, 'expect_reward': 13544 - 3386},
    {'transfer': 500, 'undelagate': 0, 'amount': 2000, 'expect_reward': 13544 - 3386},
    {'transfer': 500, 'undelagate': 1, 'amount': 500, 'expect_reward': 13544 + 3386},
    {'transfer': 500, 'undelagate': 2, 'amount': 1500, 'expect_reward': 13544 - 3386},
])
def test_cancel_stake_after_multiple_additional_transfers(core_agent, validator_set, set_candidate, tests, add):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    if add:
        delegate_coin_success(operators[0], accounts[0], delegate_amount)
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    if add is None:
        delegate_coin_success(operators[0], accounts[0], delegate_amount)
    transfer_coin_success(operators[1], operators[0], accounts[0], transfer_amount)
    if add is False:
        delegate_coin_success(operators[0], accounts[0], delegate_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward
    turn_round(consensuses)


@pytest.mark.parametrize("tests", [
    {'transfer': 500, 'undelagate': 0, 'amount': 1000, 'expect_reward': 27090 - 4515},
    {'transfer': 500, 'undelagate': 1, 'amount': 1500, 'expect_reward': 27090 - (9030 - 9030 / 4)},
    {'transfer': 500, 'undelagate': 2, 'amount': 2000, 'expect_reward': 27090 - 4515 * 2}
])
def test_additional_transfer_after_skip_round(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
    turn_round(consensuses)
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount)
    undelegate_coin_success(operators[agent_index], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + TOTAL_REWARD // 2 * 3


def test_transfer_and_cancel_after_multiple_rounds(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    transfer_amount = delegate_amount // 2
    undelegate_amount = 1000
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    turn_round(consensuses, round_count=3)
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount)
    turn_round(consensuses, round_count=3)
    stake_hub_claim_reward(accounts[0])
    undelegate_coin_success(operators[0], accounts[0], undelegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 2 * 2


def test_cancel_all_after_repeat_transfer(core_agent, validator_set, set_candidate):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    operators, consensuses = set_candidate
    transfer_amount = delegate_amount // 2
    for op in operators:
        delegate_coin_success(op, accounts[0], delegate_amount)
        delegate_coin_success(op, accounts[1], delegate_amount)
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], transfer_amount)
    transfer_coin_success(operators[1], operators[2], accounts[0], transfer_amount)
    transfer_coin_success(operators[2], operators[0], accounts[0], transfer_amount)
    for op in operators:
        undelegate_coin_success(op, accounts[0], delegate_amount)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


@pytest.mark.parametrize("inter_round_cancel", [True, False])
@pytest.mark.parametrize("tests", [
    {'transfer': 1000, 'undelagate': [0, 2], 'amount': [1000, 2000], 'expect_reward': 6772},
    {'transfer': 2000, 'undelagate': [1, 2], 'amount': [500, 1000], 'expect_reward': 6772 + 3386},
    {'transfer': 1500, 'undelagate': [0, 1], 'amount': [500, 1000], 'expect_reward': 6772 + 13545 * 1500 // 4000}
])
def test_cancel_stake_from_multiple_validators(core_agent, validator_set, set_candidate, tests,
                                               inter_round_cancel):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        if index == 0:
            delegate_value = delegate_amount * 2
        delegate_coin_success(op, accounts[0], delegate_value)
        delegate_coin_success(op, accounts[1], delegate_value)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    if inter_round_cancel:
        turn_round(consensuses)
        stake_hub_claim_reward(accounts[0])
        expect_reward += TOTAL_REWARD // 2 * 3
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    for index, a in enumerate(agent_index):
        undelegate_coin_success(operators[a], accounts[0], undelegate_amount[index])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + sum(undelegate_amount)


@pytest.mark.parametrize("tests", [
    {'transfer': 4000, 'undelagate': [1, 2], 'amount': [2000, 2000], 'expect_reward': 13545 // 6},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1500, 1000], 'expect_reward': 13545 * 2500 // 6000},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [2000, 1500], 'expect_reward': 13545 * 1500 // 6000},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1000, 1000], 'expect_reward': 6772},
    {'transfer': 2500, 'undelagate': [1, 2], 'amount': [1000, 500], 'expect_reward': 6772 + 3386},
    {'transfer': 3000, 'undelagate': [0, 2], 'amount': [1000, 2000], 'expect_reward': 13545 // 6 + 6772},
    {'transfer': 2000, 'undelagate': [0, 2], 'amount': [500, 500], 'expect_reward': 13545 * 2500 // 6000 + 6772 + 3386},
    {'transfer': 2000, 'undelagate': [0, 1], 'amount': [2000, 2000], 'expect_reward': 6772},
    {'transfer': 3000, 'undelagate': [0, 1, 2], 'amount': [1000, 2000, 2000], 'expect_reward': 0},
])
def test_cancel_stake_from_validators_after_multiple_additions(core_agent, validator_set, set_candidate, tests):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_amount = tests['amount']
    transfer_amount = tests['transfer']
    expect_reward = tests['expect_reward']
    agent_index = tests['undelagate']
    operators, consensuses = set_candidate
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        if index == 0:
            delegate_value = delegate_amount * 3
        delegate_coin_success(op, accounts[0], delegate_value)
        delegate_coin_success(op, accounts[1], delegate_value)
    turn_round()
    for index, op in enumerate(operators):
        delegate_value = delegate_amount
        delegate_coin_success(op, accounts[0], delegate_value)
        delegate_coin_success(op, accounts[1], delegate_value)
    tracker0 = get_tracker(accounts[0])
    transfer_coin_success(operators[0], operators[2], accounts[0], transfer_amount)
    for index, a in enumerate(agent_index):
        undelegate_coin_success(operators[a], accounts[0], undelegate_amount[index])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == expect_reward + sum(undelegate_amount)


def test_candidate_data_cleared_without_pop(core_agent):
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = delegate_value
    core_agent.delegateCoin(operators[0], {"value": delegate_value})
    turn_round()
    transfer_coin_success(operators[0], operators[2], accounts[0], delegate_value)
    core_agent.undelegateCoin(operators[2], undelegate_value)
    delegator_info = core_agent.getDelegator(operators[0], accounts[0])
    assert delegator_info['transferredAmount'] == 0
    turn_round(consensuses, round_count=2)
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert len(candidate_list) == 1
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    candidate_list = core_agent.getCandidateListByDelegator(accounts[0])
    assert len(candidate_list) == 0


def test_deduct_rewards_from_last_staked_validator(core_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = delegate_value // 2
    core_agent.delegateCoin(operators[1], {"value": delegate_value})
    core_agent.delegateCoin(operators[1], {"value": delegate_value, 'from': accounts[1]})
    core_agent.delegateCoin(operators[2], {"value": delegate_value})
    turn_round()
    transfer_coin_success(operators[2], operators[0], accounts[0], delegate_value)
    transfer_coin_success(operators[1], operators[0], accounts[0], delegate_value)
    core_agent.undelegateCoin(operators[0], undelegate_value)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD // 2 * 2


@pytest.mark.parametrize("tests", [
    {'amount': 1000, 'expect_reward': 13545},
    {'amount': 1500, 'expect_reward': 13545 // 2},
    {'amount': 2000, 'expect_reward': 0},
])
def test_transfer_all_after_transfer_and_claim_reward(core_agent, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['amount']
    core_agent.delegateCoin(operators[0], {"value": delegate_value})
    core_agent.delegateCoin(operators[1], {"value": delegate_value})
    turn_round()
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value)
    transfer_coin_success(operators[1], operators[2], accounts[0], delegate_value * 2)
    core_agent.undelegateCoin(operators[2], undelegate_value)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests['expect_reward']


@pytest.mark.parametrize("tests", [
    {'slash_agent': 0, 'slash_type': 'minor', 'amount': 500, 'expect_reward': 3386},
    {'slash_agent': 1, 'slash_type': 'minor', 'amount': 500, 'expect_reward': 3386},
    {'slash_agent': 0, 'slash_type': 'minor', 'amount': 1000, 'expect_reward': 0},
    {'slash_agent': 1, 'slash_type': 'minor', 'amount': 1000, 'expect_reward': 0},
    {'slash_agent': 0, 'slash_type': 'felony', 'amount': 500, 'expect_reward': 0},
    {'slash_agent': 1, 'slash_type': 'felony', 'amount': 500, 'expect_reward': 3386},
    {'slash_agent': 0, 'slash_type': 'felony', 'amount': 1000, 'expect_reward': 0},
    {'slash_agent': 1, 'slash_type': 'felony', 'amount': 1000, 'expect_reward': 0},
])
def test_additional_transfer_with_slash_validator(core_agent, slash_indicator, tests):
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    slash_type = tests['slash_type']
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['amount']
    delegate_coin_success(operators[0], accounts[0], delegate_value)
    delegate_coin_success(operators[0], accounts[1], delegate_value)
    turn_round()
    tx = None
    delegate_coin_success(operators[0], accounts[0], delegate_value)
    delegate_coin_success(operators[1], accounts[0], delegate_value)
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value * 2)
    if slash_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[tests['slash_agent']])
    assert event_name in tx.events
    core_agent.undelegateCoin(operators[1], undelegate_value)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests['expect_reward']


@pytest.mark.parametrize("tests", [
    {'validator_state': 'refuseDelegate', 'amount': 500, 'expect_reward': 3386},
    {'validator_state': 'refuseDelegate', 'amount': 1000, 'expect_reward': 0},
])
def test_deduct_rewards_from_refuse_delegate_validators(core_agent, candidate_hub, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['amount']
    delegate_coin_success(operators[0], accounts[0], delegate_value)
    delegate_coin_success(operators[0], accounts[1], delegate_value)
    turn_round()
    core_agent.delegateCoin(operators[0], {"value": delegate_value})
    transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value * 2)
    candidate_hub.refuseDelegate({'from': operators[1]})
    core_agent.undelegateCoin(operators[1], undelegate_value)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests['expect_reward']


@pytest.mark.parametrize("tests", [
    {'validator_state': 'candidate', 'amount': 500, 'expect_reward': 6772},
    {'validator_state': 'unregister', 'amount': 500, 'expect_reward': 6772},
    {'validator_state': 'candidate', 'amount': 1000, 'expect_reward': 0},
    {'validator_state': 'unregister', 'amount': 1000, 'expect_reward': 0},
    {'validator_state': 'unregister', 'amount': 2000, 'expect_reward': 0},
])
def test_deduct_rewards_from_different_state_validators(core_agent, candidate_hub, validator_set, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_value = MIN_INIT_DELEGATE_VALUE * 10
    undelegate_value = tests['amount']
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[1]})
    delegate_coin_success(operators[0], accounts[0], delegate_value)
    turn_round()
    validatos = validator_set.getValidators()
    candidate_hub.acceptDelegate({'from': operators[1]})
    assert consensuses[1] not in validatos
    if tests['validator_state'] == 'candidate':
        delegate_coin_success(operators[1], accounts[0], delegate_value)
        transfer_coin_success(operators[0], operators[2], accounts[0], delegate_value)
        undelegate_coin_success(operators[1], accounts[0], undelegate_value)
    elif tests['validator_state'] == 'unregister':
        delegate_coin_success(operators[1], accounts[0], delegate_value)
        transfer_coin_success(operators[0], operators[1], accounts[0], delegate_value)
        candidate_hub.unregister({'from': operators[1]})
        undelegate_coin_success(operators[1], accounts[0], undelegate_value)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == tests['expect_reward']
