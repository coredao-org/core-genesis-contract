import time

import brownie
import pytest
from brownie.network import gas_price
from web3 import Web3
from brownie import accounts, TransferBtcReentry, ClaimBtcRewardReentry
from .btc_block_data import *
from .common import register_candidate, turn_round, get_current_round, set_last_round_tag
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
BLOCK_REWARD = 0
ROUND_INTERVAL = 86400
BTC_VALUE = 2000
btcFactor = 0
MIN_BTC_LOCK_ROUND = 0
BTC_AMOUNT = 0
ONE_ETHER = Web3.toWei(1, 'ether')
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
TX_FEE = 100
public_key = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
lock_time = 1736956800
chain_id = 1116
lock_script_type = 'hash'
FEE = 1


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-2].transfer(validator_set.address, Web3.toWei(100000, 'ether'))
    accounts[-2].transfer(gov_hub.address, Web3.toWei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, pledge_agent):
    global BLOCK_REWARD, btcFactor, MIN_BTC_LOCK_ROUND, FEE, BTC_AMOUNT
    FEE = 1 * pledge_agent.FEE_FACTOR()
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    btcFactor = pledge_agent.btcFactor() * pledge_agent.BTC_UNIT_CONVERSION()
    BTC_AMOUNT = BTC_VALUE * btcFactor
    MIN_BTC_LOCK_ROUND = pledge_agent.minBtcLockRound()
    candidate_hub.setControlRoundTimeTag(True)
    btc_light_client.setCheckResult(True)


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
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, chain_id, operator, accounts[0], lock_script_type, lock_script)
    tx_id_list = [tx_id]
    return lock_script, btc_tx, tx_id_list


