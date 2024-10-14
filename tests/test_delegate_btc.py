import brownie
import pytest
from web3 import constants
from .calc_reward import set_delegate, parse_delegation
from .common import register_candidate, turn_round, get_current_round, stake_hub_claim_reward
from .delegate import delegate_btc_success, transfer_btc_success, get_btc_script, build_btc_tx, set_last_round_tag
from .utils import *

BLOCK_REWARD = 0
TOTAL_REWARD = 0
BTC_VALUE = 2000
FEE = 0
STAKE_ROUND = 3
# BTC delegation-related
PUBLIC_KEY = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
LOCK_TIME = 1736956800

# class BtcScript
btc_script = get_btc_script()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent):
    global BLOCK_REWARD, FEE
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, TOTAL_REWARD
    FEE = FEE * Utils.CORE_DECIMAL
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    tx_fee = 100
    total_block_reward = block_reward + tx_fee
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    candidate_hub.setControlRoundTimeTag(True)
    btc_light_client.setCheckResult(True, LOCK_TIME)
    TOTAL_REWARD = BLOCK_REWARD // 2
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent


@pytest.fixture(scope="module", autouse=True)
def set_relayer_register(relay_hub):
    for account in accounts[:3]:
        relay_hub.setRelayerRegister(account.address, True)


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_claim_rewards_from_multiple_validators(btc_stake):
    operators, consensuses = [], []
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    set_last_round_tag(STAKE_ROUND)
    sum_reward = 0
    for index, operator in enumerate(operators):
        delegate_btc_success(operator, accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_SCRIPT, accounts[1])
        sum_reward += TOTAL_REWARD
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == sum_reward - FEE * 12


def test_transfer_btc_between_different_validators(btc_stake, core_agent, candidate_hub, set_candidate, btc_lst_stake):
    operators, consensuses = set_candidate
    end_round, _ = set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_SCRIPT)
    turn_round()
    transfer_btc_success(tx_id, operators[1], accounts[0])
    transfer_btc_success(tx_id, operators[2], accounts[0])
    transfer_btc_success(tx_id, operators[0], accounts[0])
    transfer_btc_success(tx_id, operators[1], accounts[0])
    assert __get_delegator_btc_map(accounts[0])[0] == tx_id
    turn_round(consensuses, round_count=2)
    __check_btc_tx_map_info(tx_id, {})
    __check_receipt_map_info(tx_id, {})
    __check_candidate_map_info(operators[0], {})
    __check_candidate_map_info(operators[1], {})
    __check_candidate_map_info(operators[2], {})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD - FEE


def test_duplicate_transfer_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    tx = btc_stake.transfer(tx_id, operators[1])
    assert 'transferredBtc' in tx.events
    tx = btc_stake.transfer(tx_id, operators[2])
    assert 'transferredBtc' in tx.events
    tx = btc_stake.transfer(tx_id, operators[0])
    assert 'transferredBtc' in tx.events
    addr_list = btc_stake.getAgentAddrList(end_round)
    assert len(addr_list) == 3
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses)
    turn_round(consensuses)


def test_claim_btc_staking_rewards_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    expect_event(tx, "claimedReward", {
        "delegator": accounts[0],
        "amount": TOTAL_REWARD - FEE
    })
    assert tracker.delta() == TOTAL_REWARD - FEE


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_claim_multi_round_btc_staking_rewards(btc_stake, set_candidate, internal):
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, relay=accounts[0])
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, relay=accounts[0])
    turn_round()
    turn_round(consensuses, round_count=internal)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    fee = 0
    if internal > 0:
        fee = FEE * 2
    assert tracker.delta() == TOTAL_REWARD * 2 * internal - fee


