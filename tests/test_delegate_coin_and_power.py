import secrets

import pytest
from web3 import Web3
from brownie import accounts
from .common import turn_round, register_candidate, set_miner_power
from .utils import get_tracker, get_public_key_by_idx, public_key2PKHash
from .calc_reward import parse_delegation, set_delegate


MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0

ONE_ETHER = Web3.toWei(1, 'ether')
TX_FEE = int(1e4)


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
    BLOCK_REWARD = total_block_reward * (100 - block_reward_incentive_percent) // 100


@pytest.fixture()
def set_candidate():
    operator = accounts[1]
    consensus = operator
    register_candidate(consensus=consensus, operator=operator)
    return consensus, operator


def test_distribute_power_reward_during_turn_round(pledge_agent, btc_light_client, candidate_hub):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    operators = accounts[3:5]
    consensuses = []

    for operator in operators:
        consensuses.append(register_candidate(operator=operator))

    clients = accounts[:3]
    pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE, "from": clients[0]})
    pledge_agent.delegateCoin(operators[0], {"value": MIN_INIT_DELEGATE_VALUE * 4, "from": clients[1]})
    pledge_agent.delegateCoin(operators[1], {"value": MIN_INIT_DELEGATE_VALUE * 9, "from": clients[2]})

    # prepare btc block
    clients_pub_keys = [get_public_key_by_idx(idx) for idx in range(3)]
    clients_pkHash_list = [public_key2PKHash(public_key) for public_key in clients_pub_keys]
    clients_btc_block_hash = ['0x' + secrets.token_hex(32) for _ in clients]
    for idx in range(3):
        btc_light_client.setBlock(clients_btc_block_hash[idx], clients_pkHash_list[idx])

    round_time_tag = candidate_hub.roundTag() - 6
    btc_light_client.setMiners(round_time_tag, clients_pkHash_list)
    btc_light_client.setMinerCount(round_time_tag, clients_pkHash_list[0], 2)
    btc_light_client.setMinerCount(round_time_tag, clients_pkHash_list[1], 1)
    btc_light_client.setMinerCount(round_time_tag, clients_pkHash_list[2], 2)

    # delegate power
    pledge_agent.delegateHashPower(operators[0], clients_pub_keys[0], clients_btc_block_hash[0], {"from": clients[0]})
    pledge_agent.delegateHashPower(operators[0], clients_pub_keys[1], clients_btc_block_hash[1], {"from": clients[1]})
    pledge_agent.delegateHashPower(operators[1], clients_pub_keys[2], clients_btc_block_hash[2], {"from": clients[2]})

    turn_round()
    """
    N1:
        btc:
            x1 = 2
            x2 = 1
        coin:
            x1 = 100
            x2 = 400
    N2:
        btc: 2
        coin: 900
        
    total_btc_count = 6
    total_staked_coin = 1401
    r = 200
    V1 = r / 100 * 3 * 15 + 5 * 6 = 120
    V2 = r / 100 * 2 * 15 + 5 * 6 = 114
    """
    agent_score, delegate_reward = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(clients[0], 2), set_delegate(clients[1], 1)],
        "coin": [set_delegate(clients[0], 100), set_delegate(clients[1], 400)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [set_delegate(clients[2], 2)],
        "coin": [set_delegate(clients[2], 900)]
    }], BLOCK_REWARD // 2)

    tracker1 = get_tracker(clients[0])
    tracker2 = get_tracker(clients[1])

    turn_round(consensuses, tx_fee=TX_FEE)

    pledge_agent.claimReward(clients[0], operators)
    pledge_agent.claimReward(clients[1], operators)

    assert tracker1.delta() == delegate_reward[clients[0]]
    assert tracker2.delta() == delegate_reward[clients[1]]


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_delegate2one_agent_twice_in_different_rounds(candidate_hub, pledge_agent, set_candidate, internal):
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    consensus, operator = set_candidate
    turn_round()

    pledge_agent.delegateCoin(operator, {"value": MIN_INIT_DELEGATE_VALUE})
    turn_round(round_count=internal)

    public_key, btc_block_hash = set_miner_power(candidate_hub.roundTag() - 6, [0], [100])
    pledge_agent.delegateHashPower(operator, public_key, btc_block_hash)

    turn_round()

    tracker = get_tracker(accounts[0])
    turn_round([consensus], tx_fee=TX_FEE)
    pledge_agent.claimReward(accounts[0], [operator])
    assert tracker.delta() == BLOCK_REWARD / 2