def test_delegate_btc_with_lock_time_in_tx(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    btc_amount = BTC_VALUE
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000188f5ba21514a0c32cbf90baab2b48feeeb0f200bfe7388730d80bf7f78ad27cd020000006a473044022066314a4e78bda5f9cb448d867ef3e8ef0678f7e0865f188e5cb362f5b40aed5c02203df085a6f742129a78729e8ca710a3065eb13cc01cb175457f947cbb6f3f89c701210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff02d007"
        "00000000000017a914f8f68b9543eaf5a9306090fde09ac765e1412e4587"
        "0000000000000000366a345341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "00000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = pledge_agent.delegateBtc(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    expect_event(tx, 'delegatedBtc', {
        'txid': tx_id,
        'script': '0x' + lock_script,
        'blockHeight': 1,
        'outputIndex': 0

    })
    turn_round()
    agent_map = pledge_agent.agentsMap(operators[0])
    assert pledge_agent.btcReceiptMap(tx_id)['value'] == BTC_VALUE
    assert agent_map['totalBtc'] == btc_amount
    turn_round(consensuses)
    expect_query(pledge_agent.btcReceiptMap(tx_id), {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': btc_amount,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[1],
        'fee': FEE
    })
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward([tx_id])
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE
    assert tracker1.delta() == FEE


def test_delegate_btc_with_lock_script_in_tx(pledge_agent, set_candidate):
    btc_amount = BTC_VALUE * 3 // 2
    lock_script = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
    operators, consensuses = set_candidate
    btc_tx = (
        "0200000001dd94cb72979c528593cb1188f4e3bf43a52f5570edab981e3d303ff24166afe5000000006b483045022100f2f069e37929cdfafffa79dcc1cf478504875fbe2a41704a96aee88ec604c0e502207259c56c67de8de6bb8c15e9d14b6ad16acd86d6a834fbb0531fd27bee7e5e3301210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03b80b00"
        "000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "3cd20000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'txid': tx_id,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'outputIndex': 0
    })
    agent_map = pledge_agent.agentsMap(operators[0])
    expect_query(pledge_agent.btcReceiptMap(tx_id), {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': btc_amount,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[2],
        'fee': FEE
    })
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    pledge_agent.claimBtcReward([tx_id])
    assert agent_map['totalBtc'] == btc_amount
    assert pledge_agent.btcReceiptMap(tx_id)['value'] == btc_amount
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE
    assert tracker1.delta() == FEE


def test_delegate_btc_success_public_key(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(lock_time, public_key, 'key')
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], 'key')
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'outputIndex': 0,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'txid': tx_id,
    })
    agent_map = pledge_agent.agentsMap(operators[0])
    expect_query(pledge_agent.btcReceiptMap(tx_id), {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': BTC_VALUE,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[0],
        'fee': FEE
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward([tx_id])
    assert agent_map['totalBtc'] == BTC_VALUE
    assert "claimedReward" in tx.events
    assert tracker.delta() == BLOCK_REWARD // 2


def test_delegate_btc_success_public_hash(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'outputIndex': 0,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'txid': tx_id_list[0],
    })

    agent_map = pledge_agent.agentsMap(operators[0])
    expect_query(pledge_agent.btcReceiptMap(tx_id_list[0]), {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': BTC_VALUE,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[0],
        'fee': FEE
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert agent_map['totalBtc'] == BTC_VALUE
    assert "claimedReward" in tx.events
    assert tracker.delta() == BLOCK_REWARD // 2


def test_delegate_btc_success_multi_sig_script(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000188f5ba21514a0c32cbf90baab2b48feeeb0f200bfe7388730d80bf7f78ad27cd020000006a473044022066314a4e78bda5f9cb448d867ef3e8ef0678f7e0865f188e5cb362f5b40aed5c02203df085a6f742129a78729e8ca710a3065eb13cc01cb175457f947cbb6f3f89c701210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff02d007"
        "00000000000017a914f8f68b9543eaf5a9306090fde09ac765e1412e4587"
        "0000000000000000366a345341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "00000000")
    tx_id = get_transaction_txid(btc_tx)
    pledge_agent.delegateBtc(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward([tx_id])
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE


def test_delegate_btc_with_witness_transaction_hash_script(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = '0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac'
    btc_tx = (
        "0200000001ac5d10fc2c7fde4aa105a740e0ae00dafa66a87f472d0395e71c4d70c4d698ba020000006b4830450221009b0f6b1f2cdb0125f166245064d18f026dc77777a657b83d6f56c79101c269b902206c84550b64755ec2eba1893e81b22a57350b003aa5a3a8915ac7c2eb905a1b7501210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03140500"
        "0000000000220020aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a"
        "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "bcc00000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    btc_amount = 1300
    tx_id = get_transaction_txid(btc_tx)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'outputIndex': 0,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'txid': tx_id,
    })
    agent_map = pledge_agent.agentsMap(operators[0])
    btc_delegator = pledge_agent.btcReceiptMap(tx_id)
    expect_query(btc_delegator, {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': btc_amount,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[0],
        'fee': FEE
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward([tx_id])
    assert "claimedReward" in tx.events
    assert agent_map['totalBtc'] == btc_amount
    assert tracker.delta() == BLOCK_REWARD // 2


def test_delegate_btc_with_witness_transaction_key_script(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(lock_time, public_key, 'key')
    btc_tx = (
        "02000000015f6488617362efed9f022b8aa0ddb048607640232a118e684dea38a2141c45c9020000006b483045022100b2ecc85951154d98a6134293bc1a1e294cb6df98f8c3dd78da8da9b88ffc4ba002205c919bfa76bbe5e0e102f85bb46db797bd046ae21a437ed7886e1c47eda228de01210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03780500"
        "00000000002200204fe5871daeae16742a2f56b616d7db1335f1a13637ddc4daa53cbd6b6ad397f7"
        "0000000000000000366a345341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a00180db8767"
        "faaf0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    btc_amount = 1400
    tx_id = get_transaction_txid(btc_tx)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'outputIndex': 0,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'txid': tx_id,
    })
    btc_delegator = pledge_agent.btcReceiptMap(tx_id)
    expect_query(btc_delegator, {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': btc_amount,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[0],
        'fee': FEE
    })

    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward([tx_id])
    assert "claimedReward" in tx.events
    assert tracker.delta() == BLOCK_REWARD // 2


def test_invalid_lock_script(pledge_agent, delegate_btc_valid_tx):
    _, btc_tx, tx_id_list = delegate_btc_valid_tx
    lock_script = "0380db8767b175210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    lock_script = "0480db8767b275210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ac"
    with brownie.reverts("not a valid redeem script"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_insufficient_lock_round_revert(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("insufficient lock round"):
        pledge_agent.delegateBtc(btc_tx, end_round, [], 0, lock_script)
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND)
    with brownie.reverts("insufficient lock round"):
        pledge_agent.delegateBtc(btc_tx, end_round, [], 0, lock_script)
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    tx = pledge_agent.delegateBtc(btc_tx, end_round, [], 0, lock_script)
    assert "delegatedBtc" in tx.events


def test_revert_on_duplicate_btc_tx_delegate(pledge_agent, set_candidate, delegate_btc_valid_tx):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    with brownie.reverts("btc tx confirmed"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_unconfirmed_btc_tx_delegate(pledge_agent, btc_light_client, set_candidate, delegate_btc_valid_tx):
    btc_light_client.setCheckResult(False)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("btc tx not confirmed"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_insufficient_btc_amount_delegate(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    btc_amount = 999
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx, tx_id = get_btc_tx(btc_amount, chain_id, operators[0], accounts[0])
    with brownie.reverts("staked value does not meet requirement"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    btc_tx, tx_id = get_btc_tx(btc_amount + 1, chain_id, operators[0], accounts[0])
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    assert "delegatedBtc" in tx.events
    btc_tx, tx_id = get_btc_tx(btc_amount + 2, chain_id, operators[0], accounts[0])
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    assert "delegatedBtc" in tx.events


def test_revert_on_unequal_chain_id(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, chain_id - 1, operators[0], accounts[0], lock_script_type)
    with brownie.reverts("wrong chain id"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_delegate_inactive_agent(pledge_agent, set_candidate):
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx, _ = get_btc_tx(BTC_VALUE, chain_id, accounts[1], accounts[0], lock_script_type)
    error_msg = encode_args_with_signature('InactiveAgent(address)', [accounts[1].address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


@pytest.mark.parametrize("output_view", [
    pytest.param("a6149ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_HASH160 error"),
    pytest.param("a9139ca26c6aa5a614836d041193ab7df1b6d650791387", id="OP_PUSHBYTES_20 error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791287", id="ScriptPubKey error"),
    pytest.param("a9149ca26c6aa5a614836d041193ab7df1b6d650791386", id="OP_EQUAL error"),
    pytest.param("a9142d0a37f671e76a72f6dc30669ffaefa6120b798887", id="output error")
])
def test_revert_on_invalid_btc_tx_output(pledge_agent, set_candidate, delegate_btc_valid_tx, output_view):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_tx = delegate_btc_block_data['btc_tx_block_data'] + (
        f"03b80b00"
        f"000000000017{output_view}"
        f"0000000000000000356a335341542b04589fb29aac15b9a4b7f17c3385939b007540f4d7911ef01e76f1aad50144a32680f16aa97a10f8af950180db8767"
        f"89130000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("staked value does not meet requirement"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


@pytest.mark.parametrize("output_view", [
    pytest.param("0120aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a", id="OP_0 error"),
    pytest.param("0021aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a", id="OP_PUSHBYTES_32 error"),
    pytest.param("0020aee9137b4958e35085907caaa2d5a9e659b0b1036e06f04280e2e98520f7f16c", id="ScriptPubKey error")
])
def test_revert_on_invalid_witness_btc_tx_output(pledge_agent, set_candidate, delegate_btc_valid_tx, output_view):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_tx = delegate_btc_block_data[
                 'witness_btc_tx_block_data'] + (
                 f"03b80b00000000000022{output_view}"
                 f"0000000000000000356a335341542b04589fb29aac15b9a4b7f17c3385939b007540f4d7911ef01e76f1aad50144a32680f16aa97a10f8af950180db8767"
                 "8e440100000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("staked value does not meet requirement"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_insufficient_payload_length(pledge_agent, set_candidate, delegate_btc_valid_tx):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    btc_tx = delegate_btc_block_data[
                 'witness_btc_tx_block_data'] + (
                 f"03b80b00"
                 f"0000000000220020aee9137b4958e35085907caaa2d5a9e659b0b1037e06f04280e2e98520f7f16a"
                 f"00000000000000002c6a2a045cccf7e1dab7d90a0a91f8b1f6a693bf0bb3a979a09fb29aac15b9a4b7f17c3385939b007540f4d791"
                 "8e440100000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("payload length is too small"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_invalid_magic_value(pledge_agent, set_candidate, delegate_btc_valid_tx):
    lock_script, _, _ = delegate_btc_valid_tx
    btc_tx = delegate_btc_block_data[
                 'btc_tx_block_data'] + (
                 "03d00700000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
                 "0000000000000000526a4c4f5341542c04589fb29aac15b9a4b7f17c3385939b007540f4d7911ef01e76f1aad50144a32680f16aa97a10f8af95010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88aca443"
                 "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("wrong magic"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_claim_rewards_with_max_delegate_btc(pledge_agent, set_candidate):
    operators, consensuses = [], []
    pledge_agent.setClaimRoundLimit(10)
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    tx_id_list = []
    for index, operator in enumerate(operators):
        btc_tx, tx_id = get_btc_tx(BTC_VALUE + index, chain_id, operator, accounts[0], lock_script_type, lock_script)
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
        tx_id_list.append(tx_id)
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list)
    start_index = 0
    for i in range(3):
        del tx_id_list[0]
        start_index += 1
    assert tracker0.delta() == BLOCK_REWARD // 2 * 10 - FEE * 4
    assert tracker1.delta() == FEE * 4
    last_voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    expect_query(last_voucher, {'agent': operators[start_index], 'rewardIndex': 1, 'value': BTC_VALUE + start_index})
    pledge_agent.claimBtcReward(tx_id_list)
    for i in range(3):
        del tx_id_list[0]
        start_index += 1
    last_voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    expect_query(last_voucher, {'agent': operators[start_index], 'rewardIndex': 2, 'value': BTC_VALUE + start_index})
    pledge_agent.claimBtcReward(tx_id_list)
    for i in range(4):
        del tx_id_list[0]
        start_index += 1
    last_voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    expect_query(last_voucher, {'agent': operators[start_index], 'rewardIndex': 0, 'value': BTC_VALUE + start_index})
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == BLOCK_REWARD // 2 * 26 - FEE * 8
    assert tracker1.delta() == FEE * 8


def test_claim_rewards_with_max_claim_limit(pledge_agent, delegate_btc_valid_tx):
    operators, consensuses = [], []
    pledge_agent.setClaimRoundLimit(2)
    for operator in accounts[5:9]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE + 1, chain_id, operators[1], accounts[0], lock_script_type,
                                          lock_script)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[1]})
    tx_id_list.append(tx_id1)
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['rewardIndex'] == 2
    assert pledge_agent.btcReceiptMap(tx_id1)['rewardIndex'] == 0
    turn_round(consensuses, round_count=1)
    pledge_agent.setClaimRoundLimit(4)
    pledge_agent.claimBtcReward(tx_id_list)
    turn_round(consensuses, round_count=1)
    assert tracker0.delta() == BLOCK_REWARD * 3 - FEE * 2
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['agent'] == ZERO_ADDRESS
    assert pledge_agent.btcReceiptMap(tx_id1)['agent'] == ZERO_ADDRESS


def test_collect_porter_fee_success(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    tx_id = tx_id_list[0]
    round_tag = get_current_round()
    pledge_agent.delegateBtc(btc_tx, round_tag, [], 0, lock_script, {'from': accounts[1]})
    btc_delegator = pledge_agent.btcReceiptMap(tx_id)
    expect_query(btc_delegator, {
        'feeReceiver': accounts[1],
        'fee': FEE
    })
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    expect_event(tx, "transferredBtcFee", {
        "txid": tx_id_list[0],
        "feeReceiver": accounts[1],
        "fee": FEE
    })
    assert pledge_agent.btcReceiptMap(tx_id)['fee'] == 0
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert 'transferredBtcFee' not in tx.events
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE
    assert tracker1.delta() == FEE


def test_deduct_multiple_porter_fees_when_claiming_rewards(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    tx_id0 = tx_id_list[0]
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type)
    tx_id_list.append(tx_id1)
    pledge_agent.delegateBtc(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    pledge_agent.delegateBtc(delegate_btc_tx1, round_tag, [], 0, lock_script, {'from': accounts[2]})
    btc_delegator0 = pledge_agent.btcReceiptMap(tx_id0)
    btc_delegator1 = pledge_agent.btcReceiptMap(tx_id1)
    expect_query(btc_delegator0, {
        'feeReceiver': accounts[1],
        'fee': FEE
    })
    expect_query(btc_delegator1, {
        'feeReceiver': accounts[2],
        'fee': FEE
    })
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert "claimedReward" in tx.events
    expect_event(tx, "transferredBtcFee", {
        "txid": tx_id0,
        "feeReceiver": accounts[1],
        "fee": FEE
    }, idx=0)
    expect_event(tx, "transferredBtcFee", {
        "txid": tx_id1,
        "feeReceiver": accounts[2],
        "fee": FEE
    }, idx=1)
    assert pledge_agent.btcReceiptMap(tx_id0)['fee'] == pledge_agent.btcReceiptMap(tx_id1)['fee'] == 0
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE * 2
    assert tracker1.delta() == FEE
    assert tracker2.delta() == FEE


def test_claim_rewards_and_deduct_porter_fees_after_transfer(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    assert pledge_agent.btcReceiptMap(tx_id_list[0])["endRound"] == end_round
    pledge_agent.transferBtc(tx_id_list[0], operators[1])
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list)
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == 0
    assert tracker1.delta() == total_reward - total_reward // 2
    assert pledge_agent.btcReceiptMap(tx_id_list[0])["fee"] == FEE
    turn_round(consensuses)
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == total_reward - FEE
    assert tracker1.delta() == total_reward + FEE


def test_transfer_with_nonexistent_stake_certificate(pledge_agent, set_candidate, delegate_btc_valid_tx):
    tx_id = '0x8a2d192b0d0276fee31689693269e14aa9c78982c0d29ddf417a3064fd623892'
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    turn_round()
    with brownie.reverts("btc tx not found"):
        pledge_agent.transferBtc(tx_id, operators[1])


def test_transfer_btc_to_current_validator(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    with brownie.reverts("can not transfer to the same validator"):
        pledge_agent.transferBtc(tx_id_list[0], operators[0])


def test_transfer_btc_to_validator_with_lock_period_ending(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses, round_count=3)
    with brownie.reverts("insufficient locking rounds"):
        pledge_agent.transferBtc(tx_id_list[0], operators[1])
    turn_round(consensuses, round_count=1)
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['agent'] == operators[0]
    with brownie.reverts("insufficient locking rounds"):
        pledge_agent.transferBtc(tx_id_list[0], operators[1])
    pledge_agent.claimBtcReward(tx_id_list)
    # after the lockout period expires, the recorded data will be reset to zero.
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['agent'] == ZERO_ADDRESS


def test_transfer_to_non_validator_target(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses)
    error_msg = encode_args_with_signature("InactiveAgent(address)", [accounts[2].address])
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.transferBtc(tx_id_list[0], accounts[2])
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['value'] == BTC_VALUE


def test_transfer_btc_between_different_validators(pledge_agent, candidate_hub, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    tx_id = tx_id_list[0]
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    pledge_agent.transferBtc(tx_id, operators[1])
    pledge_agent.transferBtc(tx_id, operators[2])
    pledge_agent.transferBtc(tx_id, operators[0])
    pledge_agent.transferBtc(tx_id, operators[1])
    addr_list = pledge_agent.getAgentAddrList(end_round)
    for index, addr in enumerate(addr_list):
        assert addr == operators[index]
    assert len(addr_list) == 3
    assert pledge_agent.getReward(operators[0], 0)[3] == 0
    turn_round(consensuses, round_count=2)
    tx = pledge_agent.claimBtcReward(tx_id_list)
    expect_event(tx, "claimedReward", {
        "amount": BLOCK_REWARD // 2 - FEE,
        "success": True
    })
    assert pledge_agent.btcReceiptMap(tx_id)['agent'] == operators[1]
    turn_round(consensuses)
    tx = pledge_agent.claimBtcReward(tx_id_list)
    expect_event(tx, "claimedReward", {
        "amount": BLOCK_REWARD // 2,
    })


def test_claim_rewards_with_insufficient_porter_funds(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    core_fee = 136
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    round_tag = get_current_round()
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type,
                                         core_fee=core_fee)
    pledge_agent.delegateBtc(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward([tx_id])
    voucher = pledge_agent.btcReceiptMap(tx_id)
    expect_event(tx, "transferredBtcFee", {
        "txid": tx_id,
        "feeReceiver": accounts[1],
        "fee": BLOCK_REWARD // 2
    })
    remain_fee = FEE * core_fee - BLOCK_REWARD // 2
    assert voucher['fee'] == remain_fee
    assert "claimedReward" not in tx.events
    assert tracker0.delta() == 0
    assert tracker1.delta() == BLOCK_REWARD // 2
    turn_round(consensuses)
    pledge_agent.claimBtcReward([tx_id])
    assert tracker0.delta() == BLOCK_REWARD // 2 - remain_fee
    assert tracker1.delta() == remain_fee


def test_deduct_porter_fees_for_multi_round_rewards_successfully(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    core_fee = 255
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    round_tag = get_current_round()
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type, core_fee=255)
    pledge_agent.delegateBtc(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward([tx_id])
    expect_event(tx, "transferredBtcFee", {
        "txid": tx_id,
        "feeReceiver": accounts[1],
        "fee": FEE * core_fee
    })
    voucher = pledge_agent.btcReceiptMap(tx_id)
    assert voucher['fee'] == 0
    assert "claimedReward" in tx.events
    assert tracker0.delta() == BLOCK_REWARD - FEE * core_fee
    assert tracker1.delta() == FEE * core_fee


def test_duplicate_transfer_success(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    tx = pledge_agent.transferBtc(tx_id_list[0], operators[1])
    assert 'transferredBtc' in tx.events
    tx = pledge_agent.transferBtc(tx_id_list[0], operators[2])
    assert 'transferredBtc' in tx.events
    tx = pledge_agent.transferBtc(tx_id_list[0], operators[0])
    assert 'transferredBtc' in tx.events
    addr_list = pledge_agent.getAgentAddrList(end_round)
    assert len(addr_list) == 3
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert 'claimedReward' not in tx.events


def test_claim_rewards_success_with_max_stake_certificates(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    pledge_agent.setClaimRoundLimit(10)
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    tx_id = tx_id_list[0]
    turn_round()
    for i in range(11):
        before_transfer_agent = pledge_agent.btcReceiptMap(tx_id)['agent']
        assert pledge_agent.btcReceiptMap(tx_id)['agent'] == before_transfer_agent
        if i % 2 == 0:
            pledge_agent.transferBtc(tx_id, operators[1])
            agent = operators[1]
        else:
            pledge_agent.transferBtc(tx_id, operators[2])
            agent = operators[2]
        assert pledge_agent.btcReceiptMap(tx_id)['agent'] == agent
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert 'claimedReward' not in tx.events
    assert tracker0.delta() == 0


def test_revert_on_invalid_btc_transaction(pledge_agent, set_candidate):
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx = (delegate_btc_block_data['btc_tx_block_data'] +
              "03a9149ca26c6aa5a614836d041193ab7df1b6d650791387"
              "00000000000000002c6a2a045c96c42c56fdb78294f96b0cfa33c92be"
              "d7d75f96a9fb29aac15b9a4b7f17c3385939b007540f4d7914e930100000000001976a914574fdd26858c28ede5225a809f747c"
              "01fcc1f92a88ac00000000")
    with brownie.reverts("BitcoinHelper: invalid tx"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_claim_btc_staking_rewards_success(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    pledge_agent.delegateBtc(btc_tx, round_tag, [], 0, lock_script)
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    expect_event(tx, "claimedReward", {
        "amount": BLOCK_REWARD // 2 - FEE,
        "success": True
    })
    assert tracker.delta() == BLOCK_REWARD // 2


@pytest.mark.parametrize("internal", [
    pytest.param(0, id="same round"),
    pytest.param(1, id="adjacent rounds"),
    pytest.param(2, id="spanning multiple rounds"),
])
def test_claim_multi_round_btc_staking_rewards(pledge_agent, set_candidate, internal):
    operators, consensuses = set_candidate
    tx_id_list = []
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id0 = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    tx_id_list.append(tx_id0)
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[0], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script)
    tx_id_list.append(tx_id1)
    turn_round()
    turn_round(consensuses, round_count=internal)
    tracker = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker.delta() == BLOCK_REWARD * internal


def test_distribute_rewards_to_multiple_addresses(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id0 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[1], lock_script_type)
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[0], lock_script_type)
    tx_id_list0, tx_id_list1 = [], []
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script)
    tx_id_list0.append(tx_id0)
    tx_id_list1.append(tx_id1)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list1)
    pledge_agent.claimBtcReward(tx_id_list0, {"from": accounts[1]})
    assert tracker0.delta() == BLOCK_REWARD // 4 + FEE
    assert tracker1.delta() == BLOCK_REWARD // 2 - BLOCK_REWARD // 4 - FEE


def test_claim_rewards_for_multiple_coin_staking(pledge_agent, set_candidate):
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id0 = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[1], lock_script_type)
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[0], lock_script_type)
    delegate_amount = 50000
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount // 2})
    tx_id_list0, tx_id_list1 = [], []
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    tx_id_list0.append(tx_id0)
    tx_id_list1.append(tx_id1)
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list1)
    pledge_agent.claimBtcReward(tx_id_list0, {"from": accounts[1]})
    actual_reward0 = total_reward * (BTC_VALUE * btcFactor) // (delegate_amount // 2 + BTC_VALUE * btcFactor)
    actual_reward1 = total_reward * (BTC_VALUE * btcFactor) // (delegate_amount + BTC_VALUE * btcFactor)
    assert tracker0.delta() == actual_reward0 - FEE
    assert tracker1.delta() == actual_reward1 - FEE


def test_unable_to_claim_rewards_after_end_round(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    round_tag = end_round - MIN_BTC_LOCK_ROUND - 1
    set_last_round_tag(round_tag)
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses, round_count=3)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == BLOCK_REWARD * 1.5
    voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    assert voucher['delegator'] == ZERO_ADDRESS
    turn_round(consensuses)
    #  Unable to claim, as the expired data is removed from the btcReceiptList, resulting in the message 'not the delegator of this btc receipt'
    with brownie.reverts("btc tx not found"):
        pledge_agent.claimBtcReward(tx_id_list)


def test_single_validator_multiple_stakes(pledge_agent, set_candidate):
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    lock_time1 = lock_time + ROUND_INTERVAL * 2
    lock_script0 = get_lock_script(lock_time, public_key, lock_script_type)
    lock_script1 = get_lock_script(lock_time1, public_key, lock_script_type)
    end_round = lock_time // ROUND_INTERVAL
    round_tag = end_round - MIN_BTC_LOCK_ROUND - 1
    set_last_round_tag(round_tag)
    btc_amount0 = 3000 * btcFactor
    btc_amount1 = 2500 * btcFactor
    delegate_amount = 45000
    delegate_btc_tx0, tx_id0 = get_btc_tx(btc_amount0 // btcFactor, chain_id, operators[0], accounts[0],
                                          lock_script_type)
    delegate_btc_tx1 = (delegate_btc_block_data['witness_btc_tx_block_data']
                        + ("03c40900"
                           "000000000022002043c1a535b8941dbb2945ab932abb99995ffc7a5c3ea680b121ef9ca99b7dee45"
                           "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
                           "bcc00000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000"))
    tx_id_list = []
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script0)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script1)
    tx_id_list.append(tx_id0)
    tx_id_list.append(get_transaction_txid(delegate_btc_tx1))
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses, round_count=6)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    total_btc_amount = btc_amount0 + btc_amount1
    reward0 = total_reward * total_btc_amount // (total_btc_amount + delegate_amount)
    reward1 = total_reward * btc_amount1 // (btc_amount1 + delegate_amount)
    actual_reward = reward0 * 3 + reward1 * 2
    assert tracker0.delta() == actual_reward


def test_no_rewards_generated_at_end_of_round(pledge_agent, delegate_btc_valid_tx, set_candidate):
    operators, consensuses = set_candidate
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    end_round = lock_time // ROUND_INTERVAL
    round_tag = end_round - MIN_BTC_LOCK_ROUND - 1
    set_last_round_tag(round_tag)
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    turn_round(consensuses, round_count=2)
    assert pledge_agent.getAgentAddrList(end_round)[0] == operators[0]
    # endRound:20103
    # at the end of round 20102, the expired BTC staking will be deducted from the validator upon transitioning to round 20103.
    turn_round(consensuses, round_count=1)
    assert len(pledge_agent.getAgentAddrList(end_round)) == 0
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert "claimedReward" in tx.events
    turn_round(consensuses, round_count=1)
    assert "claimedReward" in tx.events


def test_multiple_users_staking_to_same_validator(pledge_agent, set_candidate):
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    lock_time1 = lock_time + ROUND_INTERVAL * 2
    lock_script0 = get_lock_script(lock_time, public_key, lock_script_type)
    lock_script1 = get_lock_script(lock_time1, public_key, lock_script_type)
    end_round = lock_time // ROUND_INTERVAL
    round_tag = end_round - MIN_BTC_LOCK_ROUND - 1
    set_last_round_tag(round_tag)
    btc_amount0 = 3000 * btcFactor
    btc_amount1 = 2500 * btcFactor
    delegate_amount = 45000
    delegate_btc_tx0, tx_id0 = get_btc_tx(btc_amount0 // btcFactor, chain_id, operators[0], accounts[1],
                                          lock_script_type)
    delegate_btc_tx1 = delegate_btc_block_data[
                           'witness_btc_tx_block_data'] + ("03c40900"
                                                           "000000000022002043c1a535b8941dbb2945ab932abb99995ffc7a5c3ea680b121ef9ca99b7dee45"
                                                           "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
                                                           "722f0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    delegate_btc_tx2, tx_id2 = get_btc_tx(btc_amount0 // btcFactor, chain_id, operators[0], accounts[0],
                                          lock_script_type)
    tx_id_list0, tx_id_list1 = [], []
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script0)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script1)
    pledge_agent.delegateBtc(delegate_btc_tx2, 0, [], 0, lock_script0)
    tx_id_list0.append(get_transaction_txid(delegate_btc_tx1))
    tx_id_list0.append(tx_id2)
    tx_id_list1.append(tx_id0)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses, round_count=5)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list0)
    pledge_agent.claimBtcReward(tx_id_list1, {"from": accounts[1]})
    total_btc_amount = btc_amount0 * 2 + btc_amount1
    reward0 = (total_reward * btc_amount0 // (total_btc_amount + delegate_amount) * 3) + (
            total_reward * btc_amount1 // (total_btc_amount + delegate_amount) * 3) + total_reward * (
                  btc_amount1) // (btc_amount1 + delegate_amount) * 2
    reward1 = total_reward * btc_amount0 // (total_btc_amount + delegate_amount) * 3
    assert tracker0.delta() == reward0 + FEE
    assert tracker1.delta() == reward1 - FEE


def test_claim_rewards_for_multiple_stakes_to_different_validators(pledge_agent, set_candidate, delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 30000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[0], lock_script_type)
    tx_id_list.append(tx_id1)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    actual_reward0 = total_reward * BTC_VALUE * btcFactor // (delegate_amount + BTC_VALUE * btcFactor)
    assert tracker0.delta() == actual_reward0 * 4


@pytest.mark.parametrize("btc_factor", [
    pytest.param(1, id="btc_factor is 1"),
    pytest.param(1000, id="btc_factor is 1000"),
    pytest.param(10000, id="btc_factor is 10000"),
    pytest.param(100000, id="btc_factor is 100000"),
    pytest.param(1000000, id="btc_factor is 1000000"),
])
def test_claim_rewards_after_modifying_btc_factor(pledge_agent, set_candidate, delegate_btc_valid_tx, btc_factor):
    pledge_agent.setBtcFactor(btc_factor)
    btc_factor = btc_factor * pledge_agent.BTC_UNIT_CONVERSION()
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 3000000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    actual_reward0 = total_reward * BTC_VALUE * btc_factor // (delegate_amount + BTC_VALUE * btc_factor)
    assert tracker0.delta() == actual_reward0


def test_claim_rewards_after_staking_every_other_round(pledge_agent, set_candidate, delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 30000
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[2]})
    turn_round()
    btc_amount = 2500
    total_btc_amount = BTC_VALUE * btcFactor
    delegate_btc_tx1, tx_id1 = get_btc_tx(btc_amount, chain_id, operators[0], accounts[0], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script)
    tx_id_list.append(tx_id1)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    actual_reward0 = total_reward * BTC_VALUE * btcFactor // (delegate_amount + total_btc_amount)
    assert tracker0.delta() == actual_reward0
    turn_round(consensuses)
    pledge_agent.claimBtcReward(tx_id_list)
    total_btc_amount += btc_amount * btcFactor
    actual_reward0 = total_reward * total_btc_amount // (delegate_amount + total_btc_amount)
    assert tracker0.delta() == actual_reward0


def test_transfer_btc_success(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    assert voucher["endRound"] == end_round
    tx = pledge_agent.transferBtc(tx_id_list[0], operators[1])
    pledge_agent.transferCoin(operators[0], operators[2], {'from': accounts[1]})
    expect_event(tx, 'transferredBtc', {
        'txid': tx_id_list[0],
        'sourceAgent': operators[0],
        'targetAgent': operators[1],
        'delegator': accounts[0],
        'amount': BTC_VALUE,
        'totalAmount': BTC_VALUE
    })
    turn_round(consensuses, round_count=4)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list)
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == total_reward * 2
    assert tracker1.delta() == total_reward * 3 + total_reward - (total_reward // 2)


def test_transfer_btc_when_no_rewards_in_current_round(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    pledge_agent.transferBtc(tx_id_list[0], operators[1])
    voucher0 = pledge_agent.btcReceiptMap(tx_id_list[0])
    assert voucher0["endRound"] == end_round
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list)
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == 0
    assert tracker1.delta() == total_reward - total_reward // 2
    voucher0 = pledge_agent.btcReceiptMap(tx_id_list[0])
    assert voucher0["endRound"] == end_round
    assert pledge_agent.agentsMap(operators[0])["btc"] == pledge_agent.agentsMap(operators[0])["totalBtc"] == 0
    assert pledge_agent.agentsMap(operators[1])["btc"] == pledge_agent.agentsMap(operators[1])["totalBtc"] == BTC_VALUE


def test_revert_on_max_fee_exceeded(pledge_agent, set_candidate):
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    # fee range 1-255
    delegate_btc_tx0, _ = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type, lock_script,
                                     core_fee=256)
    with brownie.reverts("BitcoinHelper: invalid tx"):
        pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)


def test_claim_rewards_with_fee_deduction_success(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward(tx_id_list)
    expect_event(tx, 'transferredBtcFee', {
        'txid': tx_id_list[0],
        'fee': FEE,
        'feeReceiver': accounts[1]
    })
    assert tracker1.delta() == FEE


@pytest.mark.parametrize("fee", [
    pytest.param(0, id="fee is 0"),
    pytest.param(1, id="fee is 1"),
    pytest.param(10, id="fee is 10"),
    pytest.param(50, id="fee is 50"),
    pytest.param(254, id="fee is 254"),
    pytest.param(255, id="fee is 255")
])
def test_claim_rewards_with_different_fees_success(pledge_agent, set_candidate, fee):
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id0 = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type,
                                          core_fee=fee)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward([tx_id0])
    if fee > 0:
        expect_event(tx, 'transferredBtcFee', {
            'txid': tx_id0,
            'fee': fee * pledge_agent.FEE_FACTOR(),
            'feeReceiver': accounts[1]
        })
    else:
        assert 'transferredBtcFee' not in tx.events
    assert tracker1.delta() == fee * pledge_agent.FEE_FACTOR()


def test_insufficient_rewards_to_pay_porter_fee(pledge_agent, set_candidate):
    end_round = lock_time // ROUND_INTERVAL
    fee = 100
    actual_fee = fee * pledge_agent.FEE_FACTOR()
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type, core_fee=fee)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=1)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward([tx_id])
    received_fee = BLOCK_REWARD // 4
    expect_event(tx, 'transferredBtcFee', {
        'txid': tx_id,
        'fee': received_fee,
        'feeReceiver': accounts[1]
    })
    voucher = pledge_agent.btcReceiptMap(tx_id)
    assert voucher['fee'] == actual_fee - received_fee
    assert voucher['feeReceiver'] == accounts[1]
    assert tracker1.delta() == received_fee
    turn_round(consensuses, round_count=1)
    pledge_agent.claimBtcReward([tx_id])
    assert tracker1.delta() == actual_fee - received_fee
    assert pledge_agent.btcReceiptMap(tx_id)['fee'] == 0
    assert tracker0.delta() == BLOCK_REWARD // 4 - (actual_fee - received_fee)


@pytest.mark.parametrize("fee", [
    pytest.param(0, id="fee is 0"),
    pytest.param(1, id="fee is 1"),
    pytest.param(10, id="fee is 10"),
    pytest.param(50, id="fee is 50"),
    pytest.param(254, id="fee is 254"),
    pytest.param(255, id="fee is 255")
])
def test_claim_rewards_with_different_fees_after_transfer_success(pledge_agent, set_candidate, fee):
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    delegate_btc_tx0, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type, core_fee=fee)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    pledge_agent.transferBtc(tx_id, operators[1])
    turn_round(consensuses, round_count=3)
    tracker1 = get_tracker(accounts[1])
    tx = pledge_agent.claimBtcReward([tx_id])
    if fee > 0:
        expect_event(tx, 'transferredBtcFee', {
            'txid': tx_id,
            'fee': fee * pledge_agent.FEE_FACTOR(),
            'feeReceiver': accounts[1]
        })
    else:
        assert 'transferredBtcFee' not in tx.events
    assert tracker1.delta() == fee * pledge_agent.FEE_FACTOR()


def test_multiple_btc_receipts_to_single_address(pledge_agent, set_candidate, delegate_btc_valid_tx):
    delegate_amount = 20000
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    round_tag = get_current_round()
    tx_id0 = get_transaction_txid(delegate_btc_tx0)
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[0], lock_script_type)
    tx_id_list.append(tx_id1)
    pledge_agent.delegateBtc(delegate_btc_tx0, round_tag, [], 0, lock_script, {'from': accounts[1]})
    pledge_agent.delegateBtc(delegate_btc_tx1, round_tag, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    pledge_agent.transferBtc(tx_id0, operators[2])
    pledge_agent.transferBtc(tx_id1, operators[2])
    turn_round(consensuses)
    tx = pledge_agent.claimBtcReward(tx_id_list)
    assert 'claimedReward' not in tx.events
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    actual_reward = total_reward * (BTC_VALUE * 2 * btcFactor) // (BTC_VALUE * 2 * btcFactor + delegate_amount)
    assert tracker0.delta() == actual_reward * 2 - FEE * 2


def test_multiple_reward_transfers_in_multiple_rounds(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = [], []
    for operator in accounts[10:22]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    tx_id_list = []
    for index, operator in enumerate(operators):
        btc_tx, tx_id = get_btc_tx(BTC_VALUE + index, chain_id, operator, accounts[0], lock_script_type,
                                   lock_script)
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
        tx_id_list.append(tx_id)
    turn_round()
    for index, operator in enumerate(operators):
        before_agent = operators[index]

        transfer_voucher = pledge_agent.btcReceiptMap(tx_id_list[index])
        expect_query(transfer_voucher,
                     {'agent': before_agent,
                      'delegator': accounts[0],
                      'value': BTC_VALUE + index,
                      'endRound': end_round,
                      'rewardIndex': 0,
                      'feeReceiver': accounts[1],
                      'fee': FEE})
        tx = pledge_agent.transferBtc(tx_id_list[index], operators[index - 1])
        before_amount = BTC_VALUE + index
        target_agent_amount = 0
        if index == 0:
            target_agent_amount = operators.index(operators[index - 1]) + BTC_VALUE
        expect_event(tx, "transferredBtc", {
            "txid": tx_id_list[index],
            "sourceAgent": operators[index],
            "targetAgent": operators[index - 1],
            "amount": BTC_VALUE + index,
            "totalAmount": before_amount + target_agent_amount,
        })
        latest_voucher = pledge_agent.btcReceiptMap(tx_id_list[index])
        expect_query(latest_voucher,
                     {
                         'agent': operators[index - 1],
                         'delegator': accounts[0],
                         'value': BTC_VALUE + index,
                         'endRound': end_round,
                         'rewardIndex': 1,
                         'feeReceiver': accounts[1],
                         'fee': FEE}
                     )

    pledge_agent.setClaimRoundLimit(3)
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == BLOCK_REWARD // 2 * 3 - FEE * 3
    voucher = pledge_agent.btcReceiptMap(tx_id_list[0])
    assert voucher['agent'] == operators[-1]
    pledge_agent.setClaimRoundLimit(7)
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == BLOCK_REWARD // 2 * 7 - FEE * 7
    turn_round(consensuses, round_count=2)
    pledge_agent.setClaimRoundLimit(21)
    pledge_agent.claimBtcReward(tx_id_list)
    """
    when a validator only has rewards for one round, but I attempt to claim rewards every other round, 
    even for rounds without rewards, it still counts towards the claim limit.
    """
    assert tracker0.delta() == BLOCK_REWARD // 2 * 11 - FEE
    assert pledge_agent.btcReceiptMap(tx_id_list[0])['agent'] == ZERO_ADDRESS
    pledge_agent.claimBtcReward(tx_id_list[-2:])
    assert tracker0.delta() == BLOCK_REWARD // 2 * 3 - FEE


def test_claim_limit_exhausted(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    tx_id_list = []
    for index, operator in enumerate(operators):
        btc_tx, tx_id = get_btc_tx(BTC_VALUE, chain_id, operator, accounts[0], lock_script_type,
                                   lock_script)
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
        tx_id_list.append(tx_id)
    turn_round()
    pledge_agent.setClaimRoundLimit(10)
    delegate_amount = 20000
    pledge_agent.delegateCoin(operators[1], {"value": delegate_amount, "from": accounts[1]})
    pledge_agent.delegateCoin(operators[2], {"value": delegate_amount, "from": accounts[1]})
    turn_round(consensuses, round_count=2)
    pledge_agent.claimBtcReward(tx_id_list)
    turn_round(consensuses, round_count=2)
    pledge_agent.setClaimRoundLimit(4)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    """
    If the validator has other stakes and has generated rewards, 
    then the claim limit count will not be affected when claiming BTC rewards.
    """
    assert tracker0.delta() == BLOCK_REWARD // 2 + BLOCK_REWARD // 4 * 2
    assert pledge_agent.btcReceiptMap(tx_id_list[2])['agent'] == ZERO_ADDRESS


def test_claiming_reward_by_non_owner_of_this_btc_receipt_reverts(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=1)
    with brownie.reverts("not the delegator of this btc receipt"):
        pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[1]})


def test_claiming_reward_with_unconfirmed_txid_reverts(pledge_agent, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=1)
    get_tracker(accounts[0])
    error_tx_id = '0x8a2d192b0d0276fee31689693269e14aa9c78982c0d29ddf417a3064fd623892'
    with brownie.reverts("btc tx not found"):
        pledge_agent.claimBtcReward([error_tx_id])
    error_tx_id = '0x0'
    with brownie.reverts("btc tx not found"):
        pledge_agent.claimBtcReward([error_tx_id])
    error_tx_id = '0000012345'
    with brownie.reverts("btc tx not found"):
        pledge_agent.claimBtcReward([error_tx_id])


def test_revert_on_incorrect_version(pledge_agent, set_candidate):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script = get_lock_script(lock_time, public_key, lock_script_type)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type, version=2)
    with brownie.reverts("wrong version"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)


def test_revert_on_transaction_without_op_return(pledge_agent):
    lock_script = "0480db8767b17551210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e122103000871fc99dfcbb5a811c5e23c077683b07ab2bbbfff775ce30a809a6d41214152ae"
    btc_tx = (
        "020000000102ae7f498ec542f8b2a70d3a5750058337a042b55b4130587a5271568921dc70020000006b483045022100f78b1eaacb6f10100015eca4618edea515d06d1a4ec432b2b669f4cbeed0dd1c02206c9137982f46c1129de1069b83987b1ad907314231077ac992a8e8990c92c8d401210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12ffffffff"
        "02bc34"
        "000000000000220020f55d9bd2487756dd81b84946aab690e0e2e9b17c681a81c2d1ce22006395292b9b69"
        "0000000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000")
    with brownie.reverts("payload length is too small"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})


def test_modify_btc_factor_after_delegating_btc(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    btc_factor = 4
    pledge_agent.setBtcFactor(btc_factor)
    btc_factor = btc_factor * pledge_agent.BTC_UNIT_CONVERSION()
    delegate_btc_tx1, tx_id = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script)
    tx_id_list.append(tx_id)
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list)
    assert tracker0.delta() == total_reward // 2
    turn_round(consensuses)
    pledge_agent.claimBtcReward(tx_id_list)
    reward = total_reward * (BTC_VALUE * btc_factor * 2) // (BTC_VALUE * btc_factor * 2 + delegate_amount)
    assert tracker0.delta() == reward


def test_stake_multiple_currencies_and_claim_rewards(pledge_agent, candidate_hub, btc_light_client, set_candidate,
                                                     delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    pledge_agent.setPowerBlockFactor(100000)
    turn_round()
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    pledge_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    turn_round(consensuses, tx_fee=TX_FEE)
    pledge_agent.claimReward([], {'from': accounts[2]})
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker2.delta() == total_reward // 3 * 2
    remain_reward = total_reward - total_reward // 3 * 2
    total_coin = delegate_amount + BTC_VALUE * btcFactor
    btc_value = BTC_VALUE * btcFactor
    assert tracker0.delta() == remain_reward * btc_value // total_coin
    assert tracker1.delta() == remain_reward - remain_reward * btc_value // total_coin


def test_claiming_btc_reward_with_multiple_power(pledge_agent, candidate_hub, btc_light_client, set_candidate,
                                                 delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    delegate_amount = 40000
    pledge_agent.setPowerBlockFactor(100000)
    turn_round()
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 1, operators[1], [accounts[3]])
    pledge_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    pledge_agent.delegateCoin(operators[1], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    tracker3 = get_tracker(accounts[3])
    turn_round(consensuses, tx_fee=TX_FEE)
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward([], {'from': accounts[2]})
    pledge_agent.claimReward([], {'from': accounts[3]})
    total_reward = BLOCK_REWARD // 2
    score = (delegate_amount * 2 + BTC_VALUE * btcFactor) * 3
    power_score = score // 3 * 2 // 2
    power_reward0 = total_reward * power_score // (power_score + BTC_VALUE * btcFactor + delegate_amount)
    power_reward1 = total_reward * power_score // (power_score + delegate_amount)
    remain_reward0 = total_reward - power_reward0
    remain_reward1 = total_reward - power_reward1
    reward0 = remain_reward0 * (BTC_VALUE * btcFactor) // (BTC_VALUE * btcFactor + delegate_amount)
    reward1 = remain_reward1 + remain_reward0 - reward0
    assert tracker0.delta() == reward0
    assert tracker1.delta() == reward1
    assert tracker2.delta() == power_reward0
    assert tracker3.delta() == power_reward1


def test_claim_coin_reward_correctly_with_existing_btc_staking(pledge_agent, candidate_hub, set_candidate,
                                                               delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[1]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=5)
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker1.delta() == total_reward // 2 * 3 + BLOCK_REWARD


@pytest.mark.parametrize("transfer_type", ['all', 'part'])
def test_coin_transfer_with_power_and_btc_staking(pledge_agent, btc_light_client, set_candidate, delegate_btc_valid_tx,
                                                  transfer_type):
    pledge_agent.setPowerBlockFactor(100000)
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 80000
    total_delegate = delegate_amount + BTC_AMOUNT
    transfer_amount = delegate_amount // 2
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    if transfer_type == 'all':
        transfer_amount = delegate_amount
    tx = pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[1]})
    expect_event(tx, 'transferredCoin', {
        'amount': transfer_amount
    })
    total_reward = total_reward * 1 // 3
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker0.delta() == total_reward * BTC_AMOUNT // total_delegate - FEE
    assert tracker1.delta() == total_reward - total_reward * BTC_AMOUNT // total_delegate


@pytest.mark.parametrize("undelegate_type", ['all', 'part'])
def test_undelegate_with_power_and_btc_staking(pledge_agent, set_candidate, btc_light_client, delegate_btc_valid_tx,
                                               undelegate_type):
    pledge_agent.setPowerBlockFactor(100000)
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    delegate_amount = 20000
    total_delegate = delegate_amount + BTC_AMOUNT
    undelegate_amount = delegate_amount
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    total_score = total_delegate * 3
    if undelegate_type == 'part':
        undelegate_amount = 7000
    pledge_agent.undelegateCoin(operators[0], undelegate_amount, {'from': accounts[1]})
    tx = turn_round(consensuses)
    deduction_reward = total_reward * undelegate_amount // total_score
    power_reward = total_reward * 2 // 3
    expect_event(tx, "receiveDeposit", {
        'amount': power_reward
    }, idx=0)
    expect_event(tx, "receiveDeposit", {
        'amount': deduction_reward
    }, idx=1)
    reward1 = total_reward * (delegate_amount - undelegate_amount) // total_score
    reward0 = total_reward - power_reward - reward1 - deduction_reward
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    assert tracker1.delta() == reward1
    assert tracker0.delta() == reward0 - FEE
    assert deduction_reward + reward0 + reward1 + power_reward == total_reward


def test_claiming_btc_reward_with_power_and_btc_staking(pledge_agent, set_candidate, btc_light_client,
                                                        delegate_btc_valid_tx):
    pledge_agent.setPowerBlockFactor(100000)
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    turn_round()
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    assert tracker0.delta() == total_reward // 3 - FEE


def test_operations_with_coin_power_and_btc_staking(pledge_agent, set_candidate, btc_light_client,
                                                    delegate_btc_valid_tx):
    pledge_agent.setPowerBlockFactor(100000)
    delegate_amount = 20000
    total_delegate = delegate_amount + BTC_AMOUNT
    end_round = lock_time // ROUND_INTERVAL
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    round_tag = get_current_round() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[0], [accounts[2]])
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    undelegate_amount = 7000
    transfer_amount = delegate_amount // 2
    pledge_agent.transferCoin(operators[0], operators[2], transfer_amount, {'from': accounts[1]})
    pledge_agent.undelegateCoin(operators[2], undelegate_amount, {'from': accounts[1]})
    pledge_agent.transferBtc(tx_id_list[0], operators[1])
    turn_round(consensuses)
    total_score = total_delegate * 3
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    deduction_reward = (total_reward * undelegate_amount // total_score) + (total_reward * BTC_AMOUNT // total_score)
    power_reward = total_reward * 2 // 3
    reward1 = total_reward - power_reward - deduction_reward
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimReward([], {'from': accounts[2]})
    total_delegate -= undelegate_amount
    assert tracker0.delta() == 0
    assert tracker1.delta() == reward1
    assert tracker2.delta() == total_reward * 2 // 3
    total_score = total_delegate * 3
    turn_round(consensuses)
    # the total score of all power.
    power = total_score * 2 // 3
    power_reward = total_reward * power // (power + delegate_amount - transfer_amount)
    coin_reward = total_reward - power_reward + total_reward
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward([], {'from': accounts[2]})
    assert tracker0.delta() == total_reward - FEE
    assert tracker1.delta() == coin_reward
    assert tracker2.delta() == power_reward + FEE


def test_transfer_btc_reverts_for_non_delegator(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    with brownie.reverts("not the delegator of this btc receipt"):
        pledge_agent.transferBtc(tx_id_list[0], operators[1], {'from': accounts[1]})
    with brownie.reverts("not the delegator of this btc receipt"):
        pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[1]})


def test_claiming_historical_rewards_with_btc_transfer(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script)
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tx = pledge_agent.transferBtc(tx_id_list[0], operators[1], {'from': accounts[0]})
    expect_event(tx, "claimedReward", {
        'amount': BLOCK_REWARD // 4 * 2 - FEE
    })
    assert tracker0.delta() == BLOCK_REWARD // 4 * 2


def test_transfer_btc_to_existing_btc_staker(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    delegate_amount = 20000
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[1], accounts[1], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": delegate_amount, "from": accounts[1]})
    turn_round()
    pledge_agent.transferBtc(tx_id_list[0], operators[1], {'from': accounts[0]})
    agent_map0 = pledge_agent.agentsMap(operators[0])
    agent_map1 = pledge_agent.agentsMap(operators[1])
    assert agent_map0['totalBtc'] == 0
    assert agent_map1['totalBtc'] == BTC_VALUE * 2
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward([tx_id_list[0]], {'from': accounts[0]})
    pledge_agent.claimBtcReward([tx_id1], {'from': accounts[1]})
    total_reward = BLOCK_REWARD // 2
    assert tracker0.delta() == total_reward // 2 - FEE
    assert tracker1.delta() == total_reward + total_reward - total_reward // 2 - FEE


def test_transfer_btc_from_multiple_btc_stakings(pledge_agent, set_candidate, delegate_btc_valid_tx):
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, delegate_btc_tx0, tx_id_list = delegate_btc_valid_tx
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[0], accounts[0], lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx0, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    tx_id_list.append(tx_id1)
    turn_round()
    pledge_agent.transferBtc(tx_id_list[0], operators[1], {'from': accounts[0]})
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    total_reward = BLOCK_REWARD // 2
    assert tracker0.delta() == total_reward - total_reward // 2 - FEE


def test_multiple_btc_stakings_in_vout(pledge_agent, set_candidate):
    btc_amount = 53820
    lock_script = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
    operators, consensuses = set_candidate
    btc_tx = (
        "0200000001dd94cb72979c528593cb1188f4e3bf43a52f5570edab981e3d303ff24166afe5000000006b483045022100f2f069e37929cdfafffa79dcc1cf478504875fbe2a41704a96aee88ec604c0e502207259c56c67de8de6bb8c15e9d14b6ad16acd86d6a834fbb0531fd27bee7e5e3301210223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
        "feffffff03b80b00"
        "000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
        "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a0010480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
        "3cd200000000000017a914c0958c8d9357598c5f7a6eea8a807d81683f9bb68700000000")
    tx_id = get_transaction_txid(btc_tx)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {"from": accounts[2]})
    turn_round()
    expect_event(tx, 'delegatedBtc', {
        'txid': tx_id,
        'script': '0x' + lock_script,
        'blockHeight': 0,
        'outputIndex': 2
    })
    agent_map = pledge_agent.agentsMap(operators[0])
    expect_query(pledge_agent.btcReceiptMap(tx_id), {
        'agent': operators[0],
        'delegator': accounts[0],
        'value': btc_amount,
        'endRound': lock_time // ROUND_INTERVAL,
        'rewardIndex': 0,
        'feeReceiver': accounts[2],
        'fee': FEE
    })
    turn_round(consensuses)
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[2])
    pledge_agent.claimBtcReward([tx_id])
    assert agent_map['totalBtc'] == btc_amount
    assert pledge_agent.btcReceiptMap(tx_id)['value'] == btc_amount
    assert tracker0.delta() == BLOCK_REWARD // 2 - FEE
    assert tracker1.delta() == FEE