def test_distribute_rewards_to_multiple_addresses(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == TOTAL_REWARD // 2 + FEE
    assert tracker1.delta() == TOTAL_REWARD // 2 - FEE


def test_claim_rewards_for_multiple_coin_staking(btc_stake, core_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_amount = 50000
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    core_agent.delegateCoin(operators[1], {"value": delegate_amount // 2})
    delegate_btc_success(operators[0], accounts[1], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, relay=accounts[2])
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, relay=accounts[2])
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[1], BTC_VALUE)],
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount // 2)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]] - FEE


def test_unable_to_claim_rewards_after_end_round(btc_stake, set_candidate):
    set_last_round_tag(STAKE_ROUND)
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD * 3 - FEE
    __check_receipt_map_info(tx_id, {
        'candidate': constants.ADDRESS_ZERO,
        'delegator': constants.ADDRESS_ZERO,
        'round': 0,
    })
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_single_validator_multiple_stakes(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_time1 = LOCK_TIME + Utils.ROUND_INTERVAL * 2
    set_last_round_tag(STAKE_ROUND)
    btc_amount0 = 3000
    btc_amount1 = 2500
    delegate_amount = 45000
    delegate_btc_success(operators[0], accounts[0], btc_amount0, LOCK_SCRIPT, LOCK_TIME)
    lock_script1 = __get_stake_lock_script(PUBLIC_KEY, lock_time1)
    delegate_btc_success(operators[0], accounts[0], btc_amount1, lock_script1, lock_time1, script_type='p2wsh')
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    _, _, account_rewards0, round_reward0 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount0 + btc_amount1)],
    }], BLOCK_REWARD // 2)
    turn_round(consensuses, round_count=6)
    _, _, account_rewards1, round_reward1 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount1)],
    }], BLOCK_REWARD // 2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    per_btc_map0 = round_reward0['btc'][operators[0]]
    per_btc_map1 = round_reward1['btc'][operators[0]]
    account_reward0 = (btc_amount0 + btc_amount1) * per_btc_map0 / Utils.BTC_DECIMAL * 3
    account_reward1 = btc_amount1 * per_btc_map1 / Utils.BTC_DECIMAL * 2
    assert tracker0.delta() == account_reward0 + account_reward1


def test_no_rewards_generated_at_end_of_round(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    set_last_round_tag(STAKE_ROUND)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    turn_round(consensuses, round_count=2)
    assert btc_stake.getAgentAddrList(end_round)[0] == operators[0]
    assert len(btc_stake.getAgentAddrList(end_round)) == 1
    # endRound:20103
    # at the end of round 20102, the expired BTC staking will be deducted from the validator upon transitioning to round 20103.
    turn_round(consensuses, round_count=1)
    assert len(btc_stake.getAgentAddrList(end_round)) == 0
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    tx = turn_round(consensuses, round_count=1)
    assert len(tx.events['roundReward']) == 3
    for r in tx.events['roundReward']:
        assert r['amount'] == [0, 0, 0]


def test_multiple_users_staking_to_same_validator(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_time1 = LOCK_TIME + Utils.ROUND_INTERVAL * 2
    set_last_round_tag(STAKE_ROUND)
    btc_amount0 = 3000
    btc_amount1 = 2500
    account0_btc = btc_amount0 + btc_amount1
    delegate_amount = 45000
    delegate_btc_success(operators[0], accounts[1], btc_amount0, LOCK_SCRIPT, LOCK_TIME)
    lock_script1 = __get_stake_lock_script(PUBLIC_KEY, lock_time1)
    delegate_btc_success(operators[0], accounts[0], btc_amount1, lock_script1, lock_time1)
    delegate_btc_success(operators[0], accounts[0], btc_amount0, LOCK_SCRIPT, LOCK_TIME)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    _, _, account_rewards0, round_reward0 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], account0_btc), set_delegate(accounts[1], btc_amount0)],
    }], BLOCK_REWARD // 2)
    _, _, account_rewards1, round_reward2 = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount1)],
    }], BLOCK_REWARD // 2)
    turn_round(consensuses, round_count=5)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    per_btc_reward0 = round_reward0['btc'][operators[0]] * 3
    per_btc_reward1 = round_reward2['btc'][operators[0]] * 2
    reward0 = btc_amount0 * per_btc_reward0 // Utils.BTC_DECIMAL + btc_amount1 * per_btc_reward0 // Utils.BTC_DECIMAL + btc_amount1 * per_btc_reward1 // Utils.BTC_DECIMAL
    reward1 = account_rewards0[accounts[1]] * 3
    assert tracker0.delta() == int(reward0) + FEE
    assert tracker1.delta() == reward1 - FEE


