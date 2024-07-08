import brownie
import pytest
from brownie import *
from web3 import constants
from .calc_reward import set_delegate, parse_delegation
from .common import register_candidate, turn_round, get_current_round, set_last_round_tag, stake_hub_claim_reward, \
    claim_relayer_reward
from .utils import *

BLOCK_REWARD = 0
BTC_VALUE = 2000
FEE = 1
BTC_REWARD = 0
STAKE_ROUND = 3
# BTC delegation-related
PUBLIC_KEY = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
LOCK_TIME = 1736956800


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent):
    global BLOCK_REWARD, FEE, BTC_REWARD
    global BTC_STAKE, STAKE_HUB, CORE_AGENT
    FEE = FEE * Utils.CORE_DECIMAL
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    tx_fee = 100
    total_block_reward = block_reward + tx_fee
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    candidate_hub.setControlRoundTimeTag(True)
    btc_light_client.setCheckResult(True, LOCK_TIME)
    total_reward = BLOCK_REWARD // 2
    BTC_REWARD = total_reward * (HardCap.BTC_HARD_CAP * Utils.DENOMINATOR // HardCap.SUM_HARD_CAP) // Utils.DENOMINATOR
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


@pytest.fixture()
def delegate_btc_valid_tx():
    operator = accounts[5]
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operator, accounts[0], lock_data=lock_script)
    tx_id_list = [tx_id]
    return lock_script, btc_tx, tx_id_list


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
    claim_relayer_reward(accounts[1])
    assert tracker0.delta() == BTC_REWARD - FEE
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
    __check_debts_notes_info(accounts[0], [
        {
            'contributor': accounts[2],
            'amount': 100
        }
    ])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    stake_hub_claim_reward(accounts[0])
    __check_payable_notes_info(accounts[2], 100)

    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], btc_amount)]
    }], BLOCK_REWARD // 2)

    claim_relayer_reward(accounts[2])
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == FEE


def test_delegate_btc_success_public_key(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY, 'key')
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operators[0], accounts[0], 'key')
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
    assert tracker.delta() == BTC_REWARD - FEE