def test_claim_reward_reentry(pledge_agent, set_candidate, delegate_btc_valid_tx):
    pledge_agent_proxy = ClaimBtcRewardReentry.deploy(pledge_agent.address, {'from': accounts[0]})
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, _, _ = delegate_btc_valid_tx
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[0], pledge_agent_proxy.address,
                                          lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": 20000, "from": accounts[1]})
    turn_round()
    pledge_agent_proxy.setTxidList([tx_id1])
    turn_round(consensuses)
    tracker = get_tracker(pledge_agent_proxy)
    tx = pledge_agent_proxy.claimBtcReward([tx_id1])
    expect_event(tx, "proxyBtcClaim", {
        "success": False
    })
    assert tracker.delta() == 0


def test_transfer_btc_reentry(pledge_agent, set_candidate, delegate_btc_valid_tx):
    pledge_agent_proxy = TransferBtcReentry.deploy(pledge_agent.address, {'from': accounts[0]})
    end_round = lock_time // ROUND_INTERVAL
    operators, consensuses = set_candidate
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 3)
    lock_script, _, _ = delegate_btc_valid_tx
    delegate_btc_tx1, tx_id1 = get_btc_tx(BTC_VALUE, chain_id, operators[0], pledge_agent_proxy.address,
                                          lock_script_type)
    pledge_agent.delegateBtc(delegate_btc_tx1, 0, [], 0, lock_script, {'from': accounts[2]})
    pledge_agent.delegateCoin(operators[0], {"value": 20000, "from": accounts[1]})
    turn_round()
    pledge_agent_proxy.setTxid(tx_id1)
    pledge_agent_proxy.setTargetAgent(operators[1].address)
    turn_round(consensuses)
    tracker = get_tracker(pledge_agent_proxy)
    tx = pledge_agent_proxy.transferBtc(tx_id1, operators[1].address)
    expect_event(tx, "proxyTransferBtc", {
        "success": False
    })
    assert tracker.delta() == 0