def test_claim_rewards_for_multiple_stakes_to_different_validators(btc_stake, set_candidate):
    delegate_amount = 30000
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    CORE_AGENT.delegateCoin(operators[1], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD)
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_claim_rewards_after_staking_every_other_round(btc_stake, set_candidate):
    delegate_amount = 300000
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    btc_amount = 2500
    delegate_btc_success(operators[0], accounts[0], btc_amount, LOCK_SCRIPT, LOCK_TIME)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount), set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_revert_on_max_fee_exceeded(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    # fee range 1-255
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, fee=256)
    with brownie.reverts("BitcoinHelper: invalid tx"):
        btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT)


def test_claim_rewards_with_fee_deduction_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, relay=accounts[1])
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    assert tracker1.delta() == FEE


@pytest.mark.parametrize("fee", [
    pytest.param(1, id="fee is 1"),
    pytest.param(10, id="fee is 10"),
    pytest.param(50, id="fee is 50"),
    pytest.param(100, id="fee is 100"),
    pytest.param(150, id="fee is 150"),
    pytest.param(254, id="fee is 254"),
    pytest.param(255, id="fee is 255")
])
def test_claim_rewards_with_different_fees_success(btc_stake, set_candidate, fee):
    operators, consensuses = set_candidate
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, fee=fee)
    btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=7)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker1.delta() == 0


def test_success_with_zero_fee(btc_stake, set_candidate):
    fee = 0
    operators, consensuses = set_candidate
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, fee=fee)
    btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    assert tracker1.delta() == 0


def test_multiple_btc_receipts_to_single_address(btc_stake, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    tx_id0 = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[1])
    tx_id1 = delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[2], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id0, operators[2])
    btc_stake.transfer(tx_id1, operators[2])
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, round_reward = parse_delegation([{
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE), set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    reward = BTC_VALUE * round_reward['btc'][operators[2]] * 2 // Utils.BTC_DECIMAL * 2
    assert tracker0.delta() == reward - FEE * 2


def test_multiple_reward_transfers_in_multiple_rounds(btc_stake, set_candidate):
    operators, consensuses = [], []
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    set_last_round_tag(STAKE_ROUND)
    tx_id_list = []
    for index, operator in enumerate(operators):
        tx_id = delegate_btc_success(operator, accounts[0], BTC_VALUE + index, LOCK_SCRIPT, LOCK_SCRIPT)
        tx_id_list.append(tx_id)
    turn_round()
    total_reward = 0
    for index, operator in enumerate(operators):
        before_agent = operators[index]
        __check_receipt_map_info(tx_id_list[index], {
            'candidate': before_agent
        })
        tx = btc_stake.transfer(tx_id_list[index], operators[index - 1])
        expect_event(tx, "transferredBtc", {
            "txid": tx_id_list[index],
            "sourceCandidate": operators[index],
            "targetCandidate": operators[index - 1],
            "delegator": accounts[0],
            "amount": BTC_VALUE + index
        })
        _, _, account_rewards, _ = parse_delegation([{
            "address": operators[0],
            "active": True,
            "power": [],
            "coin": [],
            "btc": [set_delegate(accounts[0], BTC_VALUE + index)]
        }], BLOCK_REWARD // 2)
        total_reward += account_rewards[accounts[0]]
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == total_reward


def test_claim_reward_without_pledge(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[1])
    turn_round()
    turn_round(consensuses, round_count=1)
    tx = stake_hub_claim_reward(accounts[1])
    assert 'claimedReward' not in tx.events


def test_stake_multiple_currencies_and_claim_rewards(btc_stake, btc_light_client, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 60000
    round_tag = get_current_round() - 6
    btc_light_client.setMiners(round_tag, operators[0], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def test_claiming_btc_reward_with_multiple_power(btc_stake, btc_light_client, set_candidate, core_agent):
    operators, consensuses = set_candidate
    delegate_amount = 40000
    turn_round()
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 1, operators[1], [accounts[3]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    CORE_AGENT.delegateCoin(operators[1], {'value': delegate_amount, 'from': accounts[1]})
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    tracker3 = get_tracker(accounts[3])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:4])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [set_delegate(accounts[3], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": []
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]
    assert tracker3.delta() == account_rewards[accounts[3]]


@pytest.mark.parametrize("transfer_type", ['all', 'part'])
def test_coin_transfer_with_power_and_btc_staking(btc_stake, btc_light_client, set_candidate, transfer_type):
    delegate_amount = 80000
    transfer_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    if transfer_type == 'all':
        transfer_amount = delegate_amount
    tx = CORE_AGENT.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[1]})
    expect_event(tx, 'transferredCoin', {
        'amount': transfer_amount
    })
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]]


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelegate_with_power_and_btc_staking(btc_stake, set_candidate, btc_light_client,
                                               undelegate_type):
    delegate_amount = 20000
    undelegate_amount = delegate_amount
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    if undelegate_type == 'part':
        undelegate_amount = 7000
    CORE_AGENT.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount, undelegate_amount=undelegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE), ]
    }], BLOCK_REWARD // 2)

    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]]


