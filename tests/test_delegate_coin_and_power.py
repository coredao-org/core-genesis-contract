import pytest
from web3 import Web3
from brownie import accounts
from .common import turn_round, register_candidate, stake_hub_claim_reward
from .utils import get_tracker
from .calc_reward import parse_delegation, set_delegate

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
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
def set_block_reward(validator_set, stake_hub):
    global BLOCK_REWARD
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * (100 - block_reward_incentive_percent) // 100


@pytest.fixture()
def set_candidate():
    operator = accounts[1]
    consensus = operator
    register_candidate(consensus=consensus, operator=operator)
    return consensus, operator


def test_distribute_power_reward_during_turn_round(core_agent, hash_power_agent, stake_hub, btc_light_client,
                                                   candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    operators = accounts[3:5]
    consensuses = []

    for operator in operators:
        consensuses.append(register_candidate(operator=operator))

    clients = accounts[:3]
    core_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE, "from": clients[0]})
    core_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE * 4, "from": clients[1]})
    core_agent.delegateCoin(operators[1], {"value": MIN_INIT_DELEGATE_VALUE * 9, "from": clients[2]})
    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operators[0], [clients[0]] * 2 + [clients[1]])
    btc_light_client.setMiners(round_time_tag, operators[1], [clients[2]] * 2)
    turn_round()
    tracker0 = get_tracker(clients[0])
    tracker1 = get_tracker(clients[1])
    tracker2 = get_tracker(clients[2])
    turn_round(consensuses, tx_fee=TX_FEE)
    rewards, _, account_rewards, collateral_reward = parse_delegation(
        [{
            "address": operators[0],
            "active": True,
            "power": [set_delegate(clients[0], 2), set_delegate(clients[1], 1)],
            "coin": [set_delegate(clients[0], 100), set_delegate(clients[1], 400)],
            "btc": []
        }, {
            "address": operators[1],
            "active": True,
            "power": [set_delegate(clients[2], 2)],
            "coin": [set_delegate(clients[2], 900)],
            "btc": []
        }], BLOCK_REWARD // 2)
    stake_hub_claim_reward(clients[:3])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2one_agent_twice_in_different_rounds(candidate_hub, core_agent, btc_light_client, stake_hub,
                                                      set_candidate, hash_power_agent,
                                                      internal):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    consensus, operator = set_candidate
    turn_round()

    core_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round(round_count=internal)

    btc_light_client.setMiners(candidate_hub.roundTag() - 6, operator, [accounts[0]] * 100)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operator,
        "active": True,
        "power": [set_delegate(accounts[0], 100)],
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "btc": []
    }], BLOCK_REWARD // 2)
    turn_round()

    tracker = get_tracker(accounts[0])
    turn_round([consensus], tx_fee=TX_FEE)
    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]


def test_scenario1(candidate_hub, core_agent, btc_light_client, stake_hub):
    """
    round x delegate coin to N1, delegate power to N2, round x+2 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    consensus1 = register_candidate(operator=accounts[1])
    consensus2 = register_candidate(operator=accounts[2])
    turn_round()

    round_tag = candidate_hub.roundTag() - 7

    btc_light_client.setMiners(round_tag + 1, accounts[2], [accounts[0]])
    btc_light_client.setMiners(round_tag + 2, accounts[2], [accounts[0]])
    core_agent.delegateCoin(accounts[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})

    _, _, account_rewards, _ = parse_delegation([{
        "address": accounts[1],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": [],
        "btc": []

    }, {
        "address": accounts[2],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }], BLOCK_REWARD // 2)
    turn_round()
    tracker = get_tracker(accounts[0])
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)
    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]


def test_scenario2(candidate_hub, core_agent, btc_light_client, stake_hub):
    """
    round x delegate coin to N1, round x+1 delegate power to N2, round x+3 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    consensus1 = register_candidate(operator=accounts[1])
    consensus2 = register_candidate(operator=accounts[2])
    turn_round()

    core_agent.delegateCoin(accounts[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, accounts[2], [accounts[0]])
    btc_light_client.setMiners(round_tag + 2, accounts[2], [accounts[0]])
    turn_round()

    _, _, account_rewards, _ = parse_delegation([{
        "address": accounts[1],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": [],
        "btc": []

    }, {
        "address": accounts[2],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }], BLOCK_REWARD // 2)
    tracker = get_tracker(accounts[0])
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)
    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]