def test_claiming_rewards_with_multiple_staking_types(pledge_agent, candidate_hub, set_candidate, btc_light_client,
                                                      delegate_btc_valid_tx):
    total_reward = BLOCK_REWARD // 2
    operators, consensuses = set_candidate
    pledge_agent.setPowerBlockFactor(100000)
    turn_round()
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    btc_light_client.setMiners(round_tag + 2, operators[1], [accounts[2]])
    pledge_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    pledge_agent.transferBtc(tx_id_list[0], operators[1], {'from': accounts[0]})
    turn_round(consensuses, tx_fee=TX_FEE)
    pledge_agent.claimReward([], {'from': accounts[2]})
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    assert tracker2.delta() == total_reward // 3 * 2
    remain_reward = total_reward - total_reward // 3 * 2
    total_coin = delegate_amount + BTC_VALUE * btcFactor
    btc_value = BTC_VALUE * btcFactor
    assert tracker0.delta() == 0
    assert tracker1.delta() == remain_reward - remain_reward * btc_value // total_coin


def test_btc_transaction_with_witness_as_output_address(pledge_agent, set_candidate):
    btc_tx = (
        "020000000001010280516aa5b5fb7bd9b7b94b14145af46f6404da96d5f56e1504e1d9d15ef6520200000017160014a808bc3c1ba547b0ba2df4abf1396f35c4d23b4ffeffffff"
        "03a08601"
        "00000000002200204969dea00948f43ae8f6efb45db768e41b15f4fd70d7fcf366c270c1cbca262a"
        "0000000000000000536a4c505341542b01045c9fb29aac15b9a4b7f17c3385939b007540f4d791ccf7e1DAb7D90A0a91f8B1f6A693Bf0bb3a979a001041e28fd65b17576a914a808bc3c1ba547b0ba2df4abf1396f35c4d23b4f88ac"
        "a4d81d"
        "000000000017a9144c35996fbf4026de7c8fe79c4320c248a10e4bf28702483045022100e32dd040238c19321407b7dfbba957e5988755779030dbcc52e6ae22a2a2088402202eeb497ae61aee9eba97cc4f5d34ba814c3ad1c0bf3286edaba05f044ab4bba401210386f359aa5a42d821370bf07a5ad86c1ff2d892662699103e462ae04d082d83ac00000000")
    lock_script = '041e28fd65b17576a914a808bc3c1ba547b0ba2df4abf1396f35c4d23b4f88ac'
    scrip_pubkey = 'a9144c35996fbf4026de7c8fe79c4320c248a10e4bf287'
    btc_tx = remove_witness_data_from_raw_tx(btc_tx, scrip_pubkey)
    tx = pledge_agent.delegateBtc(btc_tx, 200, [], 22, lock_script)
    assert 'delegatedBtc' in tx.events