def test_claiming_btc_reward_with_power_and_btc_staking(btc_stake, set_candidate, btc_light_client):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 6
    btc_light_client.setMiners(round_tag, operators[0], [accounts[2]])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE), ]
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE


def test_operations_with_coin_power_and_btc_staking(btc_stake, set_candidate, btc_light_client):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[0], [accounts[2]])
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    undelegate_amount = 7000
    transfer_amount = delegate_amount // 2
    CORE_AGENT.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[1]})
    CORE_AGENT.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    btc_stake.transfer(tx_id, operators[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount, undelegate_amount=undelegate_amount)],
        # There are no rewards for BTC transfers
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    stake_hub_claim_reward(accounts[:3])
    assert tracker0.delta() == 0
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], transfer_amount - undelegate_amount)],
        "btc": []
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }, {
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], transfer_amount)],
        "btc": []
    }
    ], BLOCK_REWARD // 2)
    stake_hub_claim_reward(accounts[:3])
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def test_btc_transfer_does_not_claim_historical_rewards(btc_stake, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND * 2)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tx = btc_stake.transfer(tx_id, operators[1], {'from': accounts[0]})
    assert 'claimedReward' not in tx.events
    assert tracker0.delta() == 0


def test_transfer_btc_to_existing_btc_stake(btc_stake, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id, operators[1], {'from': accounts[0]})
    __check_candidate_map_info(operators[0], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': 0
    })
    __check_candidate_map_info(operators[1], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE * 2
    })
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    _, _, account_rewards0, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[1], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    _, _, account_rewards1, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": []
    }, {
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE), set_delegate(accounts[1], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards1[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards0[accounts[1]] + account_rewards1[accounts[1]] - FEE
    __check_candidate_map_info(operators[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0
    })


def test_transfer_btc_from_multiple_btc_stakings(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND * 2)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_SCRIPT, accounts[2])
    turn_round()
    transfer_btc_success(tx_id, operators[1], accounts[0])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE * 2)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] // 2 - FEE * 2