def test_scenario1(candidate_hub, pledge_agent):
    """
    round x delegate coin to N1, delegate power to N2, round x+2 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    consensus1 = register_candidate(operator=accounts[1])
    consensus2 = register_candidate(operator=accounts[2])
    turn_round()

    round_tag = candidate_hub.roundTag() - 7
    public_key, btc_block_hash = set_miner_power(round_tag, [0], [1])
    set_miner_power(round_tag + 1, [0], [1])
    set_miner_power(round_tag + 2, [0], [1])

    pledge_agent.delegateCoin(accounts[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    pledge_agent.delegateHashPower(accounts[2], public_key, btc_block_hash, {'from': accounts[0]})

    _, delegator_reward = parse_delegation([{
        "address": accounts[1],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": []
    }, {
        "address": accounts[2],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)]
    }], BLOCK_REWARD // 2)
    coin_reward = BLOCK_REWARD // 2
    power_reward = delegator_reward[accounts[0]] - coin_reward

    turn_round()

    tracker = get_tracker(accounts[0])
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)
    assert tracker.delta() == power_reward
    pledge_agent.claimReward(accounts[0], accounts[1:3])
    assert tracker.delta() == coin_reward


def test_scenario2(candidate_hub, pledge_agent):
    """
    round x delegate coin to N1, round x+1 delegate power to N2, round x+3 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    consensus1 = register_candidate(operator=accounts[1])
    consensus2 = register_candidate(operator=accounts[2])
    turn_round()

    pledge_agent.delegateCoin(accounts[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    round_tag = candidate_hub.roundTag() - 7
    public_key, btc_block_hash = set_miner_power(round_tag, [0], [1])
    set_miner_power(round_tag + 1, [0], [1])
    set_miner_power(round_tag + 2, [0], [1])
    pledge_agent.delegateHashPower(accounts[2], public_key, btc_block_hash, {'from': accounts[0]})
    turn_round()

    _, delegator_reward = parse_delegation([{
        "address": accounts[1],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": []
    }, {
        "address": accounts[2],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)]
    }], BLOCK_REWARD // 2)
    coin_reward = BLOCK_REWARD // 2
    power_reward = delegator_reward[accounts[0]] - coin_reward

    tracker = get_tracker(accounts[0])
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)
    assert tracker.delta() == power_reward
    pledge_agent.claimReward(accounts[0], accounts[1:3])
    assert tracker.delta() == coin_reward


def test_scenario3(candidate_hub, pledge_agent):
    """
    round x delegate coin to N1,
    round x+1 delegate power to N2,
    round x+2 delegate coin to N3,
    round x+4 transfer from N1 to N3
    round x+6 claim reward
    """
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(7)

    operators = accounts[1:4]
    consensuses = []
    for operator in operators:
        consensuses.append(register_candidate(operator=operator))
    turn_round()

    pledge_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    round_tag = candidate_hub.roundTag() - 7
    public_key, btc_block_hash = set_miner_power(round_tag, [0], [1])
    for i in range(1, 5):
        set_miner_power(round_tag + i, [0], [1])
    pledge_agent.delegateHashPower(operators[1], public_key, btc_block_hash, {'from': accounts[0]})
    turn_round()

    pledge_agent.delegateCoin(operators[2], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    _, delegator_reward = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": []
    }, {
        "address": operators[1],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)]
    }, {
        "address": operators[2],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE)],
        "power": []
    }], BLOCK_REWARD // 2)
    power_reward = delegator_reward[accounts[0]] - BLOCK_REWARD // 2 * 2

    tracker = get_tracker(accounts[0])
    turn_round(consensuses, tx_fee=TX_FEE)
    assert tracker.delta() == power_reward
    pledge_agent.transferCoin(operators[0], operators[2])
    assert tracker.delta() == BLOCK_REWARD // 2 * 2
    turn_round(consensuses, tx_fee=TX_FEE, round_count=2)

    _, delegator_reward = parse_delegation([{
        "address": operators[1],
        "active": True,
        "coin": [],
        "power": [set_delegate(accounts[0], 1)]
    }, {
        "address": operators[2],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE * 2)],
        "power": []
    }], BLOCK_REWARD // 2)
    power_reward = delegator_reward[accounts[0]] - BLOCK_REWARD // 2

    assert tracker.delta() == power_reward * 2

    pledge_agent.claimReward(accounts[0], operators)
    assert tracker.delta() == BLOCK_REWARD // 2 * 2