def test_claiming_rewards_after_turn_round_failure(pledge_agent, candidate_hub, btc_light_client,
                                                   set_candidate, delegate_btc_valid_tx):
    set_last_round_tag(get_block_info()['timestamp'] // ROUND_INTERVAL - MIN_BTC_LOCK_ROUND)
    pledge_agent.setPowerBlockFactor(100000)
    candidate_hub.setControlRoundTimeTag(False)
    candidate_hub.setRoundInterval(ROUND_INTERVAL)
    turn_round()
    block_time = get_block_info()['timestamp']
    operators, consensuses = set_candidate
    delegate_amount = 60000
    round_tag = candidate_hub.roundTag() - 7
    btc_light_client.setMiners(round_tag + 1, operators[0], [accounts[2]])
    pledge_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    chain.mine(timestamp=block_time + ROUND_INTERVAL)
    turn_round()
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    candidate_hub.setTurnroundFailed(True)
    chain.mine(timestamp=block_time + ROUND_INTERVAL * 2)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses, tx_fee=TX_FEE)
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    assert tracker0.delta() == 0
    candidate_hub.setTurnroundFailed(False)
    chain.mine(timestamp=block_time + ROUND_INTERVAL * 3)
    turn_round(consensuses, tx_fee=TX_FEE)
    pledge_agent.claimReward([], {'from': accounts[2]})
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    total_reward = BLOCK_REWARD // 2
    assert tracker2.delta() == total_reward // 3 * 2 * 2
    remain_reward = BLOCK_REWARD - total_reward // 3 * 4
    total_coin = delegate_amount + BTC_VALUE * btcFactor
    btc_value = BTC_VALUE * btcFactor
    assert tracker0.delta() == remain_reward * btc_value // total_coin
    assert tracker1.delta() == remain_reward - remain_reward * btc_value // total_coin


