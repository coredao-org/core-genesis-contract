import brownie
import pytest
import rlp
from brownie import *
from web3 import constants
from .calc_reward import set_delegate, parse_delegation
from .common import register_candidate, turn_round, get_current_round, set_round_tag, stake_hub_claim_reward
from .delegate import *
from .utils import *

BLOCK_REWARD = 0
BTC_VALUE = 2000
FEE = 0
STAKE_ROUND = 3
TOTAL_REWARD = 0
# BTC delegation-related
PUBLIC_KEY = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
LOCK_TIME = 1736956800
LOCK_SCRIPT = '0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac'
btc_script = get_btc_script()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, pledge_agent, stake_hub, core_agent):
    global BLOCK_REWARD, FEE
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, TOTAL_REWARD, PLEDGE_AGENT
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
    PLEDGE_AGENT = pledge_agent


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


@pytest.fixture()
def delegate_btc_valid_tx():
    operator = accounts[5]
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME)
    btc_tx = build_btc_tx(operator, accounts[0], BTC_VALUE, lock_script, lock_script)
    return lock_script, btc_tx


def test_btc_stake_init_can_only_run_once(btc_stake):
    with brownie.reverts("the contract already init"):
        btc_stake.init()


def test_revert_if_not_called_by_only_pledge_agent(btc_stake):
    candidates = accounts[:3]
    amounts = [1000, 2000, 3000]
    realtime_amounts = [2000, 2000, 4000]
    with brownie.reverts("the sender must be pledge agent contract"):
        btc_stake._initializeFromPledgeAgent(candidates, amounts, realtime_amounts)


def test_initialize_from_pledge_agent_success(btc_stake):
    update_system_contract_address(btc_stake, pledge_agent=accounts[0])
    candidates = accounts[:3]
    amounts = [1000, 2000, 3000]
    realtime_amounts = [2000, 2000, 4000]
    btc_stake._initializeFromPledgeAgent(candidates, amounts, realtime_amounts)
    for index, i in enumerate(candidates):
        c = btc_stake.candidateMap(i)
        assert c[0] == amounts[index]
        assert c[1] == realtime_amounts[index]


def test_delegate_btc_with_lock_time_in_tx(btc_stake, set_candidate, stake_hub, btc_lst_stake, btc_agent):
    turn_round()
    operators, consensuses = set_candidate
    btc_amount = BTC_VALUE
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000188f5ba21514a0c32cbf90baab2b48feeeb0f200bfe7388730d80bf7f78ad27cd020000006a473044022066314a4e78bda5f9cb448d867ef3e8ef0678f7e0865f188e5cb362f5b40aed5c02203df085a6f742129a78729e8ca710a3065eb13cc01cb175457f947cbb6f3f89c701210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff02d007"
        "00000000000017a914f8f68b9543eaf5a9306090fde09ac765e1412e4587"
        "0000000000000000366a345341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "00000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': btc_amount
    })
    turn_round()
    assert btc_stake.receiptMap(tx_id)['candidate'] == operators[0]
    assert btc_stake.receiptMap(tx_id)['delegator'] == accounts[0]
    assert btc_stake.receiptMap(tx_id)['round'] == get_current_round() - 1
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD - FEE
    assert tracker1.delta() == FEE


def test_delegate_btc_with_lock_script_in_tx(btc_stake, set_candidate):
    btc_amount = BTC_VALUE * 3 // 2
    lock_script = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
    operators, consensuses = set_candidate
    btc_tx = (
        "0200000001dd94cb72979c528593cb1188f4e3bf43a52f5570edab981e3d303ff24166afe5000000006b483045022100f2f069e37929cdfafffa79dcc1cf478504875fbe2a41704a96aee88ec604c0e502207259c56c67de8de6bb8c15e9d14b6ad16acd86d6a834fbb0531fd27bee7e5e3301210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03b80b00"
        "000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "3cd20000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': btc_amount
    })
    __check_candidate_map_info(operators[0], {
        'stakedAmount': btc_amount,
        'realtimeAmount': btc_amount
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    __check_btc_tx_map_info(tx_id, {
        'amount': btc_amount,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_amount)]
    }], BLOCK_REWARD // 2)
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == FEE