def test_delegate_btc_success_public_hash(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegated', {
        'txid': tx_id_list[0],
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
        'amount': BTC_VALUE
    })
    __check_receipt_map_info(tx_id_list[0], {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 1
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == BTC_REWARD - FEE


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
    assert tracker0.delta() == BTC_REWARD - FEE


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
    _, _, account_rewards, _, _ = parse_delegation(delegate_info, BLOCK_REWARD // 2)

    assert tracker.delta() == account_rewards[accounts[0]] - FEE


def test_delegate_btc_with_witness_transaction_key_script(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY, 'key')
    btc_tx = (
        "02000000015f6488617362efed9f022b8aa0ddb048607640232a118e684dea38a2141c4589020000006b483045022100b2ecc85951154d98a6134293bc1a1e294cb6df98f8c3dd78da8da9b88ffc4ba002205c919bfa76bbe5e0e102f85bb46db797bd046ae21a437ed7886e1c47eda228de01210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03780500"
        "00000000002200204fe5871daeae16742a2f56b616d7db1335f1a13637ddc4daa53cbd6b6ad397f7"
        "0000000000000000366a345341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "faaf0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    btc_amount = 1400
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
    assert tracker.delta() == __calculate_btc_only_rewards(btc_amount) - FEE


def test_invalid_lock_script(btc_stake, delegate_btc_valid_tx):
    _, btc_tx, tx_id_list = delegate_btc_valid_tx
    lock_script = "0380db8767b175210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    lock_script = "0480db8767b275210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_insufficient_lock_round_revert(btc_stake, set_candidate, delegate_btc_valid_tx):
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    set_last_round_tag(end_round)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    __set_last_round_tag(0)
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    __set_last_round_tag(STAKE_ROUND)
    tx = btc_stake.delegate(btc_tx, end_round, [], 0, lock_script)
    assert "delegated" in tx.events


def test_revert_on_duplicate_btc_tx_delegate(btc_stake, set_candidate, delegate_btc_valid_tx, btc_light_client):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_unconfirmed_btc_tx_delegate(btc_stake, btc_light_client, set_candidate, delegate_btc_valid_tx):
    btc_light_client.setCheckResult(False, 0)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("btc tx isn't confirmed"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


@pytest.mark.parametrize("btc_value", [1, 2, 100, 800, 1200, 99999999])
def test_btc_delegate_no_amount_limit(btc_stake, set_candidate, delegate_btc_valid_tx, btc_value):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id = __create_btc_delegate(operators[0], accounts[0], btc_value)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    assert "delegated" in tx.events
    turn_round(consensuses, round_count=2)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert "claimedReward" in tx.events
    assert tracker.delta() == __calculate_btc_only_rewards(btc_value) - FEE
    claim_relayer_reward(accounts[0])
    assert tracker.delta() == FEE


def test_revert_on_unequal_chain_id(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID - 1, operators[0], accounts[0])
    with brownie.reverts("wrong chain id"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_delegate_inactive_agent(btc_stake, set_candidate):
    lock_script, btc_tx, _ = __create_btc_delegate(accounts[1], accounts[0])
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    assert 'delegated' in tx.events


@pytest.mark.parametrize("output_view", [
    pytest.param("a6149ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_HASH160 error"),
    pytest.param("a9139ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_PUSHBYTES_20 error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791287", id="ScriptPubKey error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791386", id="OP_EQUAL error"),
    pytest.param("a9142d0a37f671e76a72f6dc30669ffaefa6120b798887", id="output error")
])
def test_revert_on_invalid_btc_tx_output(btc_stake, set_candidate, output_view):
    operators, consensuses = set_candidate
    lock_script, btc_tx, _ = __create_btc_delegate(operators[0], accounts[0], scrip_type='key')
    old_script_pub_key = output_script_pub_key['script_public_key']
    btc_tx = btc_tx.replace(old_script_pub_key, output_view)
    with brownie.reverts("staked value is zero"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


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


def test_revert_on_insufficient_payload_length(btc_stake, set_candidate, delegate_btc_valid_tx):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_tx = delegate_btc_block_data[
                 'witness_btc_tx_block_data'] + (
                 f"03b80b00"
                 f"0000000000220020aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a"
                 f"00000000000000002c6a2a0458ccf7e1dab7d90a0a91f8b1f6a693bf0bb3a979a09fb29aac15b9a4b7f17c3385939b007540f4d791"
                 "8e440100000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("payload length is too small"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_invalid_magic_value(btc_stake, set_candidate, delegate_btc_valid_tx):
    lock_script, _, _ = delegate_btc_valid_tx
    error_magic = '5341542c'
    btc_tx = delegate_btc_block_data[
                 'btc_tx_block_data'] + (
                 "03d00700000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
                 f"0000000000000000526a4c4f{error_magic}04589fb29aac15b9a4b7f17c3385939b007540f4d7911ef01e76f1aad50144a32680f16aa97a10f8af95010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88aca443"
                 "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("wrong magic"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_claim_rewards_from_multiple_validators(btc_stake, set_candidate):
    operators, consensuses = [], []
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    __set_last_round_tag(STAKE_ROUND)
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    sum_reward = 0
    for index, operator in enumerate(operators):
        btc_tx, tx_id = get_btc_tx(BTC_VALUE + index, Utils.CHAIN_ID, operator, accounts[0], lock_data=lock_script)
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
        amount = BTC_VALUE + index
        sum_reward += __calculate_btc_only_rewards(amount)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
    assert tracker0.delta() == sum_reward - FEE * 12
    assert tracker1.delta() == FEE * 12


def test_collect_porter_fee_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    btc_stake.delegate(btc_tx, round_tag, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    __check_payable_notes_info(accounts[1], 0)
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': 100}])
    stake_hub_claim_reward(accounts[0])
    __check_payable_notes_info(accounts[1], 100)
    __check_debts_notes_info(accounts[0], [])
    tx = claim_relayer_reward(accounts[1])
    expect_event(tx, 'claimedRelayerReward', {
        'relayer': accounts[1],
        'amount': FEE
    })
    turn_round(consensuses)
    assert tracker0.delta() == BTC_REWARD - FEE
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
    assert tracker1.delta() == FEE


def test_relay_fees_for_multiple_relays(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[0], accounts[0])
    tx_id_list.append(tx_id1)
    btc_stake.delegate(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    btc_stake.delegate(delegate_btc_tx1, round_tag, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    __check_payable_notes_info(accounts[1], 0)
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': 100},
                                           {'contributor': accounts[2], 'amount': 100}])
    stake_hub_claim_reward(accounts[0])
    __check_payable_notes_info(accounts[1], 100)
    __check_payable_notes_info(accounts[2], 100)
    __check_debts_notes_info(accounts[0], [])
    claim_relayer_reward(accounts[1:3])
    assert tracker0.delta() == BTC_REWARD - FEE * 2
    assert tracker1.delta() == FEE
    assert tracker2.delta() == FEE


def test_claim_rewards_and_deduct_porter_fees_after_transfer(btc_stake, set_candidate, delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id_list[0], operators[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == total_reward // 2
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:2])
    claim_relayer_reward(accounts[1])
    assert tracker1.delta() == total_reward + FEE


def test_transfer_with_nonexistent_stake_certificate(btc_stake, set_candidate, delegate_btc_valid_tx):
    tx_id = '0x8a2d192b0d0276fee31689693269e14aa9c78982c0d29ddf417a3064fd623892'
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    __set_last_round_tag(STAKE_ROUND)
    turn_round()
    with brownie.reverts("btc tx not found"):
        btc_stake.transfer(tx_id, operators[1])


def test_transfer_btc_to_current_validator(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    with brownie.reverts("can not transfer to the same validator"):
        btc_stake.transfer(tx_id_list[0], operators[0])


def test_transfer_btc_to_validator_with_lock_period_ending(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses, round_count=3)
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.transfer(tx_id_list[0], operators[1])
    turn_round(consensuses, round_count=1)
    __check_btc_tx_map_info(tx_id_list[0], {
        'amount': BTC_VALUE,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })
    __check_receipt_map_info(tx_id_list[0], {
        'candidate': operators[0],
        'delegator': accounts[0],
        'round': get_current_round() - 4
    })
    with brownie.reverts("insufficient locking rounds"):
        btc_stake.transfer(tx_id_list[0], operators[1])
    stake_hub_claim_reward(accounts[0])
    # after the lockout period expires, the recorded data will be reset to zero.
    __check_receipt_map_info(tx_id_list[0], {
        'candidate': constants.ADDRESS_ZERO,
        'delegator': constants.ADDRESS_ZERO,
        'round': 0
    })


def test_transfer_to_non_validator_target(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(2)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses)
    error_msg = encode_args_with_signature("InactiveCandidate(address)", [accounts[2].address])
    with brownie.reverts(f"{error_msg}"):
        btc_stake.transfer(tx_id_list[0], accounts[2])
    __check_candidate_map_info(operators[0], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE
    })
    __check_btc_tx_map_info(tx_id_list[0], {
        'amount': BTC_VALUE,
        'outputIndex': 0,
        'lockTime': LOCK_TIME,
        'usedHeight': 0,
    })


def test_transfer_btc_between_different_validators(btc_stake, core_agent, candidate_hub, set_candidate,
                                                   delegate_btc_valid_tx, btc_lst_stake):
    operators, consensuses = set_candidate
    end_round, _ = __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    tx_id = tx_id_list[0]
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id, operators[1])
    btc_stake.transfer(tx_id, operators[2])
    btc_stake.transfer(tx_id, operators[0])
    btc_stake.transfer(tx_id, operators[1])
    assert __get_delegator_btc_map(accounts[0])[0] == tx_id
    turn_round(consensuses, round_count=2)
    __check_btc_tx_map_info(tx_id, {})
    __check_receipt_map_info(tx_id, {})
    __check_candidate_map_info(operators[0], {})
    __check_candidate_map_info(operators[1], {})
    __check_candidate_map_info(operators[2], {})
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == __calculate_btc_only_rewards(BTC_VALUE) - FEE


def test_claim_rewards_with_insufficient_porter_funds(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    core_fee = 92
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    round_tag = get_current_round()
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operators[0], accounts[0],
                                         core_fee=core_fee)
    btc_stake.delegate(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': core_fee * FEE}])
    stake_hub_claim_reward(accounts[0])
    __check_payable_notes_info(accounts[1], BTC_REWARD)
    claim_relayer_reward(accounts[1])
    assert tracker0.delta() == 0
    assert tracker1.delta() == BTC_REWARD
    remain_fee = core_fee * FEE - BTC_REWARD
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': remain_fee}])
    __check_payable_notes_info(accounts[1], 0)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
    assert tracker1.delta() == BTC_REWARD
    remain_fee -= BTC_REWARD
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': remain_fee}])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    __check_payable_notes_info(accounts[1], remain_fee)
    claim_relayer_reward(accounts[1])
    assert tracker0.delta() == BTC_REWARD * 3 - core_fee * FEE
    assert tracker1.delta() == remain_fee


def test_deduct_porter_fees_for_multi_round_rewards_successfully(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    core_fee = 100
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    round_tag = get_current_round()
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operators[0], accounts[0], core_fee=core_fee)
    btc_stake.delegate(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
    assert tracker0.delta() == BTC_REWARD * 3 - core_fee * FEE
    assert tracker1.delta() == core_fee * FEE


def test_duplicate_transfer_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    tx = btc_stake.transfer(tx_id_list[0], operators[1])
    assert 'transferredBtc' in tx.events
    tx = btc_stake.transfer(tx_id_list[0], operators[2])
    assert 'transferredBtc' in tx.events
    tx = btc_stake.transfer(tx_id_list[0], operators[0])
    assert 'transferredBtc' in tx.events
    addr_list = btc_stake.getAgentAddrList(end_round)
    assert len(addr_list) == 3
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_revert_on_invalid_btc_transaction(btc_stake, set_candidate):
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    btc_tx = (delegate_btc_block_data['btc_tx_block_data'] +
              "03a9149ca26c6aa5a614836d041193ab7df1b6d650791387"
              "00000000000000002c6a2a045896c42c56fdb78294f96b0cfa33c92be"
              "d7d75f96a9fb29aac15b9a4b7f17c3385939b007540f4d7914e930100000000001976a914574fdd26858c28ede5225a809f747c"
              "01fcc1f92a88ac00000000")
    with brownie.reverts("BitcoinHelper: invalid tx"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_claim_btc_staking_rewards_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    btc_stake.delegate(btc_tx, round_tag, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    expect_event(tx, "claimedReward", {
        "delegator": accounts[0],
        "amount": __calculate_btc_only_rewards(BTC_VALUE) - FEE
    })
    assert tracker.delta() == __calculate_btc_only_rewards(BTC_VALUE) - FEE


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_claim_multi_round_btc_staking_rewards(btc_stake, set_candidate, internal):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[0])
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[1], accounts[0])
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses, round_count=internal)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    fee = 0
    if internal > 0:
        fee = FEE * 2
    assert tracker.delta() == BTC_REWARD * 2 * internal - fee
    claim_relayer_reward(accounts[0])
    assert tracker.delta() == fee


def test_distribute_rewards_to_multiple_addresses(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[1], accounts[1])
    _, delegate_btc_tx1, tx_id0 = __create_btc_delegate(operators[1], accounts[0])

    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == BTC_REWARD // 2 + FEE
    assert tracker1.delta() == BTC_REWARD - BTC_REWARD // 2 - FEE


def test_claim_rewards_for_multiple_coin_staking(btc_stake, core_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[1])
    _, delegate_btc_tx1, tx_id0 = __create_btc_delegate(operators[1], accounts[0])
    delegate_amount = 50000
    core_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    core_agent.delegateCoin(operators[1], {"value": delegate_amount // 2})
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    _, _, account_rewards, _, _ = parse_delegation([{
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


def test_unable_to_claim_rewards_after_end_round(btc_stake, set_candidate, delegate_btc_valid_tx):
    __set_last_round_tag(STAKE_ROUND)
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == BTC_REWARD * 3 - FEE
    __check_receipt_map_info(tx_id_list[0], {
        'candidate': constants.ADDRESS_ZERO,
        'delegator': constants.ADDRESS_ZERO,
        'round': 0,
    })
    turn_round(consensuses)
    #  Unable to claim, as the expired data is removed from the btcReceipt
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_single_validator_multiple_stakes(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_time1 = LOCK_TIME + Utils.ROUND_INTERVAL * 2
    lock_script1 = get_lock_script(lock_time1, PUBLIC_KEY)
    __set_last_round_tag(STAKE_ROUND)
    btc_amount0 = 3000
    btc_amount1 = 2500
    delegate_amount = 45000
    lock_script0, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[0], btc_amount0)
    delegate_btc_tx1 = (delegate_btc_block_data['witness_btc_tx_block_data']
                        + ("03c40900"
                           "000000000022002043c1a535b8941dbb2945ab932abb99995ffc7a5c3ea680b121ef9ca99b7dee45"
                           "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
                           "bcc00000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000"))
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script0)
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script1)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    _, _, account_rewards0, round_reward0, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount0 + btc_amount1)],
    }], BLOCK_REWARD // 2)
    turn_round(consensuses, round_count=6)
    _, _, account_rewards1, round_reward1, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount1)],
    }], BLOCK_REWARD // 2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    account_reward = (btc_amount0 + btc_amount1) * round_reward0[0]['btc'] / Utils.BTC_DECIMAL * 3 + btc_amount1 * \
                     round_reward1[0]['btc'] / Utils.BTC_DECIMAL * 2
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_reward


def test_no_rewards_generated_at_end_of_round(btc_stake, delegate_btc_valid_tx, set_candidate):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    end_round = LOCK_TIME // Utils.ROUND_INTERVAL
    __set_last_round_tag(STAKE_ROUND)
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
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
    lock_script1 = get_lock_script(lock_time1, PUBLIC_KEY)
    __set_last_round_tag(STAKE_ROUND)
    btc_amount0 = 3000
    btc_amount1 = 2500
    account0_btc = btc_amount0 + btc_amount1
    delegate_amount = 45000
    lock_script0, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[1], btc_amount0)
    delegate_btc_tx1 = delegate_btc_block_data[
                           'witness_btc_tx_block_data'] + ("03c40900"
                                                           "000000000022002043c1a535b8941dbb2945ab932abb99995ffc7a5c3ea680b121ef9ca99b7dee45"
                                                           "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
                                                           "722f0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    _, delegate_btc_tx2, tx_id2 = __create_btc_delegate(operators[0], accounts[0], btc_amount0)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script0)
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script1)
    btc_stake.delegate(delegate_btc_tx2, 0, [], 0, lock_script0)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    _, _, account_rewards0, round_reward0, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], account0_btc), set_delegate(accounts[1], btc_amount0)],
    }], BLOCK_REWARD // 2)
    _, _, account_rewards1, round_reward2, _ = parse_delegation([{
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
    reward0 = btc_amount0 * (round_reward0[0]['btc'] * 3) // Utils.BTC_DECIMAL + btc_amount1 * (
            round_reward0[0]['btc'] * 3) // Utils.BTC_DECIMAL + btc_amount1 * (
                      round_reward2[0]['btc'] * 2) // Utils.BTC_DECIMAL
    reward1 = account_rewards0[accounts[1]] * 3
    tx = claim_relayer_reward(accounts[0])
    expect_event(tx, 'claimedRelayerReward', {
        'relayer': accounts[0],
        'amount': FEE * 3
    })
    assert tracker0.delta() == int(reward0) + FEE
    assert tracker1.delta() == reward1 - FEE


def test_claim_rewards_for_multiple_stakes_to_different_validators(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 30000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[1], accounts[0])
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    CORE_AGENT.delegateCoin(operators[1], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == BTC_REWARD * 4


@pytest.mark.parametrize("btc_factor", [
    pytest.param(1, id="btc_factor is 1"),
    pytest.param(100, id="btc_factor is 100"),
    pytest.param(1000, id="btc_factor is 1000"),
    pytest.param(10000, id="btc_factor is 10000"),
    pytest.param(100000, id="btc_factor is 100000"),
    pytest.param(1000000, id="btc_factor is 1000000"),
])
def test_claim_rewards_after_modifying_btc_factor(btc_stake, set_candidate, stake_hub, delegate_btc_valid_tx,
                                                  btc_factor):
    stake_hub.setBtcFactor(btc_factor)
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 3e10
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    actual_reward0 = total_reward * BTC_VALUE * btc_factor // (delegate_amount + BTC_VALUE * btc_factor)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == actual_reward0


def test_claim_rewards_after_staking_every_other_round(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 300000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    btc_amount = 2500
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[0], accounts[0], btc_amount)
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], btc_amount), set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]