def test_btc_stake_expiry_after_turn_round_failure(pledge_agent, candidate_hub, btc_light_client,
                                                   set_candidate, delegate_btc_valid_tx):
    set_last_round_tag(get_block_info()['timestamp'] // ROUND_INTERVAL)
    round = 0
    chain_time = lock_time - ROUND_INTERVAL * (MIN_BTC_LOCK_ROUND + 2)
    pledge_agent.setPowerBlockFactor(100000)
    candidate_hub.setControlRoundTimeTag(False)
    candidate_hub.setRoundInterval(ROUND_INTERVAL)
    set_last_round_tag(get_block_info()['timestamp'] // ROUND_INTERVAL)
    chain.mine(timestamp=chain_time)
    turn_round()
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round()
    operators, consensuses = set_candidate
    delegate_amount = 20000
    pledge_agent.delegateCoin(operators[0], {'value': delegate_amount, 'from': accounts[1]})
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script)
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round()
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round(consensuses, tx_fee=TX_FEE)
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round(consensuses, tx_fee=TX_FEE)
    round += 1
    candidate_hub.setTurnroundFailed(True)
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    with brownie.reverts("turnRound failed"):
        turn_round(consensuses, tx_fee=TX_FEE)
    candidate_hub.setTurnroundFailed(False)
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round(consensuses, tx_fee=TX_FEE)
    total_reward = BLOCK_REWARD // 2
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})
    pledge_agent.claimReward(operators, {'from': accounts[1]})
    reward0 = total_reward // 2 * 2 + BLOCK_REWARD // 2
    assert tracker0.delta() == reward0
    assert tracker1.delta() == BLOCK_REWARD * 2 - reward0
    round += 1
    chain.mine(timestamp=chain_time + ROUND_INTERVAL * round)
    turn_round(consensuses, tx_fee=TX_FEE)
    with brownie.reverts("btc tx not found"):
        pledge_agent.claimBtcReward(tx_id_list, {'from': accounts[0]})