def test_scenario4(candidate_hub, pledge_agent):
    """
    round x delegate coin to N1,
    round x+1 delegate power to N2,
    round x+2 delegate coin to N3,
    round x+4 transfer power to N3
    round x+6 claim reward
    """
    round_time_tag = 7
    candidate_hub.setControlRoundTimeTag(True)
    candidate_hub.setRoundTag(round_time_tag)

    operators = accounts[1:4]
    consensuses = []
    for operator in operators:
        consensuses.append(register_candidate(operator=operator))
    turn_round()

    pledge_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    round_time_tag = candidate_hub.roundTag() - 6
    public_key, btc_block_hash = set_miner_power(round_time_tag, [0], [100])
    for i in range(1, 5):
        set_miner_power(round_time_tag + i, [0], [100])
    pledge_agent.delegateHashPower(operators[1], public_key, btc_block_hash, {'from': accounts[0]})
    turn_round()
    pledge_agent.delegateCoin(operators[2], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[0]})
    turn_round()

    tracker = get_tracker(accounts[0])
    turn_round(consensuses, tx_fee=TX_FEE)
    assert tracker.delta() == BLOCK_REWARD // 2
    pledge_agent.transferPower(operators[2], {'from': accounts[0]})
    assert tracker.delta() == 0
    turn_round(consensuses, tx_fee=TX_FEE)
    assert tracker.delta() == 0
    turn_round(consensuses, tx_fee=TX_FEE)
    assert tracker.delta() == BLOCK_REWARD // 2 * 100 * 2 * 201 // 50300

    pledge_agent.claimReward(accounts[0], operators)
    assert tracker.delta() == BLOCK_REWARD // 2 * 5 + BLOCK_REWARD // 2 * 100 * 101 // 50300