def test_btc_transfer_from_non_validator_account(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND * 2)
    tx_id = delegate_btc_success(accounts[3], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    btc_stake.transfer(tx_id, operators[1], {'from': accounts[0]})
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' in tx.events
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE


def test_multiple_btc_stakings_in_vout(btc_stake, set_candidate):
    btc_amount = 53820
    operators, consensuses = set_candidate
    btc_tx = (
        "0200000001dd94cb72979c528593cb1188f4e3bf43a52f5570edab981e3d303ff24166afe5000000006b483045022100f2f069e37929cdfafffa79dcc1cf478504875fbe2a41704a96aee88ec604c0e502207259c56c67de8de6bb8c15e9d14b6ad16acd86d6a834fbb0531fd27bee7e5e3301210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03b80b00"
        "000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "3cd200000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb68700000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT, {"from": accounts[2]})
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + LOCK_SCRIPT,
        'amount': btc_amount
    })
    __check_candidate_map_info(operators[0], {
        'stakedAmount': 0,
        'realtimeAmount': btc_amount
    })
    turn_round()
    __check_candidate_map_info(operators[0], {
        'stakedAmount': btc_amount,
        'realtimeAmount': btc_amount
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    stake_hub_claim_reward(accounts[0])
    __check_btc_tx_map_info(tx_id, {
        'amount': btc_amount,
        'outputIndex': 2,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_amount)],
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == FEE


def test_claim_reward_reentry(btc_stake, set_candidate, stake_hub):
    btc_stake_proxy = ClaimBtcRewardReentry.deploy(btc_stake.address, stake_hub.address, {'from': accounts[0]})
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    delegate_btc_success(operators[0], btc_stake_proxy.address, BTC_VALUE // 2, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE * 2, LOCK_SCRIPT, LOCK_TIME, accounts[2])
    CORE_AGENT.delegateCoin(operators[0], {"value": 20000, "from": accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(btc_stake_proxy)
    rewards = stake_hub.claimReward.call({'from': btc_stake_proxy})
    tx = btc_stake_proxy.claimRewardNew()
    expect_event(tx, "proxyClaim", {
        "success": True})
    assert tracker.delta() == rewards[2] - FEE


def test_claiming_rewards_with_multiple_staking_types(btc_stake, candidate_hub, set_candidate, btc_light_client):
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[1], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    btc_stake.transfer(tx_id, operators[1], {'from': accounts[0]})
    turn_round(consensuses)
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)

    stake_hub_claim_reward(accounts[:3])
    assert tracker0.delta() == 0
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def test_btc_transaction_with_witness_as_output_address(btc_stake, set_candidate):
    btc_tx = (
        "020000000001010280516aa5b5fb7bd9b7b94b14145af46f6404da96d5f56e1504e1d9d15ef6520200000017160014a808bc3c1ba547b0ba2df4abf1396f35c4d23b4ffeffffff"
        "03a08601"
        "00000000002200204969dea00948f43ae8f6efb45db768e41b15f4fd70d7fcf366c270c1cbca262a"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a001041e28fd65b17576a914a808bc3c1ba547b0ba2df4abf1396f35c4d23b4f88ac"
        "a4d81d"
        "000000000017a9144c35996fbf4026de7c8fe79c4320c248a10e4bf28702483045022100e32dd040238c19321407b7dfbba957e5988755779030dbcc52e6ae22a2a2088402202eeb497ae61aee9eba97cc4f5d34ba814c3ad1c0bf3286edaba05f044ab4bba401210386f359aa5a42d821370bf07a5ad86c1ff2d892662699103e462ae04d082d83ac00000000")
    lock_script = '041e28fd65b17576a914a808bc3c1ba547b0ba2df4abf1396f35c4d23b4f88ac'
    scrip_pubkey = 'a9144c35996fbf4026de7c8fe79c4320c248a10e4bf287'
    btc_tx = remove_witness_data_from_raw_tx(btc_tx, scrip_pubkey)
    tx = btc_stake.delegate(btc_tx, 200, [], 22, lock_script)
    assert 'delegated' in tx.events


def test_claiming_rewards_after_turn_round_failure(btc_stake, candidate_hub, btc_light_client,
                                                   set_candidate):
    block_times_tamp = 1723122315
    chain.mine(timestamp=block_times_tamp)
    candidate_hub.setControlRoundTimeTag(False)
    set_last_round_tag(2, block_times_tamp)
    turn_round()
    block_time = block_times_tamp
    operators, consensuses = set_candidate
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    candidate_hub.setTurnroundFailed(True)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 2)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    candidate_hub.setTurnroundFailed(False)
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 3)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD)
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 4)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == 0