def test_delegate_btc_success_public_key(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME, 'key')
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, lock_script)
    tx_id = get_transaction_txid(btc_tx)
    tx = BTC_STAKE.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    __check_candidate_map_info(operators[0], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE
    })
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': BTC_VALUE
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    __check_btc_tx_map_info(tx_id, {
        'amount': BTC_VALUE,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == TOTAL_REWARD - FEE


def test_delegate_btc_success_public_hash(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME, 'hash')
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, lock_script)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    tx_id = get_transaction_txid(btc_tx)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': BTC_VALUE
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == TOTAL_REWARD - FEE


def test_delegate_btc_success_multi_sig_script(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000188f5ba21514a0c32cbf90baab2b48feeeb0f200bfe7388730d80bf7f78ad27cd020000006a473044022066314a4e78bda5f9cb448d867ef3e8ef0678f7e0865f188e5cb362f5b40aed5c02203df085a6f742129a78729e8ca710a3065eb13cc01cb175457f947cbb6f3f89c701210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff02d007"
        "00000000000017a914f8f68b9543eaf5a9306090fde09ac765e1412e4587"
        "0000000000000000366a345341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "00000000")
    btc_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD - FEE


def test_delegate_btc_with_witness_transaction_hash_script(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = '0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac'
    btc_tx = (
        "0200000001ac5d10fc2c7fde4aa105a740e0ae00dafa66a87f472d0395e71c4d70c4d698ba020000006b4830450221009b0f6b1f2cdb0125f166245064d18f026dc77777a657b83d6f56c79101c269b902206c84550b64755ec2eba1893e81b22a57350b003aa5a3a8915ac7c2eb905a1b7501210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03140500"
        "0000000000220020aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "bcc00000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    btc_amount = 1300
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': btc_amount
    })
    __check_btc_tx_map_info(tx_id, {
        'amount': btc_amount,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    delegate_info = [{
        "address": "n0",
        "active": True,
        "coin": [],
        "power": [],
        "btc": [set_delegate(accounts[0], btc_amount)],
    }]
    _, _, account_rewards, _ = parse_delegation(delegate_info, BLOCK_REWARD // 2)

    assert tracker.delta() == account_rewards[accounts[0]] - FEE


def test_delegate_btc_with_witness_transaction_key_script(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME, 'key', 'p2wsh')
    btc_amount = 1400
    btc_tx = build_btc_tx(operators[0], accounts[0], btc_amount, lock_script, LOCK_TIME, 'p2wsh')
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': btc_amount
    })
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
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == TOTAL_REWARD - FEE


def test_invalid_lock_script(btc_stake, delegate_btc_valid_tx):
    _, btc_tx = delegate_btc_valid_tx
    lock_script = "0380db8767b175210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    lock_script = "0480db8767b275210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_invalid_btc_transaction(btc_stake, set_candidate):
    btc_tx = (
        "0200000001f57820c2694b1d88e85dbe0e23c4c9bab63af2907fd4f277761e2317c0717956020000006a473044022020509b1e3d63a3e2d893bb5a1f0b873886db420727010e7e7f024394c929885b022027953577efb6deb377e6b3df98fa58f36c05c8d08c46538c7c6a4dbde172cb1e01210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12feffffff03a9149ca26c6aa5a614836d041193ab7df1b6d650791387"
        "00000000000000002c6a2a045896c42c56fdb78294f96b0cfa33c92be"
        "d7d75f96a9fb29aac15b9a4b7f17c3385939b007540f4d7914e930100000000001976a914574fdd26858c28ede5225a809f747c"
        "01fcc1f92a88ac00000000")
    with brownie.reverts("BitcoinHelper: invalid tx"):
        btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT)


def test_revert_on_unconfirmed_btc_tx_delegate(btc_stake, btc_light_client, delegate_btc_valid_tx):
    btc_light_client.setCheckResult(False, 0)
    lock_script, btc_tx = delegate_btc_valid_tx
    with brownie.reverts("btc tx isn't confirmed"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_duplicate_btc_tx_delegate(btc_stake, delegate_btc_valid_tx):
    lock_script, btc_tx = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_restaking_after_btc_staking_expiry(btc_stake, candidate_hub, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    lock_script, btc_tx = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses, round_count=4)
    stake_hub_claim_reward(accounts[0])
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


def test_insufficient_lock_round_revert(btc_stake, set_candidate, delegate_btc_valid_tx):
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    set_round_tag(end_round)
    lock_script, btc_tx = delegate_btc_valid_tx
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    set_last_round_tag(0)
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    set_last_round_tag(STAKE_ROUND)
    tx = btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    assert "delegated" in tx.events


@pytest.mark.parametrize("output_view", [
    pytest.param("a6149ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_HASH160 error"),
    pytest.param("a9139ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_PUSHBYTES_20 error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791287", id="ScriptPubKey error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791386", id="OP_EQUAL error"),
    pytest.param("a9142d0a37f671e76a72f6dc30669ffaefa6120b798887", id="output error")
])
def test_revert_p2sh_on_invalid_btc_tx_output(btc_stake, set_candidate, output_view):
    operators, consensuses = set_candidate
    lock_scrip, old_pay_address = btc_script.k2_btc_script(PUBLIC_KEY, LOCK_TIME, 'key', 'p2sh')
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, lock_scrip, LOCK_TIME)
    btc_tx = btc_tx.replace(old_pay_address.replace('0x', ''), output_view)
    with brownie.reverts("staked value is zero"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_scrip)


@pytest.mark.parametrize("output_view", [
    pytest.param("0120aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a", id="OP_0 error"),
    pytest.param("0021aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a", id="OP_PUSHBYTES_32 error"),
    pytest.param("0020aee9137b4958e35085907caaa2d5a9e659b0b1036e06f04280e2e98520f7f16c", id="ScriptPubKey error")
])
def test_revert_on_invalid_witness_btc_tx_output(btc_stake, set_candidate, output_view):
    lock_script = '0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac'
    btc_tx = (
        "0200000001ac5d10fc2c7fde4aa105a740e0ae00dafa66a87f472d0395e71c4d70c4d698ba020000006b4830450221009b0f6b1f2cdb0125f166245064d18f026dc77777a657b83d6f56c79101c269b902206c84550b64755ec2eba1893e81b22a57350b003aa5a3a8915ac7c2eb905a1b7501210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03140500"
        f"000000000022{output_view}"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "bcc00000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("staked value is zero"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_insufficient_payload_length(btc_stake, set_candidate):
    btc_tx = (
        f"0200000001ac5d10fc2c7fde4aa105a740e0ae00dafa66a87f472d0395e71c4d70c4d698ba020000006b4830450221009b0f6b1f2cdb0125f166245064d18f026dc77777a657b83d6f56c79101c269b902206c84550b64755ec2eba1893e81b22a57350b003aa5a3a8915ac7c2eb905a1b7501210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12feffffff"
        f"03b80b000000000000220020aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a"
        f"00000000000000002c6a2a0458ccf7e1dab7d90a0a91f8b1f6a693bf0bb3a979a09fb29aac15b9a4b7f17c3385939b007540f4d791"
        "8e440100000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("payload length is too small"):
        btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT)


def test_revert_on_invalid_magic_value(btc_stake, set_candidate, delegate_btc_valid_tx):
    lock_script, _, = delegate_btc_valid_tx
    error_magic = '5341542c'
    btc_tx = (
        f"0200000001f57820c2694b1d88e85dbe0e23c4c9bab63af2907fd4f277761e2317c0717956020000006a473044022020509b1e3d63a3e2d893bb5a1f0b873886db420727010e7e7f024394c929885b022027953577efb6deb377e6b3df98fa58f36c05c8d08c46538c7c6a4dbde172cb1e01210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12feffffff"
        f"03d00700000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        f"0000000000000000526a4c4f{error_magic}04589fb29aac15b9a4b7f17c3385939b007540f4d7911ef01e76f1aad50144a32680f16aa97a10f8af95010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88aca443"
        "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("wrong magic"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_unequal_chain_id(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME)
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, lock_script,
                          chain_id=Utils.CHAIN_ID - 1)
    with brownie.reverts("wrong chain id"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_incorrect_version(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME)
    btc_tx = build_btc_tx(operators[0], accounts[0], BTC_VALUE, lock_script, version=2)
    with brownie.reverts("unsupported sat+ version in btc staking"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_transaction_without_op_return(btc_stake):
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000102ae7f498ec542f8b2a70d3a5750058337a042b55b4130587a5271568921dc70020000006b483045022100f78b1eaacb6f10100015eca4618edea515d06d1a4ec432b2b669f4cbeed0dd1c02206c9137982f46c1129de1069b83987b1ad907314231077ac992a8e8990c92c8d401210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ffffffff"
        "02bc34000000000000"
        "220020f55d9bd2487756dd81b84946aab690e0e2e9b17c681a81c2d1ce22006395292b9b69"
        "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("no opreturn"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})


def test_revert_on_btc_stake_with_zero_address(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    btc_tx = build_btc_tx(operators[0], constants.ADDRESS_ZERO, BTC_VALUE, LOCK_SCRIPT)
    btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT, {"from": accounts[2]})
    turn_round()
    turn_round(consensuses)
    tx = stake_hub_claim_reward(ZERO_ADDRESS)
    assert 'claimedReward' in tx.events


def test_stake_to_inactive_agent_success_without_reward(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    btc_tx = build_btc_tx(accounts[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, LOCK_SCRIPT)
    assert 'delegated' in tx.events
    turn_round()
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_revert_for_non_delegator_or_relayer_calling_delegate_btc(btc_stake, delegate_btc_valid_tx, relay_hub,
                                                                  set_candidate):
    lock_script, btc_tx = delegate_btc_valid_tx
    relay_hub.setRelayerRegister(accounts[1], False)
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


def test_successful_delegate_btc_call_by_relayer(btc_stake, delegate_btc_valid_tx, relay_hub,
                                                 set_candidate):
    lock_script, btc_tx = delegate_btc_valid_tx
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    relay_hub.setRelayerRegister(accounts[5], True)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    assert 'delegated' in tx.events


@pytest.mark.parametrize("btc_value", [1, 2, 100, 800000, 120000, 50000000])
def test_btc_delegate_no_amount_limit(btc_stake, set_candidate, delegate_btc_valid_tx, btc_value):
    operators, consensuses = set_candidate
    lock_script, btc_tx = __create_btc_stake_scrip_and_btc_tx(operators[0], accounts[0], btc_value)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    assert "delegated" in tx.events
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == TOTAL_REWARD - FEE
    assert tracker.delta() == FEE


def test_btc_stake_distribute_reward_success(btc_stake, candidate_hub):
    validators = accounts[:3]
    amounts = [1000, 2000, 3000]
    staked_amounts = [3000, 5000, 6000]
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    round_tag = get_current_round()
    for index, v in enumerate(validators):
        btc_stake.setCandidateMap(v, staked_amounts[index], staked_amounts[index], [round_tag - 1])
    btc_stake.distributeReward(validators, amounts)
    for index, v in enumerate(validators):
        reward = amounts[index] * Utils.BTC_DECIMAL // staked_amounts[index]
        __check_accured_reward_per_btc(v, round_tag, reward)


def test_distribute_reward_with_new_validator(btc_stake, candidate_hub):
    validators = accounts[:3]
    amounts = [2000, 1000, 3000]
    staked_amounts = [3000, 5000, 6000]
    round_tag = get_current_round()
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    for index, v in enumerate(validators[:2]):
        btc_stake.setCandidateMap(v, staked_amounts[index], staked_amounts[index], [round_tag - 1])
    btc_stake.setCandidateMap(accounts[2], staked_amounts[2], staked_amounts[2], [])
    assert len(__get_continuous_reward_end_rounds(accounts[2])) == 0
    btc_stake.distributeReward(validators, amounts)
    for index, v in enumerate(validators):
        reward = amounts[index] * Utils.BTC_DECIMAL // staked_amounts[index]
        __check_accured_reward_per_btc(v, round_tag, reward)
    assert __get_continuous_reward_end_rounds(accounts[2])[0] == round_tag


def test_distribute_reward_with_existing_history(btc_stake, candidate_hub):
    validators = accounts[:3]
    amounts = [2000, 1000, 3000]
    staked_amounts = [3000, 5000, 6000]
    round_tag = get_current_round()
    history_reward0 = 5000
    history_reward1 = 120000
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    btc_stake.setCandidateMap(accounts[0], staked_amounts[0], staked_amounts[0], [round_tag - 6, round_tag - 3])
    btc_stake.setAccuredRewardPerBTCMap(accounts[0], round_tag - 6, history_reward0)
    btc_stake.setAccuredRewardPerBTCMap(accounts[0], round_tag - 3, history_reward1)
    btc_stake.setCandidateMap(accounts[1], staked_amounts[1], staked_amounts[1], [round_tag - 1, ])
    btc_stake.setCandidateMap(accounts[2], staked_amounts[2], staked_amounts[2], [])
    btc_stake.distributeReward(validators, amounts)
    account_reward0 = history_reward1 + amounts[0] * Utils.BTC_DECIMAL // staked_amounts[0]
    __check_accured_reward_per_btc(accounts[0], round_tag, account_reward0)
    for index, v in enumerate(validators[1:]):
        index = index + 1
        reward = amounts[index] * Utils.BTC_DECIMAL // staked_amounts[index]
        __check_accured_reward_per_btc(v, round_tag, reward)
    assert __get_continuous_reward_end_rounds(accounts[2])[0] == round_tag


def test_distribute_reward_with_zero_amount(btc_stake, candidate_hub):
    validators = accounts[:3]
    rewards = [0, 0, 0]
    round_tag = get_current_round()
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    btc_stake.distributeReward(validators, rewards)
    reward = 0
    for index, v in enumerate(validators[1:]):
        __check_accured_reward_per_btc(v, round_tag, reward)


def test_get_btc_stake_amounts_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    stake_amounts = []
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE + index, LOCK_SCRIPT)
        stake_amounts.append(BTC_VALUE + index)
    amounts = btc_stake.getStakeAmounts(operators)
    assert amounts == stake_amounts


def test_btc_claim_reward_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD * 3
    assert reward_unclaimed == 0
    assert acc_staked_amount == BTC_VALUE * 3


def test_reward_increase_with_longer_stake_duration(btc_stake, set_candidate, btc_light_client):
    operators, consensuses = set_candidate
    btc_light_client.setCheckResult(True, LOCK_TIME - 1000)
    grades = [(100, 2000), (500, 5000)]
    for g in grades:
        btc_stake.setTlpRates(g[0], g[1])
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD // 2 * 3
    assert reward_unclaimed == TOTAL_REWARD * 3 - TOTAL_REWARD // 2 * 3
    assert acc_staked_amount == BTC_VALUE * 3
    assert btc_stake.rewardMap(accounts[0]) == (0, 0, 0)
    assert len(btc_stake.getDelegatorBtcMap(accounts[0])) == 3


def test_claim_expired_stake_btc_reward(btc_stake, set_candidate, btc_agent):
    operators, consensuses = set_candidate
    set_last_round_tag(1)
    lock_script0 = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME + Utils.ROUND_INTERVAL * 2)
    lock_script1 = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME + Utils.ROUND_INTERVAL * 2)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    tx_id0 = delegate_btc_success(operators[1], accounts[0], BTC_VALUE, lock_script0)
    tx_id1 = delegate_btc_success(operators[2], accounts[0], BTC_VALUE, lock_script1)
    __get_receipt_map_info(tx_id0)
    turn_round()
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    tx_ids = btc_stake.getDelegatorBtcMap(accounts[0])
    reward, _, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == 0
    assert acc_staked_amount == 0
    assert len(tx_ids) == 3
    update_system_contract_address(btc_stake, btc_agent=btc_agent)
    turn_round(consensuses)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD * 3
    assert acc_staked_amount == BTC_VALUE * 3
    tx_ids = btc_stake.getDelegatorBtcMap(accounts[0])
    assert tx_ids == [tx_id1, tx_id0]


def test_claim_multiple_rounds_of_btc_rewards(btc_stake, set_candidate, btc_agent):
    operators, consensuses = set_candidate
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses, round_count=3)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD * 9
    assert acc_staked_amount == BTC_VALUE * 9
    update_system_contract_address(btc_stake, btc_agent=btc_agent)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD * 6
    assert acc_staked_amount == BTC_VALUE * 6


def test_claim_rewards_after_multiple_expired_stake_rounds(btc_stake, set_candidate, btc_agent):
    operators, consensuses = set_candidate
    set_last_round_tag(1)
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses, round_count=3)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == TOTAL_REWARD * 3
    assert acc_staked_amount == BTC_VALUE * 3


def test_claim_reward_reverts_on_nonexistent_tx_id(btc_stake, set_candidate, btc_agent):
    btc_stake.setRoundTag(0)
    operators, consensuses = set_candidate
    for index, o in enumerate(operators):
        delegate_btc_success(o, accounts[0], BTC_VALUE, LOCK_SCRIPT)
    error_tx_id = '0xd6ca139d58ae36e3beb84e0ea5458ef999dcaee865ec12d0cc50e46f31979d53'
    btc_stake.setDelegatorMap(accounts[0], error_tx_id)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    with brownie.reverts("invalid deposit receipt"):
        btc_stake.claimReward(accounts[0])


def test_only_btc_agent_can_call_claim_reward(btc_stake, btc_agent):
    with brownie.reverts("the msg sender must be bitcoin agent contract"):
        btc_stake.claimReward(accounts[0])


@pytest.mark.parametrize('round_count', [0, 1])
@pytest.mark.parametrize("tests", [
    [2000, 'delegate', 'transfer', 'claim'],
    [6000, 'delegate', 'delegate', 'claim'],
    [2000, 'delegate', 'delegate', 'transfer', 'claim'],
    [2000, 'delegate', 'transfer', 'claim'],
    [2000, 'transfer', 'claim'],
    [2000, 'transfer', 'delegate']
])
def test_get_acc_stake_amount_success(btc_stake, btc_agent, set_candidate, round_count, tests):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    for i in tests:
        if i == 'delegate':
            delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
        elif i == 'transfer':
            transfer_btc_success(tx_id, operators[2], accounts[0])
        else:
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=round_count)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    expect_stake_amount = tests[0]
    if round_count == 0:
        expect_stake_amount = 0
    assert acc_staked_amount == expect_stake_amount


@pytest.mark.parametrize("tests", [
    [10000, 'delegate', 'transfer', 'claim'],
    [16000, 'delegate', 'delegate', 'claim'],
    [12000, 'delegate', 'delegate', 'transfer', 'claim'],
    [10000, 'delegate', 'transfer', 'claim'],
    [8000, 'transfer', 'claim'],
    [10000, 'transfer', 'delegate']
])
def test_multi_round_acc_amount(btc_stake, btc_agent, set_candidate, tests):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    for i in tests:
        if i == 'delegate':
            delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
        elif i == 'transfer':
            transfer_btc_success(tx_id, operators[2], accounts[0])
        else:
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    expect_stake_amount = tests[0]
    assert acc_staked_amount == expect_stake_amount


def test_check_acc_stake_amount_after_btc_expiration(btc_stake, btc_agent, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(1)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses, round_count=5)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert acc_staked_amount == BTC_VALUE


def test_clear_acc_stake_amount_after_claiming_rewards(btc_stake, slash_indicator, btc_agent, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(20)
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        slash_indicator.slash(consensuses[0])
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert reward == 0
    assert acc_staked_amount == BTC_VALUE * 2
    update_system_contract_address(btc_stake, btc_agent=btc_agent)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_stake.claimReward(accounts[0]).return_value
    assert acc_staked_amount == BTC_VALUE * 2


def test_only_btc_agent_can_call_set_new_round(btc_stake, btc_agent):
    round_tag = get_current_round()
    with brownie.reverts("the msg sender must be bitcoin agent contract"):
        btc_stake.setNewRound(accounts[:2], round_tag)


def test_set_new_round_success(btc_stake):
    round_tag = 7
    assert btc_stake.roundTag() == round_tag
    turn_round()
    round_tag += 1
    for index, o in enumerate(accounts[:4]):
        btc_stake.setCandidateMap(o, 0, BTC_VALUE + index, [])
    update_system_contract_address(btc_stake, btc_agent=accounts[0])
    btc_stake.setNewRound(accounts[:4], round_tag + 1)
    for index, op in enumerate(accounts[:4]):
        assert btc_stake.candidateMap(op) == [BTC_VALUE + index, BTC_VALUE + index]
    assert btc_stake.roundTag() == round_tag + 1


def test_only_stake_hub_can_call_prepare(btc_stake):
    with brownie.reverts("the msg sender must be stake hub contract"):
        btc_stake.prepare(get_current_round())


def test_prepare_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script0 = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME + Utils.ROUND_INTERVAL * 2)
    end_round0 = LOCK_TIME // Utils.ROUND_INTERVAL
    end_round1 = (LOCK_TIME + Utils.ROUND_INTERVAL * 2) // Utils.ROUND_INTERVAL
    delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE + 1, lock_script0)
    delegate_btc_success(operators[2], accounts[0], BTC_VALUE + 2, lock_script0)
    set_last_round_tag(1)
    turn_round()
    update_system_contract_address(btc_stake, stake_hub=accounts[0])
    __get_candidate_map_info(operators[0])
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(end_round0)
    __check_list_length(candidate_list, 1)
    __check_list_length(amounts, 1)
    assert amounts[0] == BTC_VALUE + 1
    btc_stake.prepare(end_round0)
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(end_round0)
    __check_list_length(candidate_list, 0)
    __check_list_length(amounts, 0)
    __check_candidate_map_info(operators[0], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': 0,
    })
    btc_stake.prepare(end_round1)
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(end_round1)
    __check_list_length(candidate_list, 0)
    __check_list_length(amounts, 0)


