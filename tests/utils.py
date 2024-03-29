import random
import codecs
import hashlib

from web3 import Web3
from brownie.network.transaction import TransactionReceipt
from brownie.network.account import LocalAccount
from brownie import chain, web3, history
from eth_account import Account
from eth_abi import encode
from hashlib import sha256

from tests.btc_block_data import *


def random_address():
    return Account.create(str(random.random())).address


def expect_event(tx_receipt: TransactionReceipt, event_name, event_value: dict = None, idx=0):
    assert event_name in tx_receipt.events

    if event_value is None:
        return

    # fetch event by idx
    event = tx_receipt.events[event_name][idx]
    for k, v in event_value.items():
        assert event[k] == v, f'{k} error {event[k]}!={v}'


def get_transaction_txid(btc_tx):
    try:
        tx_id = '0x' + sha256(sha256(bytes.fromhex(btc_tx)).digest()).digest().hex()
    except Exception:
        tx_id = '0x00'
    return tx_id


def expect_event_not_emitted(tx_receipt: TransactionReceipt, event_name):
    assert event_name not in tx_receipt.events


def public_key2PKHash(public_key):
    if public_key.startswith('0x'):
        public_key_bytes = Web3.toBytes(hexstr=public_key)
    else:
        public_key_bytes = codecs.decode(public_key, 'hex')
    # Run SHA256 for the public key
    sha256_bpk_digest = hashlib.sha256(public_key_bytes).digest()
    # Run ripemd160 for the SHA256
    ripemd160_bpk = hashlib.new('ripemd160')
    ripemd160_bpk.update(sha256_bpk_digest)
    ripemd160_bpk_digest = ripemd160_bpk.hexdigest()
    return '0x' + ripemd160_bpk_digest


class AccountTracker:
    def __init__(self, account: LocalAccount):
        self.account = account
        self.height = chain.height

    def balance(self):
        self.height = chain.height
        return self.account.balance()

    def update_height(self):
        self.height = chain.height

    def delta(self, exclude_tx_fee=True):
        total_tx_fee = 0
        if exclude_tx_fee:
            tx: TransactionReceipt
            for tx in history:
                if tx.sender.address == self.account.address:
                    if self.height < tx.block_number <= chain.height:
                        total_tx_fee += tx.gas_price * tx.gas_used
        previous_balance = web3.eth.get_balance(self.account.address, self.height)
        self.height = chain.height
        return self.account.balance() - previous_balance + total_tx_fee


def get_tracker(account: LocalAccount) -> AccountTracker:
    return AccountTracker(account)


def padding_left(hex_str, length):
    return '0x' + hex_str[2:].zfill(length)


def encode_args_with_signature(function_signature: str, args: list) -> str:
    selector = Web3.keccak(text=function_signature)[:4].hex()
    args_in_function_signature = function_signature[function_signature.index('(') + 1:-1].replace(' ', '').split(',')
    return selector + encode(args_in_function_signature, args).hex()


def expect_query(query_data, expect: dict):
    for k, v in expect.items():
        ex = query_data[k]
        assert ex == v, f'k:{k} {ex} != {v}'


def get_transaction_op_return_data(chain_id, agent_address, delegate_address, lock_data,
                                   core_fee=1, version=1):
    if lock_data is not None and len(str(lock_data)) == 10:
        hex_result = hex(lock_data)[2:]
        lock_time_hex = reverse_by_bytes(hex_result)
        op_return_data = lock_time_hex
        op_push_data = '6a'
    else:
        op_return_data = lock_data
        op_push_data = '6a4c'
    flag_hex = ''.join(format(ord(c), 'x') for c in 'SAT+').zfill(8)
    version_hex = format(int(version), 'x').zfill(2)
    chain_id_hex = format(int(chain_id), 'x').zfill(4)
    delegate_address_hex = str(delegate_address)[2:].lower().zfill(40)
    agent_address_hex = str(agent_address)[2:].lower().zfill(40)
    core_fee_hex = format(core_fee, 'x').zfill(2)
    data_hex = flag_hex + version_hex + chain_id_hex + delegate_address_hex + agent_address_hex + core_fee_hex + op_return_data
    op_push_bytes = hex(len(data_hex) // 2).replace('0x', '')
    return op_push_data + op_push_bytes + data_hex


def get_lock_script(lock_time, public_key, scrip_type='hash'):
    lock_scrip = "0x"
    hex_result = hex(lock_time)[2:]
    lock_time_hex = reverse_by_bytes(hex_result)
    if scrip_type == 'hash':
        public = public_key2PKHash(public_key)
        lock_scrip = "04" + lock_time_hex + "b17576a914" + public[2:] + "88ac"
    elif scrip_type == 'key':
        public = public_key
        lock_scrip = "04" + lock_time_hex + "b17521" + public + "ac"
    elif scrip_type == 'multi_sig':
        pass
    return lock_scrip


def reverse_by_bytes(value: str) -> str:
    if len(value) % 2 > 0:
        value = '0' + value
    return "".join(reversed([value[i: i + 2] for i in range(0, len(value), 2)]))


def get_btc_tx(value, chain_id, validator, delegator, script_type='hash', lock_data=1736956800, core_fee=1, version=1):
    hex_result = hex(value)[2:]
    btc_coin = reverse_by_bytes(hex_result).ljust(16, '0')
    op_return = get_transaction_op_return_data(chain_id, validator, delegator, lock_data, core_fee, version)
    if script_type == 'key':
        script_pub_key = output_script_pub_key["script_public_key"]
    else:
        script_pub_key = output_script_pub_key["script_public_key_hash"]
    script_pub_key_length = hex(len(script_pub_key) // 2).replace('0x', '')
    op_return_length = hex(len(op_return) // 2).replace('0x', '')
    btc_tx = delegate_btc_block_data[
                 'btc_tx_block_data'] + (f'03{btc_coin}{script_pub_key_length}{script_pub_key}'
                                         f'0000000000000000{op_return_length}{op_return}'
                                         f'4e930100000000001976a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac00000000')

    tx_id = get_transaction_txid(btc_tx)
    return btc_tx, tx_id


def remove_witness_data_from_raw_tx(btc_tx_hex, script_pubkey) -> str:
    raw_tx: str = btc_tx_hex
    if raw_tx[8:12] == '0001':
        raw_tx = raw_tx[:8] + raw_tx[12:]
        witness_data = raw_tx[raw_tx.index(script_pubkey) + len(script_pubkey): -8]
        raw_tx = raw_tx.replace(witness_data, '')
    return raw_tx


def get_block_info(height='latest'):
    return web3.eth.get_block(height)