def test_scenario5(candidate_hub, pledge_agent, validator_set):
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
    public_key_list, btc_block_hash_list = set_miner_power(round_tag, [0, 1], [1, 2])
    for i in range(1, 5):
        set_miner_power(round_tag + i, [0, 1], [1, 2])

    pledge_agent.delegateCoin(operators[0], {'value': MIN_INIT_DELEGATE_VALUE * 4, 'from': accounts[0]})
    pledge_agent.delegateHashPower(operators[1], public_key_list[0], btc_block_hash_list[0], {'from': accounts[0]})
    pledge_agent.delegateCoin(operators[1], {'value': MIN_INIT_DELEGATE_VALUE, 'from': accounts[1]})
    pledge_agent.delegateHashPower(operators[0], public_key_list[1], btc_block_hash_list[1], {'from': accounts[1]})

    _, delegator_reward = parse_delegation([{
        "address": operators[0],
        "active": True,
        "coin": [set_delegate(accounts[0], MIN_INIT_DELEGATE_VALUE * 4)],
        "power": [set_delegate(accounts[1], 2)]
    }, {
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
        "power": [set_delegate(accounts[0], 1)]
    }], BLOCK_REWARD // 2)

    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})

    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    turn_round(consensuses, tx_fee=TX_FEE)

    pledge_agent.claimReward(accounts[0], operators)
    pledge_agent.claimReward(accounts[1], operators)

    assert tracker0.delta() == delegator_reward[accounts[0]]
    assert tracker1.delta() == delegator_reward[accounts[1]]

    turn_round(consensuses, tx_fee=TX_FEE)
    assert validator_set.getValidators() == [consensuses[1]]

    agent_score, delegator_reward = parse_delegation([{
        "address": operators[1],
        "active": True,
        "coin": [set_delegate(accounts[1], MIN_INIT_DELEGATE_VALUE)],
        "power": [set_delegate(accounts[0], 1)]
    }], BLOCK_REWARD // 2)

    pledge_agent.claimReward(accounts[1], operators)

    assert tracker1.delta() == delegator_reward[accounts[1]]


def test_scenario6(candidate_hub, pledge_agent, validator_set):
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
    public_key, btc_block_hash = set_miner_power(round_time_tag, [0], [1])
    pledge_agent.delegateHashPower(operator, public_key, btc_block_hash, {'from': accounts[0]})
    candidate_hub.refuseDelegate({'from': operator})
    turn_round()

    assert validator_set.getValidators() == [consensus1]

    tracker = get_tracker(accounts[0])

    turn_round([consensus1], tx_fee=TX_FEE)
    candidate_hub.acceptDelegate({'from': operator})
    turn_round([consensus1], tx_fee=TX_FEE)

    assert len(validator_set.getValidators()) == 2
    turn_round([consensus1, consensus2], tx_fee=TX_FEE)

    assert tracker.delta() == 0


def test_scenario7(candidate_hub, pledge_agent, validator_set):
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
    pledge_agent.delegateCoin(agent0xDe7, {'from': delegator0x910, 'value': MIN_INIT_DELEGATE_VALUE})
    delegator0xa7b = accounts.at('0xa7bfE86f05E93201811B428244B09cF16D7467b7', force=True)
    accounts[0].transfer(delegator0xa7b, ONE_ETHER)
    pledge_agent.delegateCoin(agent0x5f8, {'from': delegator0xa7b, 'value': MIN_INIT_DELEGATE_VALUE})
    turn_round(consensus_list, tx_fee=TX_FEE)

    delegator0xB66 = accounts.at('0xB66bdd5C5287b6E23D76510afc73208238E30Ad3', force=True)
    accounts[0].transfer(delegator0xB66, ONE_ETHER)
    tracker = get_tracker(delegator0xB66)
    pledge_agent.delegateCoin(agent0xD53, {'from': delegator0xB66, 'value': MIN_INIT_DELEGATE_VALUE})
    pledge_agent.transferCoin(agent0xD53, agent0xDe7, {'from': delegator0xB66})
    pledge_agent.transferCoin(agent0xDe7, agent0xB4f, {'from': delegator0x910})
    turn_round(consensus_list, tx_fee=TX_FEE)

    pledge_agent.undelegateCoin(agent0xB4f, {'from': delegator0x910})
    delegator0xbe6 = accounts.at('0xbe6dcEE3dE0d1Cf50B660d9e965BFeefa7Ab081f', force=True)
    accounts[0].transfer(delegator0xbe6, ONE_ETHER)
    pledge_agent.delegateCoin(agent0x97b, {'from': delegator0xbe6, 'value': MIN_INIT_DELEGATE_VALUE})
    turn_round(consensus_list, tx_fee=TX_FEE)

    turn_round(consensus_list, tx_fee=TX_FEE)

    turn_round(consensus_list, tx_fee=TX_FEE)

    pledge_agent.transferCoin(agent0x97b, agent0xD53, {'from': delegator0xbe6})
    pledge_agent.transferCoin(agent0xD53, agent0xDe7, {'from': delegator0xbe6})
    delegator0xc40 = accounts.at('0xc40e52501d9969B6788C173C1cA6b23DE6f3392d', force=True)
    accounts[0].transfer(delegator0xc40, ONE_ETHER)
    pledge_agent.delegateCoin(agent0x97b, {'from': delegator0xc40, 'value': MIN_INIT_DELEGATE_VALUE})

    pledge_agent.claimReward(delegator0xB66, [agent0xDe7])
    assert tracker.delta() == BLOCK_REWARD // 2 * 3 - MIN_INIT_DELEGATE_VALUE