def test_prepare_success_with_no_expiring_collateral(btc_stake):
    turn_round()
    update_system_contract_address(btc_stake, stake_hub=accounts[0])
    round_tag = get_current_round()
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(round_tag)
    __check_list_length(candidate_list, 0)
    btc_stake.prepare(round_tag)
    btc_stake.prepare(round_tag + 1)


def test_prepare_success_after_specific_round_interval(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script0 = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME + Utils.ROUND_INTERVAL * 2)
    end_round1 = (LOCK_TIME + Utils.ROUND_INTERVAL * 2) // Utils.ROUND_INTERVAL
    delegate_btc_success(operators[1], accounts[0], BTC_VALUE + 1, lock_script0)
    delegate_btc_success(operators[2], accounts[0], BTC_VALUE + 2, lock_script0)
    set_last_round_tag(1)
    turn_round()
    update_system_contract_address(btc_stake, stake_hub=accounts[0])
    __get_candidate_map_info(operators[0])
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(end_round1)
    __check_list_length(candidate_list, 2)
    __check_list_length(amounts, 2)
    existAmount = 1
    assert amounts[0] == BTC_VALUE + 1 + existAmount
    btc_stake.prepare(end_round1)
    candidate_list, amounts = btc_stake.getRound2expireInfoMap(end_round1)
    __check_list_length(candidate_list, 0)
    __check_list_length(amounts, 0)
    __check_candidate_map_info(operators[1], {
        'stakedAmount': BTC_VALUE + 1,
        'realtimeAmount': 0,
    })
    __check_candidate_map_info(operators[2], {
        'stakedAmount': BTC_VALUE + 2,
        'realtimeAmount': 0,
    })