def test_btc_stake_expiry_after_turn_round_failure(btc_stake, candidate_hub, btc_light_client,
                                                   set_candidate):
    set_last_round_tag(1, LOCK_TIME)
    chain_time = LOCK_TIME - Utils.ROUND_INTERVAL
    candidate_hub.setControlRoundTimeTag(False)
    operators, consensuses = set_candidate
    delegate_amount = 20000
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    chain.mine(timestamp=chain_time)
    turn_round()
    candidate_hub.setTurnroundFailed(True)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses)
    candidate_hub.setTurnroundFailed(False)
    chain.mine(timestamp=chain_time + Utils.ROUND_INTERVAL * 3)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD)
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    chain.mine(timestamp=chain_time + Utils.ROUND_INTERVAL * 4)
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


@pytest.mark.parametrize("round", [0, 1, 2, 3, 4])
def test_delegate_after_fixed_lock_time_different_rounds(btc_stake, candidate_hub, set_candidate,
                                                         round):
    operators, consensuses = set_candidate
    set_last_round_tag(3)
    turn_round()
    turn_round(consensuses, round_count=round)
    if round <= 1:
        delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)
    else:
        with brownie.reverts("insufficient locking rounds"):
            delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)


def test_delegator_calling_delegate_btc(btc_stake, set_candidate, relay_hub):
    operators, consensuses = set_candidate
    relay_hub.setRelayerRegister(accounts[0], False)
    assert relay_hub.isRelayer(accounts[0]) is False
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT, LOCK_TIME)


def test_small_amount_btc_stake(btc_stake, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], 1, LOCK_SCRIPT, LOCK_TIME)
    __check_btc_tx_map_info(tx_id, {
        'amount': 1
    })


def test_register_new_validator_after_pledge(core_agent, validator_set, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    tx_id = delegate_btc_success(operators[2], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    new_agent = accounts[8]
    consensus = register_candidate(operator=new_agent)
    operators.append(accounts[8])
    consensuses.append(consensus)
    transfer_btc_success(tx_id, operators[3], accounts[0])
    delegate_btc_success(operators[3], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD - FEE * 3
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE), set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] + TOTAL_REWARD


def test_append_and_transfer_delegate_btc(core_agent, validator_set, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    core_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[0]})
    turn_round()
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    transfer_btc_success(tx_id, operators[2], accounts[0])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[0], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)


def test_re_pledge_after_multiple_refusals(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    core_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    turn_round(consensuses, round_count=4)
    candidate_hub.acceptDelegate({'from': operators[0]})
    turn_round(consensuses, round_count=2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_btc_pledge_expiration_after_refusal(core_agent, validator_set, candidate_hub, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    core_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round(consensuses, round_count=5)
    tracker0 = get_tracker(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    turn_round(consensuses, round_count=2)
    assert tracker0.delta() == 0


def __get_receipt_map_info(tx_id):
    receipt_map = BTC_STAKE.receiptMap(tx_id)
    return receipt_map


def __get_candidate_map_info(candidate):
    candidate_map = BTC_STAKE.candidateMap(candidate)
    return candidate_map


def __get_stake_lock_script(public_key, lock_time, scrip_type='hash', lock_script_type='p2sh'):
    lock_scrip, pay_address = btc_script.k2_btc_script(public_key, lock_time, scrip_type, lock_script_type)
    return lock_scrip


def __get_btc_tx_map_info(tx_id):
    data = BTC_STAKE.btcTxMap(tx_id)
    return data


def __get_delegator_btc_map(delegator):
    data = BTC_STAKE.getDelegatorBtcMap(delegator)
    return data


def __get_accured_reward_per_btc_map(validate, round):
    BTC_STAKE.accuredRewardPerBTCMap(validate, round)


def __check_candidate_map_info(candidate, result: dict):
    data = __get_candidate_map_info(candidate)
    for i in result:
        assert data[i] == result[i]


def __check_receipt_map_info(tx_id, result: dict):
    data = __get_receipt_map_info(tx_id)
    for i in result:
        assert data[i] == result[i]


def __check_btc_tx_map_info(tx_id, result: dict):
    data = __get_btc_tx_map_info(tx_id)
    for i in result:
        assert data[i] == result[i]