def test_transfer_btc_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    tx = btc_stake.transfer(tx_id_list[0], operators[1])
    CORE_AGENT.transferCoin(operators[0], operators[2], delegate_amount, {'from': accounts[1]})
    expect_event(tx, 'transferredBtc', {
        'txid': tx_id_list[0],
        'sourceCandidate': operators[0],
        'targetCandidate': operators[1],
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])

    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[1],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }, {
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": []
    }], BLOCK_REWARD // 2)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]] + total_reward // 2


def test_transfer_btc_when_no_rewards_in_current_round(btc_stake, set_candidate, delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id_list[0], operators[1])
    __check_receipt_map_info(tx_id_list[0], {
        'round': get_current_round()
    })
    __check_btc_tx_map_info(tx_id_list[0], {
        'lockTime': LOCK_TIME
    })
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[:2])
    assert tracker0.delta() == 0
    assert tracker1.delta() == total_reward // 2
    __check_candidate_map_info(operators[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0
    })
    __check_candidate_map_info(operators[1], {
        'stakedAmount': BTC_VALUE,
        'realtimeAmount': BTC_VALUE
    })


def test_revert_on_max_fee_exceeded(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    # fee range 1-255
    lock_script, delegate_btc_tx0, _ = __create_btc_delegate(operators[0], accounts[0], fee=256)
    with brownie.reverts("BitcoinHelper: invalid tx"):
        btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)