def test_transfer_btc_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    tx = btc_stake.transfer(tx_id, operators[1])
    CORE_AGENT.transferCoin(operators[0], operators[2], delegate_amount, {'from': accounts[1]})
    expect_event(tx, 'transferredBtc', {
        'txid': tx_id,
        'sourceCandidate': operators[0],
        'targetCandidate': operators[1],
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD - FEE


def test_transfer_btc_when_no_rewards_in_current_round(btc_stake, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id, operators[1])
    __check_receipt_map_info(tx_id, {
        'candidate': operators[1],
        'delegator': accounts[0],
        'round': get_current_round()
    })
    __check_btc_tx_map_info(tx_id, {
        'lockTime': LOCK_TIME
    })
    __check_candidate_map_info(operators[1], {
        'stakedAmount': 0,
        'realtimeAmount': BTC_VALUE
    })
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0
    __check_candidate_map_info(operators[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0
    })
    __check_candidate_map_info(operators[1], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE
    })


def test_transfer_with_nonexistent_stake_certificate(btc_stake, set_candidate):
    not_found_tx_id = '0x8a2d192b0d0276fee31689693269e14aa9c78982c0d29ddf417a3064fd623892'
    operators, consensuses = set_candidate
    turn_round()
    with brownie.reverts("btc tx not found"):
        btc_stake.transfer(not_found_tx_id, operators[1])


def test_transfer_btc_reverts_for_non_delegator(btc_stake, set_candidate):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    with brownie.reverts("not the delegator of this btc receipt"):
        btc_stake.transfer(tx_id, operators[1], {'from': accounts[1]})
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_transfer_btc_to_current_validator(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    with brownie.reverts("can not transfer to the same validator"):
        btc_stake.transfer(tx_id, operators[0])


def test_transfer_btc_to_validator_with_lock_period_ending(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    set_last_round_tag(STAKE_ROUND)
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=3)
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.transfer(tx_id, operators[1])
    turn_round(consensuses, round_count=1)
    __check_btc_tx_map_info(tx_id, {
        'amount': BTC_VALUE,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    __check_receipt_map_info(tx_id, {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 4
    })
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.transfer(tx_id, operators[1])
    stake_hub_claim_reward(accounts[0])
    # after the lockout period expires, the recorded data will be reset to zero.
    __check_receipt_map_info(tx_id, {
        'candidate': constants.ADDRESS_ZERO,
        'delegator': constants.ADDRESS_ZERO,
        'round': 0
    })


def test_transfer_to_non_validator_target(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses)
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [accounts[2].address])
    with brownie.reverts(f"{error_msg}"):
        btc_stake.transfer(tx_id, accounts[2])
    __check_candidate_map_info(operators[0], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE
    })
    __check_btc_tx_map_info(tx_id, {
        'amount': BTC_VALUE,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })


def test_transfer_expired_collateral_quantity_decreases(btc_stake, set_candidate):
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    operators, consensuses = set_candidate
    tx_id = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    candidate_list, amounts = __get_round2_expire_info_map(end_round)
    assert candidate_list == [operators[0]]
    assert amounts == [BTC_VALUE + 1]
    btc_stake.transfer(tx_id, operators[2])
    candidate_list, amounts = __get_round2_expire_info_map(end_round)
    assert candidate_list == [operators[0], operators[2]]
    assert amounts == [1, BTC_VALUE + 1]


def test_calculate_btc_reward_success(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    tx_id0 = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    tx_id1 = delegate_btc_success(operators[0], accounts[0], BTC_VALUE + 1, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    reward = btc_stake.calculateRewardMock([tx_id0, tx_id1]).return_value
    assert reward == [TOTAL_REWARD // 2 * 2, BTC_VALUE * 2 + 1]
    reward = btc_stake.calculateRewardMock([tx_id0, tx_id1]).return_value
    assert reward == [0, 0]
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == TOTAL_REWARD // 2 * 2 - FEE * 2
    reward = btc_stake.calculateRewardMock([]).return_value
    assert reward == [0, 0]


def test_calculate_btc_reward_with_invalid_txid(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    tx_id0 = delegate_btc_success(operators[0], accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    turn_round(consensuses)
    with brownie.reverts("invalid deposit receipt"):
        btc_stake.calculateRewardMock([tx_id0, '0x00'])


def test_move_data_success(btc_stake, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    btc_amount = BTC_VALUE // 2
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    tx_id = old_delegate_btc_success(btc_amount, operators[2], accounts[1], lock_time=LOCK_TIME, script=LOCK_SCRIPT)
    btc_stake.moveData([tx_id])
    __check_receipt_map_info(tx_id, {
        'candidate': operators[2],
        'delegator': accounts[1],
        'round': 1
    })
    __check_btc_tx_map_info(tx_id, {
        'amount': btc_amount,
        'outputIndex': 0,
        'blockTimestamp': 0,
        'lockTime': LOCK_TIME // Utils.ROUND_INTERVAL * Utils.ROUND_INTERVAL,
        'usedHeight': 0
    })
    assert __get_delegator_btc_map(accounts[1])[0] == tx_id
    tx_ids = []
    for i in range(2):
        tx_id = old_delegate_btc_success(btc_amount + i, operators[i], accounts[i], lock_time=LOCK_TIME,
                                         script=LOCK_SCRIPT)
        tx_ids.append(tx_id)
    btc_stake.moveData(tx_ids)
    for i in range(2):
        __check_receipt_map_info(tx_ids[i], {
            'candidate': operators[i],
            'delegator': accounts[i],
            'round': 1
        })
    agents, amounts = __get_round2_expire_info_map(end_round)
    assert agents[0] == operators[2]
    assert amounts[0] == btc_amount + 1


def test_move_data_with_btc_already_collateralized(btc_stake, pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    btc_amount = BTC_VALUE // 2
    tx_id = old_delegate_btc_success(btc_amount, operators[1], accounts[1], lock_time=LOCK_TIME, script=LOCK_SCRIPT)
    btc_stake.moveData([tx_id])
    __check_receipt_map_info(tx_id, {
        'candidate': operators[1],
        'delegator': accounts[1],
        'round': 1
    })
    btc_stake.moveData([tx_id])


def test_get_grades_success(btc_stake, pledge_agent, set_candidate):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades = [[0, 1], [1000, 2000]]
    grades_encode = rlp.encode(grades)
    btc_stake.updateParam('grades', grades_encode)
    assert btc_stake.getGrades() == [[0, 1], [grades[1][0] * Utils.ROUND_INTERVAL, 2000]]


def test_update_param_only_callable_by_gov_hub(btc_stake):
    with brownie.reverts("the msg sender must be governance contract"):
        btc_stake.updateParam('grades', '1')


def test_update_param_callable_only_after_init(btc_stake):
    btc_stake.setAlreadyInit(False)
    with brownie.reverts("the contract not init yet"):
        btc_stake.updateParam('grades', '1')


@pytest.mark.parametrize("grades", [
    [[0, 1], [1000, 2000]],
    [[0, 1200], [2000, 2000], [3000, 4000]],
    [[0, 1000], [2000, 2000], [3000, 4000], [3500, 9000], [4000, 10000]],
    [[0, 1000], [1, 2000], [2, 4000], [30, 9000], [40, 10000]]
])
def test_update_param_grades_success(btc_stake, grades):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    btc_stake.updateParam('grades', grades_encode)
    for i in range(btc_stake.getGradesLength()):
        grades_value = btc_stake.grades(i)
        grades[i][0] = grades[i][0] * Utils.ROUND_INTERVAL
        assert grades_value == grades[i]


@pytest.mark.parametrize("grades", [
    [[0, 1], [4001, 2000]],
    [[0, 1000], [4002, 2000], [2, 4000], [30, 9000], [40, 10000]],
    [[0, 1000], [1, 2000], [2, 4000], [4001, 9000], [40, 10000]],
    [[5000, 1000], [1, 2000], [2, 4000], [4001, 9000], [40, 10000]],
])
def test_revert_on_exceeding_max_lock_duration(btc_stake, grades):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    indices = [index for index, item in enumerate(grades) if item[0] > 4000][0]
    percentage = 0
    if indices > 0:
        indices -= 1
        percentage = grades[indices][1]
    with brownie.reverts(f"OutOfBounds: lockDuration, {percentage}, 0, 4000"):
        btc_stake.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grades", [
    [[0, 1], [1, 10001]],
    [[1, 10002], [1, 2000], [2, 4000], [4000, 9000], [40, 10002]],
    [[1000, 1000], [1, 2000], [2, 10001], [4000, 9000], [40, 1000]],
])
def test_reward_discount_over_100_percent_reverts(btc_stake, grades):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    percentage = [item[1] for item in grades if item[1] > 10000][0]
    with brownie.reverts(f"OutOfBounds: percentage, {percentage}, 1, 10000"):
        btc_stake.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grades", [
    [[1, 1], [0, 10000]],
    [[40, 1000], [3000, 2000], [2, 4000], [4000, 9000], [40, 10000]],
    [[3000, 1000], [1, 2000], [2, 10000], [4000, 9000], [40, 1000]],
    [[1, 1000], [1, 2000], [2, 3000], [3, 9000], [4, 10000]],
])
def test_lock_duration_sorting_error_reverts(btc_stake, grades):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    with brownie.reverts(f"lockDuration disorder"):
        btc_stake.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grades", [
    [[0, 10000], [1, 1000]],
    [[40, 10000], [50, 2000], [60, 4000], [70, 9000], [80, 2000]],
    [[300, 1000], [400, 2000], [500, 10000], [600, 9000], [4000, 1000]],
    [[0, 1000], [1, 3000], [2, 3000], [3, 9000], [4, 10000]],
])
def test_percentage_sorting_error_reverts(btc_stake, grades):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    with brownie.reverts("percentage disorder"):
        btc_stake.updateParam('grades', grades_encode)


def test_lock_duration_not_starting_from_zero_reverts(btc_stake):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode([[1, 1000], [2, 2000]])
    with brownie.reverts("lowest lockDuration must be zero"):
        btc_stake.updateParam('grades', grades_encode)


def test_grades_length_zero(btc_stake):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    grades_encode = rlp.encode([])
    with brownie.reverts("MismatchParamLength: grades"):
        btc_stake.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grade_active", [0, 1])
def test_update_param_grade_active_success(btc_stake, grade_active):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    btc_stake.updateParam('gradeActive', grade_active)
    assert btc_stake.gradeActive() == grade_active


def test_revert_on_grade_active_exceeding_limit(btc_stake):
    grade_active = 2
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: gradeActive, {grade_active}, 0, 1"):
        btc_stake.updateParam('gradeActive', grade_active)


def test_update_param_short_param_reverts(btc_stake):
    grade_active = 2
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(grade_active), 60)
    with brownie.reverts(f"MismatchParamLength: gradeActive"):
        btc_stake.updateParam('gradeActive', hex_value)


def test_revert_on_nonexistent_governance_param(btc_stake):
    update_system_contract_address(btc_stake, gov_hub=accounts[0])
    with brownie.reverts(f"UnsupportedGovParam: error"):
        btc_stake.updateParam('error', '0x00')


def __get_round2_expire_info_map(round_tag):
    agents, amounts = BTC_STAKE.getRound2expireInfoMap(round_tag)
    return agents, amounts


def __get_continuous_reward_end_rounds(candidate):
    end_rounds = BTC_STAKE.getContinuousRewardEndRounds(candidate)
    return end_rounds


def __create_btc_stake_scrip_and_btc_tx(candidate, delegator, amount, public_key_type='hash',
                                        lock_script_type='p2sh'):
    lock_script = __get_stake_lock_script(PUBLIC_KEY, LOCK_TIME, public_key_type, lock_script_type)
    btc_tx = build_btc_tx(candidate, delegator, amount, lock_script, LOCK_TIME, lock_script_type)
    return lock_script, btc_tx


def __check_list_length(result, length):
    assert len(result) == length


def __get_stake_lock_script(public_key, lock_time, scrip_type='hash', lock_script_type='p2sh'):
    lock_scrip, pay_address = btc_script.k2_btc_script(public_key, lock_time, scrip_type, lock_script_type)
    return lock_scrip


def __get_receipt_map_info(tx_id):
    receipt_map = BTC_STAKE.receiptMap(tx_id)
    return receipt_map


def __get_candidate_map_info(candidate):
    candidate_map = BTC_STAKE.candidateMap(candidate)
    return candidate_map


def __get_btc_tx_map_info(tx_id):
    data = BTC_STAKE.btcTxMap(tx_id)
    return data


def __get_delegator_btc_map(delegator):
    data = BTC_STAKE.getDelegatorBtcMap(delegator)
    return data


def __get_accured_reward_per_btc_map(validate, round_tag):
    data = BTC_STAKE.accuredRewardPerBTCMap(validate, round_tag)
    return data


def __check_accured_reward_per_btc(validate, round_tag, result: int):
    reward = __get_accured_reward_per_btc_map(validate, round_tag)
    assert reward == result


def __get_payable_notes_info(relayer):
    data = STAKE_HUB.payableNotes(relayer)
    return data


def __get_debts_notes_info(delegator):
    debts = STAKE_HUB.getDebts(delegator)
    return debts


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
