import random
import pathlib
import codecs
import hashlib
import ecdsa
import yaml

from web3 import Web3
from brownie.network.transaction import TransactionReceipt
from brownie.network.account import LocalAccount
from brownie import accounts, chain, web3, history
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


def get_mnemonic() -> str:
    current_path = pathlib.Path(__file__)
    config_file_path = current_path.parent.parent / "brownie-config.yaml"
    with open(config_file_path, "r") as f:
        data = yaml.load(f.read(), Loader=yaml.CLoader)
        return data['networks']['development']['cmd_settings']['mnemonic']


def get_private_key_by_idx(idx):
    account = accounts.from_mnemonic(get_mnemonic(), offset=idx)
    return account.private_key


def pk2public_key(pk, compressed=False):
    if pk.startswith('0x'):
        private_key_bytes = Web3.toBytes(hexstr=pk)
    else:
        private_key_bytes = codecs.decode(pk, 'hex')

    # Generating a public key in bytes using SECP256k1 & ecdsa library
    public_key_raw = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1).verifying_key
    public_key_bytes = public_key_raw.to_string()

    # Hex encoding the public key from bytes
    public_key_hex = codecs.encode(public_key_bytes, 'hex')

    # Bitcoin uncompressed public key begins with bytes 0x04 so we have to add the bytes at the start
    public_key = (b'04' + public_key_hex).decode('utf-8')
    if not compressed:
        return '0x' + public_key

    # Checking if the last byte is odd or even
    if ord(bytearray.fromhex(public_key[-2:])) % 2 == 0:
        public_key_compressed = '02'
    else:
        public_key_compressed = '03'
    # Add bytes 0x02 to the X of the key if even or 0x03 if odd
    public_key_compressed += public_key[2:66]
    return '0x' + public_key_compressed


def get_public_key_by_idx(idx: int, compressed=False):
    return pk2public_key(get_private_key_by_idx(idx), compressed)


def get_public_key_by_address(address, compressed=False):
    idx = [account.address for account in accounts].index(address)
    return get_public_key_by_idx(idx, compressed)


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