def test_claim_rewards_with_fee_deduction_success(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
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
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[0], fee=fee)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=7)
    tracker1 = get_tracker(accounts[1])
    __check_debts_notes_info(accounts[0], [{'contributor': accounts[1], 'amount': fee * FEE}])
    stake_hub_claim_reward(accounts[0])
    tx = claim_relayer_reward(accounts[1])
    expect_event(tx, 'claimedRelayerReward', {
        'relayer': accounts[1],
        'amount': fee * FEE
    })
    assert tracker1.delta() == fee * FEE


def test_success_with_zero_fee(btc_stake, set_candidate):
    fee = 0
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], accounts[0], fee=fee)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker1 = get_tracker(accounts[1])
    __check_debts_notes_info(accounts[0], [])
    stake_hub_claim_reward(accounts[0])
    tx = claim_relayer_reward(accounts[1])
    assert 'claimedRelayerReward' not in tx.events
    assert tracker1.delta() == 0


def test_insufficient_rewards_to_pay_porter_fee(btc_stake, set_candidate):
    fee = 100
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id = __create_btc_delegate(operators[0], accounts[0], fee=fee)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=1)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    tx = claim_relayer_reward(accounts[1])
    expect_event(tx, 'claimedRelayerReward', {
        'relayer': accounts[1],
        'amount': BTC_REWARD
    })
    assert tracker1.delta() == BTC_REWARD
    turn_round(consensuses, round_count=1)
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[1])
    assert tracker1.delta() == BTC_REWARD