def test_scenario3(candidate_hub, core_agent, stake_hub, btc_light_client, hash_power_agent):
    """
    round x delegate coin to N1,
    round x+1 delegate power to N2,
    round x+2 delegate coin to N3,
    round x+4 transfer coin from N1 to N3
    round x+6 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    operators = accounts[1:4]
    consensuses = []
    for operator in operators:
        consensuses.append(register_candidate(operator=operator))
    turn_round()

    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    round_tag = candidate_hub.roundTag() - 7

    btc_light_client.setMiners(round_tag, operators[1], [accounts[0]])
    for i in range(0, 5):
        btc_light_client.setMiners(round_tag + i, operators[1], [accounts[0]])

    turn_round()

    core_agent.delegateCoin(operators[2], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": [],
        "btc": []

    }, {
        "address": operators[1],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }, {
        "address": operators[2],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": [],
        "btc": []

    }], BLOCK_REWARD // 2)

    tracker = get_tracker(accounts[0])
    turn_round(consensuses, tx_fee=TX_FEE)
    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]
    core_agent.transferCoin(operators[0], operators[2], MIN_INIT_DELEGATE_VALUE)
    turn_round(consensuses, tx_fee=TX_FEE, round_count=1)
    _, _, account_rewards, _ = parse_delegation([
        {
            "address": operators[0],
            "active": True,
            "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
            "power": [],
            "btc": []

        },
        {
            "address": operators[1],
            "active": True,
            "coin": [],
            "power": [set_delegate(accounts[0], 1)],
            "btc": []

        }, {
            "address": operators[2],
            "active": True,
            "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
            "power": [],
            "btc": []

        }], BLOCK_REWARD // 2)

    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]


def test_scenario4(candidate_hub, core_agent, validator_set, btc_light_client, stake_hub):
    """
    round
        x P1 delegate coin to N1, power to N2
        x P2 delegate power to N1, coin to N2
      x+1 N1 refuse delegate
      x+2
      x+3 P1 claim
    """
    round_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_tag)

    operators = accounts[2:4]
    consensuses = []
    for operator in operators:
        consensuses.append(register_candidate(operator=operator))
    turn_round()

    round_tag = candidate_hub.roundTag() - 7
    for i in range(0, 5):
        btc_light_client.setMiners(round_tag + i, operators[1], [accounts[0]])
        btc_light_client.setMiners(round_tag + i, operators[0], [accounts[1]] * 2)

    core_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE * 4, 'from': accounts[0]})
    core_agent.delegateCoin(operators[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})

    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE * 4)],
        "power": [set_delegate(accounts[1], 2)],
        "btc": []

    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }], BLOCK_REWARD // 2)

    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})

    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses, tx_fee=TX_FEE)
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]

    turn_round(consensuses, tx_fee=TX_FEE)
    assert validator_set.getValidators() == [consensuses[1]]

    delegator_coin_reward, delegator_power_reward, account_rewards, _ = parse_delegation([{
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }], BLOCK_REWARD // 2)

    stake_hub_claim_reward(accounts[:2])

    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]


def test_scenario5(candidate_hub, core_agent, validator_set, btc_light_client, stake_hub):
    """
    round X: N has power, delegate to A
    round X+1: A didn't become validator
    round X+2: N has no power, A become validator
    expect N has no reward
    """
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    consensus1 = register_candidate(operator=accounts[1])
    turn_round()

    operator = accounts[2]
    consensus2 = register_candidate(operator=operator)

    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, operator, [accounts[0]])

    candidate_hub.refuseDelegate({'from': operator})
    turn_round()

    assert validator_set.getValidators() == [consensus1]

    tracker = get_tracker(accounts[0])

    turn_round([consensus1], tx_fee=TX_FEE)
    candidate_hub.acceptDelegate({'from': operator})
    turn_round([consensus1], tx_fee=TX_FEE)

    assert len(validator_set.getValidators()) == 2
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)

    stake_hub.claimReward()
    assert tracker.delta() == 0


def test_scenario6(candidate_hub, core_agent, validator_set, stake_hub):
    agent0xD53 = accounts.at('0xD53434e5DcD1127dB61aeD63d19bB9d044F59BCE', force=True)
    accounts[0].transfer(agent0xD53, ONE_ETHER)
    agent0x97b = accounts.at('0x97bBEe4F4CDf2709945f5869BE5b58BF349ead63', force=True)
    accounts[0].transfer(agent0x97b, ONE_ETHER)
    agent0xDe7 = accounts.at('0xDe79C463efe48e909d2b9768559f77Dd0cf87935', force=True)
    accounts[0].transfer(agent0xDe7, ONE_ETHER)
    agent0x5f8 = accounts.at('0x5f807646ef039E4323218Fe88ac66ceae138B6ae', force=True)
    accounts[0].transfer(agent0x5f8, ONE_ETHER)
    agent0xB4f = accounts.at('0xB4fc06682d326350F7fB74DdA00EfdBB2F702CbD', force=True)
    accounts[0].transfer(agent0xB4f, ONE_ETHER)
    consensus_list = [
        register_candidate(operator=agent0xD53),
        register_candidate(operator=agent0x97b),
        register_candidate(operator=agent0xDe7),
        register_candidate(operator=agent0x5f8),
        register_candidate(operator=agent0xB4f)
    ]
    turn_round()

    delegator0x910 = accounts.at('0x910cFFAB256EAF41890a9480bcc382d16A538D3C', force=True)
    accounts[0].transfer(delegator0x910, ONE_ETHER)
    core_agent.delegateCoin(agent0xDe7, {'from': delegator0x910, 'value': MIN_INIT_DELEGATE_VALUE})
    delegator0xa7b = accounts.at('0xa7bfE86f05E93201811B428244B09cF16D7467b7', force=True)
    accounts[0].transfer(delegator0xa7b, ONE_ETHER)
    core_agent.delegateCoin(agent0x5f8, {'from': delegator0xa7b, 'value': MIN_INIT_DELEGATE_VALUE})
    turn_round(consensus_list, tx_fee=TX_FEE)

    delegator0xB66 = accounts.at('0xB66bdd5C5287b6E23D76510afc73208238E30Ad3', force=True)
    accounts[0].transfer(delegator0xB66, ONE_ETHER)
    tracker = get_tracker(delegator0xB66)
    turn_round(consensus_list, tx_fee=TX_FEE)

    core_agent.delegateCoin(agent0xD53, {'from': delegator0xB66, 'value': MIN_INIT_DELEGATE_VALUE})
    core_agent.transferCoin(agent0xDe7, agent0xB4f, MIN_INIT_DELEGATE_VALUE, {'from': delegator0x910})
    turn_round(consensus_list, tx_fee=TX_FEE)

    core_agent.undelegateCoin(agent0xB4f, MIN_INIT_DELEGATE_VALUE, {'from': delegator0x910})
    delegator0xbe6 = accounts.at('0xbe6dcEE3dE0d1Cf50B660d9e965BFeefa7Ab081f', force=True)
    accounts[0].transfer(delegator0xbe6, ONE_ETHER)
    core_agent.delegateCoin(agent0x97b, {'from': delegator0xbe6, 'value': MIN_INIT_DELEGATE_VALUE})
    turn_round(consensus_list, tx_fee=TX_FEE)

    turn_round(consensus_list, tx_fee=TX_FEE)

    turn_round(consensus_list, tx_fee=TX_FEE)

    core_agent.transferCoin(agent0x97b, agent0xD53, MIN_INIT_DELEGATE_VALUE, {'from': delegator0xbe6})
    delegator0xc40 = accounts.at('0xc40e52501d9969B6788C173C1cA6b23DE6f3392d', force=True)
    accounts[0].transfer(delegator0xc40, ONE_ETHER)
    core_agent.delegateCoin(agent0x97b, {'from': delegator0xc40, 'value': MIN_INIT_DELEGATE_VALUE})

    stake_hub.claimReward({'from': delegator0xB66})
    assert tracker.delta() == BLOCK_REWARD // 2 * 3 - MIN_INIT_DELEGATE_VALUE


def test_scenario7(core_agent, btc_light_client, candidate_hub, set_candidate, stake_hub):
    """
    round X: N has power, delegate to A
    round X+1: N has not power
    round X+1: N claim power reward
    """
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    btc_light_client.setMiners(candidate_hub.roundTag() - 6, accounts[1], [accounts[0]])
    consensus, operator = set_candidate
    turn_round()
    turn_round([consensus], tx_fee=TX_FEE)
    delegator_coin_reward, delegator_power_reward, account_rewards, _ = parse_delegation([{
        "address": accounts[1],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)],
        "btc": []

    }], BLOCK_REWARD // 2)
    tracker = get_tracker(accounts[0])
    stake_hub.claimReward()
    assert tracker.delta() == account_rewards[accounts[0]]
