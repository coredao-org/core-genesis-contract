import random
import codecs
import hashlib

from web3 import Web3
from brownie.network.transaction import TransactionReceipt
from brownie.network.account import LocalAccount
from brownie import chain, web3, history
from eth_account import Account
from eth_abi import encode


def random_address():
    return Account.create(str(random.random())).address


def expect_event(tx_receipt: TransactionReceipt, event_name, event_value: dict = None, idx=0):
    assert event_name in tx_receipt.events

    if event_value is None:
        return

    # fetch event by idx
    event = tx_receipt.events[event_name][idx]
    for k, v in event_value.items():
        assert event[k] == v


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