@pytest.mark.parametrize("fee", [
    pytest.param(0, id="fee is 0"),
    pytest.param(1, id="fee is 1"),
    pytest.param(10, id="fee is 10"),
    pytest.param(50, id="fee is 50"),
    pytest.param(254, id="fee is 254"),
    pytest.param(255, id="fee is 255")
])
def test_claim_rewards_with_different_fees_after_transfer_success(btc_stake, set_candidate, fee):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id = __create_btc_delegate(operators[0], accounts[0], fee=fee)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id, operators[1])
    turn_round(consensuses, round_count=7)
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    tx = claim_relayer_reward(accounts[1])
    if fee > 0:
        expect_event(tx, 'claimedRelayerReward', {
            'relayer': accounts[1],
            'amount': fee * FEE
        })
    else:
        assert 'claimedRelayerReward' not in tx.events
    assert tracker1.delta() == fee * FEE


def test_multiple_btc_receipts_to_single_address(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[1], accounts[0])
    tx_id_list.append(tx_id1)
    btc_stake.delegate(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    btc_stake.delegate(delegate_btc_tx1, round_tag, [], 0, lock_script, {'from': accounts[2]})
    CORE_AGENT.delegateCoin(operators[2], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id_list[0], operators[2])
    btc_stake.transfer(tx_id_list[1], operators[2])
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])

    _, _, account_rewards, round_reward, _ = parse_delegation([{
        "address": operators[2],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE), set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    reward = BTC_VALUE * round_reward[0]['btc'] * 2 // Utils.BTC_DECIMAL * 2
    assert tracker0.delta() == reward - FEE * 2


def test_multiple_reward_transfers_in_multiple_rounds(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = [], []
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    __set_last_round_tag(STAKE_ROUND)
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    tx_id_list = []
    for index, operator in enumerate(operators):
        btc_tx, tx_id = get_btc_tx(BTC_VALUE + index, Utils.CHAIN_ID, operator, accounts[0],
                                   lock_data=lock_script)
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
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

        _, _, account_rewards, _, _ = parse_delegation([{
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
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == total_reward


def test_claiming_reward_by_non_owner_of_this_btc_receipt_reverts(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=1)
    tx = stake_hub_claim_reward(accounts[1])
    assert 'claimedReward' not in tx.events


def test_revert_on_incorrect_version(btc_stake, set_candidate):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operators[0], accounts[0], version=2)
    with brownie.reverts("unsupported sat+ version in btc staking"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script)


def test_revert_on_transaction_without_op_return(btc_stake):
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000102ae7f498ec542f8b2a70d3a5750058337a042b55b4130587a5271568921dc70020000006b483045022100f78b1eaacb6f10100015eca4618edea515d06d1a4ec432b2b669f4cbeed0dd1c02206c9137982f46c1129de1069b83987b1ad907314231077ac992a8e8990c92c8d401210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ffffffff"
        "02bc34"
        "000000000000220020f55d9bd2487756dd81b84946aab690e0e2e9b17c681a81c2d1ce22006395292b9b69"
        "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("no opreturn"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})


def test_modify_btc_factor_after_delegating_btc(btc_stake, stake_hub, btc_lst_stake, set_candidate,
                                                delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(stake_round=5)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_factor = 1
    stake_hub.setBtcFactor(btc_factor)
    _, delegate_btc_tx1, _ = __create_btc_delegate(operators[0], accounts[0])
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == BTC_REWARD
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[2], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE), set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2, btc_factor=1)

    assert tracker0.delta() == account_rewards[accounts[0]]


def test_stake_multiple_currencies_and_claim_rewards(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                     delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def test_claiming_btc_reward_with_multiple_power(btc_stake, candidate_hub, btc_light_client, set_candidate,
                                                 delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    delegate_amount = 40000
    turn_round()
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 1, operators[1], [accounts[3]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    CORE_AGENT.delegateCoin(operators[1], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    tracker3 = get_tracker(accounts[3])
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:4])
    _, _, account_rewards, _, _ = parse_delegation([{
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
def test_coin_transfer_with_power_and_btc_staking(btc_stake, btc_light_client, set_candidate, delegate_btc_valid_tx,
                                                  transfer_type):
    delegate_amount = 80000
    transfer_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
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
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)],
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]]


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelegate_with_power_and_btc_staking(btc_stake, set_candidate, btc_light_client, delegate_btc_valid_tx,
                                               undelegate_type):
    delegate_amount = 20000
    undelegate_amount = delegate_amount
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    if undelegate_type == 'part':
        undelegate_amount = 7000
    CORE_AGENT.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    turn_round(consensuses)
    _, _, account_rewards, _, _ = parse_delegation([{
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


def test_claiming_btc_reward_with_power_and_btc_staking(btc_stake, set_candidate, btc_light_client,
                                                        delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 6
    btc_light_client.setMiners(round_tag, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE), ]
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE


def test_operations_with_coin_power_and_btc_staking(btc_stake, set_candidate, btc_light_client,
                                                    delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    undelegate_amount = 7000
    transfer_amount = delegate_amount // 2
    CORE_AGENT.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[1]})
    CORE_AGENT.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    btc_stake.transfer(tx_id_list[0], operators[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    _, _, account_rewards, _, _ = parse_delegation([{
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
    _, _, account_rewards, _, _ = parse_delegation([{
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


def test_transfer_btc_reverts_for_non_delegator(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    with brownie.reverts("not the delegator of this btc receipt"):
        btc_stake.transfer(tx_id_list[0], operators[1], {'from': accounts[1]})
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_btc_transfer_does_not_claim_historical_rewards(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND * 2)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script)
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tx = btc_stake.transfer(tx_id_list[0], operators[1], {'from': accounts[0]})
    assert 'claimedReward' not in tx.events
    assert tracker0.delta() == 0


def test_transfer_btc_to_existing_btc_staker(btc_stake, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[1], accounts[1])
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    CORE_AGENT.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_stake.transfer(tx_id_list[0], operators[1], {'from': accounts[0]})
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
    _, _, account_rewards, _, _ = parse_delegation([{
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
    assert tracker0.delta() == account_rewards[accounts[0]] - FEE
    assert tracker1.delta() == account_rewards[accounts[1]] + BLOCK_REWARD // 4 * 2 - FEE
    __check_candidate_map_info(operators[0], {
        'stakedAmount': 0,
        'realtimeAmount': 0
    })


def test_transfer_btc_from_multiple_btc_stakings(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND * 2)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(operators[0], accounts[0])
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    btc_stake.transfer(tx_id_list[0], operators[1], {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE * 2)]
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] // 2 - FEE * 2


def test_btc_transfer_from_non_validator_account(btc_stake, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND * 2)
    lock_script, _, tx_id_list = delegate_btc_valid_tx
    _, delegate_btc_tx1, tx_id1 = __create_btc_delegate(accounts[3], accounts[0])
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    btc_stake.transfer(tx_id1, operators[1], {'from': accounts[0]})
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' in tx.events

    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)

    assert tracker0.delta() == account_rewards[accounts[0]] - FEE


def test_multiple_btc_stakings_in_vout(btc_stake, set_candidate):
    btc_amount = 53820
    lock_script = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
    operators, consensuses = set_candidate
    btc_tx = (
        "0200000001dd94cb72979c528593cb1188f4e3bf43a52f5570edab981e3d303ff24166afe5000000006b483045022100f2f069e37929cdfafffa79dcc1cf478504875fbe2a41704a96aee88ec604c0e502207259c56c67de8de6bb8c15e9d14b6ad16acd86d6a834fbb0531fd27bee7e5e3301210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03b80b00"
        "000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        "0000000000000000536a4c505341542b0104589fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "3cd200000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb68700000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'candidate': operators[0],
        'delegator': accounts[0],
        'script': '0x' + lock_script,
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
    assert tracker0.delta() == __calculate_btc_only_rewards(btc_amount) - FEE
    claim_relayer_reward(accounts[2])
    assert tracker1.delta() == FEE


def test_claim_reward_reentry(btc_stake, set_candidate, stake_hub):
    btc_stake_proxy = ClaimBtcRewardReentry.deploy(btc_stake.address, stake_hub.address, {'from': accounts[0]})
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, delegate_btc_tx0, tx_id0 = __create_btc_delegate(operators[0], btc_stake_proxy.address, BTC_VALUE // 2)
    _, delegate_btc_tx1, _ = __create_btc_delegate(operators[0], accounts[0], BTC_VALUE * 2)
    btc_stake.delegate(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    btc_stake.delegate(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    CORE_AGENT.delegateCoin(operators[0], {"value": 20000, "from": accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(btc_stake_proxy)
    rewards, debt_amount = stake_hub.claimReward.call({'from': btc_stake_proxy})
    tx = btc_stake_proxy.claimReward()
    expect_event(tx, "proxyClaim", {
        "success": True})
    assert tracker.delta() == rewards[2] - FEE


def test_claiming_rewards_with_multiple_staking_types(btc_stake, candidate_hub, set_candidate, btc_light_client,
                                                      delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    turn_round()
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[1], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    btc_stake.transfer(tx_id_list[0], operators[1], {'from': accounts[0]})
    turn_round(consensuses)

    _, _, account_rewards, _, _ = parse_delegation([{
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
                                                   set_candidate, delegate_btc_valid_tx):
    block_times_tamp = 1723122315
    chain.mine(timestamp=block_times_tamp)
    candidate_hub.setControlRoundTimeTag(False)
    __set_last_round_tag(2, block_times_tamp)
    turn_round()
    block_time = block_times_tamp
    operators, consensuses = set_candidate
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, _ = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
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
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [set_delegate(accounts[2], 1)],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]
    chain.mine(timestamp=block_time + Utils.ROUND_INTERVAL * 4)
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[:3])
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD // 2)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == 0


def test_btc_stake_expiry_after_turn_round_failure(btc_stake, candidate_hub, btc_light_client,
                                                   set_candidate, delegate_btc_valid_tx):
    __set_last_round_tag(1, LOCK_TIME)
    chain_time = LOCK_TIME - Utils.ROUND_INTERVAL
    candidate_hub.setControlRoundTimeTag(False)
    operators, consensuses = set_candidate
    delegate_amount = 20000
    CORE_AGENT.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script)
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
    _, _, account_rewards, _, _ = parse_delegation([{
        "address": operators[0],
        "active": True,
        "power": [],
        "coin": [set_delegate(accounts[1], delegate_amount)],
        "btc": [set_delegate(accounts[0], BTC_VALUE)]
    }], BLOCK_REWARD)
    claim_relayer_reward(accounts[0])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    chain.mine(timestamp=chain_time + Utils.ROUND_INTERVAL * 4)
    turn_round(consensuses)
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' not in tx.events


def test_restaking_after_btc_staking_expiry(btc_stake, candidate_hub, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    __set_last_round_tag(STAKE_ROUND)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses, round_count=4)
    stake_hub_claim_reward(accounts[0])
    with brownie.reverts("btc tx is already delegated."):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


@pytest.mark.parametrize("round", [0, 1, 2, 3, 4])
def test_delegate_after_fixed_lock_time_different_rounds(btc_stake, candidate_hub, set_candidate, delegate_btc_valid_tx, round):
    operators, consensuses = set_candidate
    __set_last_round_tag(3)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    turn_round()
    turn_round(consensuses, round_count=round)
    if round <= 1:
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    else:
        with brownie.reverts("insufficient locking rounds"):
            btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


@pytest.mark.parametrize("key,value", [('gradeActive', 0)])
def test_update_param_success(btc_stake, gov_hub, key, value):
    hex_value = padding_left(Web3.to_hex(int(value)), 64)
    tx = btc_stake.updateParam(key, hex_value, {'from': gov_hub.address})
    expect_event(tx, 'paramChange', {
        'key': key,
        'value': hex_value
    })
    if key == 'gradeActive':
        assert btc_stake.gradeActive() == value


@pytest.mark.parametrize("key", ['gradeActive'])
def test_update_param_failed(btc_stake, gov_hub, key):
    hex_value = padding_left(Web3.to_hex(0), 64)
    uint256_max = 2 ** 256 - 1
    lower_bound = 1
    value = 1
    if key == 'gradeActive':
        lower_bound = 0
        uint256_max = 1
        value = 2
        hex_value = padding_left(Web3.to_hex(2), 64)
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        [key, value, lower_bound, uint256_max]
    )
    with brownie.reverts(f"{error_msg}"):
        btc_stake.updateParam(key, hex_value, {'from': gov_hub.address})


def test_update_param_failed_non_governance_contract(btc_stake):
    hex_value = padding_left(Web3.to_hex(0), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        btc_stake.updateParam('isActive', hex_value, {'from': accounts[0]})


def test_init_required_before_governance_functions(btc_stake):
    btc_stake.setAlreadyInit(False)
    hex_value = padding_left(Web3.to_hex(0), 64)
    with brownie.reverts("the contract not init yet"):
        btc_stake.updateParam('isActive', hex_value, {'from': accounts[0]})


def test_delegator_calling_delegate_btc(btc_stake, delegate_btc_valid_tx, set_candidate, relay_hub):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    relay_hub.setRelayerRegister(accounts[0], False)
    assert relay_hub.isRelayer(accounts[0]) is False
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    assert 'delegated' in tx.events


def test_revert_for_non_delegator_or_relayer_calling_delegate_btc(btc_stake, delegate_btc_valid_tx, relay_hub,
                                                                  set_candidate):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    relay_hub.setRelayerRegister(accounts[1], False)
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


def test_successful_delegate_btc_call_by_relayer(btc_stake, delegate_btc_valid_tx, relay_hub,
                                                 set_candidate):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    relay_hub.setRelayerRegister(accounts[5], True)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    assert 'delegated' in tx.events


def test_small_amount_btc_stake(btc_stake, candidate_hub, set_candidate, delegate_btc_valid_tx):
    lock_script, _, tx_id_list = delegate_btc_valid_tx
    operators, consensuses = set_candidate
    btc_tx, tx_id = get_btc_tx(1, Utils.CHAIN_ID, operators[0], accounts[0], lock_data=lock_script)
    tx = btc_stake.delegate(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    assert 'claimedReward' not in tx.events


def __create_btc_delegate(candidate, account, amount=None, fee=1, scrip_type='hash'):
    lock_script = get_lock_script(LOCK_TIME, PUBLIC_KEY, scrip_type)
    if amount is None:
        amount = BTC_VALUE
    btc_tx, tx_id = get_btc_tx(amount, Utils.CHAIN_ID, candidate, account, scrip_type, LOCK_TIME, core_fee=fee)
    return lock_script, btc_tx, tx_id


def __set_last_round_tag(stake_round, time0=None):
    if time0 is None:
        time0 = LOCK_TIME
    end_round0 = time0 // Utils.ROUND_INTERVAL
    current_round = end_round0 - stake_round - 1
    CandidateHubMock[0].setRoundTag(current_round)
    BTC_STAKE.setRoundTag(current_round)
    BitcoinLSTStakeMock[0].setInitRound(current_round)
    return end_round0, current_round


def __calculate_btc_only_rewards(total_btc, claim_btc=None, validator_score=None, btc_factor=10, total_reward=None):
    collateral_state_btc = HardCap.BTC_HARD_CAP * Utils.DENOMINATOR // HardCap.SUM_HARD_CAP
    if total_reward is None:
        total_reward = BLOCK_REWARD // 2
    if validator_score is None:
        validator_score = total_btc
    if claim_btc is None:
        claim_btc = total_btc
    reward = total_reward * (total_btc * btc_factor) // (
            validator_score * btc_factor) * collateral_state_btc // Utils.DENOMINATOR
    reward1 = reward * Utils.BTC_DECIMAL // total_btc
    reward2 = reward1 * claim_btc // Utils.BTC_DECIMAL
    return reward2


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


def __get_accured_reward_per_btc_map(validate, round):
    data = BTC_STAKE.accuredRewardPerBTCMap(validate, round)


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


def __check_debts_notes_info(delegator, result: list):
    data = __get_debts_notes_info(delegator)
    if len(result) == 0 and len(data) == 0:
        return
    for index, r in enumerate(result):
        for i, c in enumerate(r):
            assert data[index][i] == r[c]


def __check_payable_notes_info(relayer, amount):
    data = __get_payable_notes_info(relayer)
    assert data == amount


def __check_btc_tx_map_info(tx_id, result: dict):
    data = __get_btc_tx_map_info(tx_id)
    for i in result:
        assert data[i] == result[i]