def test_restaking_after_btc_staking_expiry(pledge_agent, candidate_hub, set_candidate, delegate_btc_valid_tx):
    operators, consensuses = set_candidate
    end_round = lock_time // ROUND_INTERVAL
    set_last_round_tag(end_round - MIN_BTC_LOCK_ROUND - 1)
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round()
    with brownie.reverts("btc tx confirmed"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})
    turn_round(consensuses, round_count=4)
    pledge_agent.claimBtcReward(tx_id_list)
    with brownie.reverts("insufficient lock round"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


@pytest.mark.parametrize("key,value", [
    ("requiredCoinDeposit", 1001),
    ("powerFactor", 1002),
    ("btcFactor", 1003),
    ("minBtcLockRound", 1004),
    ("btcConfirmBlock", 1005),
    ("minBtcValue", 1006),
    ("delegateBtcGasPrice", 1e9)
])
def test_update_param_success(pledge_agent, gov_hub, key, value):
    hex_value = padding_left(Web3.toHex(int(value)), 64)
    tx = pledge_agent.updateParam(key, hex_value, {'from': gov_hub.address})
    expect_event(tx, 'paramChange', {
        'key': key,
        'value': hex_value
    })
    if key == 'requiredCoinDeposit':
        assert pledge_agent.requiredCoinDeposit() == value
    elif key == 'powerFactor':
        assert pledge_agent.powerFactor() == value
    elif key == 'btcFactor':
        assert pledge_agent.btcFactor() == value
    elif key == 'minBtcLockRound':
        assert pledge_agent.minBtcLockRound() == value
    elif key == 'btcConfirmBlock':
        assert pledge_agent.btcConfirmBlock() == value
    elif key == 'delegateBtcGasPrice':
        assert pledge_agent.delegateBtcGasPrice() == value
    else:
        assert pledge_agent.minBtcValue() == value


@pytest.mark.parametrize("key", [
    "requiredCoinDeposit",
    "powerFactor",
    "btcFactor",
    "minBtcLockRound",
    "btcConfirmBlock",
    "minBtcValue",
    "delegateBtcGasPrice"
])
def test_update_param_failed(pledge_agent, gov_hub, key):
    hex_value = padding_left(Web3.toHex(0), 64)
    uint256_max = 2 ** 256 - 1
    lower_bound = 1
    if key == 'minBtcValue':
        lower_bound = int(1e4)
    elif key == 'delegateBtcGasPrice':
        lower_bound = int(1e9)
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        [key, 0, lower_bound, uint256_max]
    )
    with brownie.reverts(f"typed error: {error_msg}"):
        pledge_agent.updateParam(key, hex_value, {'from': gov_hub.address})


def test_update_param_failed_non_governance_contract(pledge_agent):
    hex_value = padding_left(Web3.toHex(1000), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        pledge_agent.updateParam('minBtcValue', hex_value, {'from': accounts[0]})


def test_delegator_calling_delegate_btc(pledge_agent, delegate_btc_valid_tx, set_candidate, relay_hub):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    relay_hub.setRelayerRegister(accounts[0], False)
    assert relay_hub.isRelayer(accounts[0]) is False
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    assert 'delegatedBtc' in tx.events


def test_revert_for_non_delegator_or_relayer_calling_delegate_btc(pledge_agent, delegate_btc_valid_tx, relay_hub,
                                                                  set_candidate):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    relay_hub.setRelayerRegister(accounts[1], False)
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[1]})


def test_successful_delegate_btc_call_by_relayer(pledge_agent, delegate_btc_valid_tx, relay_hub,
                                                 set_candidate):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    relay_hub.setRelayerRegister(accounts[5], True)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[5]})
    assert 'delegatedBtc' in tx.events


def test_revert_for_too_high_gas_price(pledge_agent, delegate_btc_valid_tx, set_candidate, relay_hub, gov_hub):
    lock_script, btc_tx, tx_id_list = delegate_btc_valid_tx
    delegate_gas_price = pledge_agent.INIT_DELEGATE_BTC_GAS_PRICE() + 1
    gas_price(delegate_gas_price)
    with brownie.reverts("gas price is too high"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    new_delegate_btc_gas_price = int(1e9)
    hex_value = padding_left(Web3.toHex(new_delegate_btc_gas_price), 64)
    pledge_agent.updateParam('delegateBtcGasPrice', hex_value, {'from': gov_hub.address})
    gas_price(new_delegate_btc_gas_price + 1)
    with brownie.reverts("gas price is too high"):
        pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    gas_price(new_delegate_btc_gas_price)
    tx = pledge_agent.delegateBtc(btc_tx, 0, [], 0, lock_script, {'from': accounts[0]})
    assert 'delegatedBtc' in tx.events
    assert tx.gas_price == new_delegate_btc_gas_price
