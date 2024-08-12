import codecs
from bitcoinlib.keys import *
from web3 import Web3
from brownie.network.transaction import TransactionReceipt
from brownie.network.account import LocalAccount
from eth_account import Account
from hashlib import sha256
from eth_abi import encode
from brownie import *
from Crypto.Hash import keccak
import ecdsa
from tests.constant import *
import binascii


def random_address():
    return Account.create(str(random.random())).address


def random_btc_tx_id():
    rand_bytes = random.randbytes(32)
    tx_id = sha256(sha256(rand_bytes).digest()).hexdigest()
    return '0x' + tx_id


def generate_private_key():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    private_key_hex = sk.to_string().hex()
    return private_key_hex


def get_public_key(private_key_hex):
    private_key_bytes = bytes.fromhex(private_key_hex)
    sk = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
    vk = sk.get_verifying_key()
    public_key_coordinates = (vk.pubkey.point.x(), vk.pubkey.point.y())
    prefix = '02' if (public_key_coordinates[1] & 1) == 0 else '03'
    compressed_public_key_hex = prefix + public_key_coordinates[0].to_bytes(32, byteorder='big').hex()
    return compressed_public_key_hex


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


class AccountTracker:
    def __init__(self, account: LocalAccount):
        self.account = account
        self.height = chain.height
        self.address = account.address

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


def get_trackers(accounts: list):
    delegators = []
    for account in accounts:
        tracker = AccountTracker(account)
        delegators.append(tracker)
    return delegators


def assert_trackers(trackers: AccountTracker, expect_reward):
    if isinstance(trackers, list):
        for index, tracker in enumerate(trackers):
            reward = tracker.delta()
            actual_reward = expect_reward[index]
            assert reward == actual_reward, f'assert_trackers error address: {tracker.address}:claimed_reward :{reward}, expect_reward:{actual_reward}'
    else:
        assert trackers.delta() == expect_reward


def padding_left(hex_str, length):
    return '0x' + hex_str[2:].zfill(length)


def encode_args_with_signature(function_signature: str, args: list) -> str:
    selector = function_signature.split('(')[0]
    types = function_signature.split('(')[-1].split(',')
    sr = ', '
    new_args = []
    for index, a in enumerate(args):
        if types[index].replace(')', '') == 'address':
            new_args.append(str(a).lower())
        else:
            new_args.append(str(a))
    error1 = sr.join(new_args)
    error = f"{selector}: {error1}"
    return error


def expect_query(query_data, expect: dict):
    for k, v in expect.items():
        ex = query_data[k]
        assert ex == v, f'k:{k} {ex} != {v}'


def reverse_by_bytes(value: str) -> str:
    if len(value) % 2 > 0:
        value = '0' + value
    return "".join(reversed([value[i: i + 2] for i in range(0, len(value), 2)]))


def remove_witness_data_from_raw_tx(btc_tx_hex, script_pubkey) -> str:
    raw_tx: str = btc_tx_hex
    if raw_tx[8:12] == '0001':
        raw_tx = raw_tx[:8] + raw_tx[12:]
        witness_data = raw_tx[raw_tx.index(script_pubkey) + len(script_pubkey): -8]
        raw_tx = raw_tx.replace(witness_data, '')
    return raw_tx


def get_block_info(height='latest'):
    return web3.eth.get_block(height)


def update_system_contract_address(update_contract,
                                   candidate_hub=None,
                                   btc_light_client=None,
                                   gov_hub=None,
                                   relay_hub=None,
                                   slash_indicator=None,
                                   system_reward=None,
                                   validator_set=None,
                                   pledge_agent=None,
                                   burn=None,
                                   foundation=None,
                                   stake_hub=None,
                                   btc_stake=None,
                                   btc_agent=None,
                                   btc_lst_stake=None,
                                   core_agent=None,
                                   hash_power_agent=None,
                                   lst_token=None
                                   ):
    if candidate_hub is None:
        candidate_hub = CandidateHubMock[0]
    if btc_light_client is None:
        btc_light_client = BtcLightClientMock[0]
    if gov_hub is None:
        gov_hub = GovHubMock[0]
    if relay_hub is None:
        relay_hub = RelayerHubMock[0]
    if slash_indicator is None:
        slash_indicator = SlashIndicatorMock[0]
    if system_reward is None:
        system_reward = SystemRewardMock[0]
    if validator_set is None:
        validator_set = ValidatorSetMock[0]
    if pledge_agent is None:
        pledge_agent = PledgeAgentMock[0]
    if burn is None:
        burn = Burn[0]
    if foundation is None:
        foundation = Foundation[0]
    if stake_hub is None:
        stake_hub = StakeHubMock[0]
    if btc_stake is None:
        btc_stake = BitcoinStakeMock[0]
    if btc_agent is None:
        btc_agent = BitcoinAgentMock[0]
    if btc_lst_stake is None:
        btc_lst_stake = BitcoinLSTStakeMock[0]
    if core_agent is None:
        core_agent = CoreAgentMock[0]
    if hash_power_agent is None:
        hash_power_agent = HashPowerAgentMock[0]
    if lst_token is None:
        lst_token = BitcoinLSTToken[0]

    contracts = [
        validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub, gov_hub,
        pledge_agent, burn, foundation, stake_hub, btc_stake, btc_agent, btc_lst_stake, core_agent, hash_power_agent,
        lst_token
    ]
    args = encode(['address'] * len(contracts), [c.address for c in contracts])
    getattr(update_contract, "updateContractAddr")(args)


def keccak_hash256(data):
    keccak_hash = keccak.new(digest_bits=256)
    a_bytes = bytes.fromhex(data.replace('0x', ''))
    keccak_hash.update(a_bytes)
    hexdigest = keccak_hash.hexdigest()
    return hexdigest


def hash160(v):
    sha = hashlib.sha256()
    sha.update(v)
    v = sha.digest()
    return hashlib.new("ripemd160", v).digest()


def btc_value_2hex(amount):
    amount_hex = reverse_by_bytes(hex(amount)[2:]).ljust(16, '0')
    return amount_hex


def op2hex(op_value: int) -> str:
    r = remove_0x(hex(op_value))
    if len(r) == 1:
        return '0' + r
    return r


def remove_0x(hex_str):
    hex_str = str(hex_str)
    if hex_str.startswith('0x'):
        return hex_str[2:]
    return hex_str


def value2hex(value):
    if isinstance(value, int):
        value_hex = hex(value)
    hex_str = remove_0x(value_hex)
    return hex_str


def format_number(vout):
    formatted_number = f"{vout:02}"
    result = formatted_number + "000000"
    return result


def public_key_2pkhash(public_key):
    if public_key.startswith('0x'):
        public_key_bytes = Web3.to_bytes(hexstr=public_key)
    else:
        public_key_bytes = codecs.decode(public_key, 'hex')
    # Run SHA256 for the public key
    sha256_bpk_digest = hashlib.sha256(public_key_bytes).digest()
    # Run ripemd160 for the SHA256
    ripemd160_bpk = hashlib.new('ripemd160')
    ripemd160_bpk.update(sha256_bpk_digest)
    ripemd160_bpk_digest = ripemd160_bpk.hexdigest()
    return '0x' + ripemd160_bpk_digest


def bytes_to_hex_string(byte_data: bytes) -> str:
    return binascii.hexlify(byte_data).decode('utf-8')


def index_bytes32(data: bytes, start: int, length: int) -> bytes:
    return data[start:start + length]


def extract_pk_script_addr(pk_script: bytes):
    length = len(pk_script)
    if length == 25:
        # pay-to-pubkey-hash
        if (pk_script[0] == Opcode.OP_DUP and pk_script[1] == Opcode.OP_HASH160 and
                pk_script[2] == Opcode.OP_DATA_20 and pk_script[23] == Opcode.OP_EQUALVERIFY
                and pk_script[24] == Opcode.OP_CHECKSIG):
            return index_bytes32(pk_script, 3, 20), AddressType.TYPE_P2PKH
    elif length == 23:
        # pay-to-script-hash
        if (pk_script[0] == Opcode.OP_HASH160 and pk_script[1] == Opcode.OP_DATA_20
                and pk_script[22] == Opcode.OP_EQUAL):
            return index_bytes32(pk_script, 2, 20), AddressType.TYPE_P2SH
    elif length == 22:
        # pay-to-witness-pubkey-hash
        if pk_script[0] == Opcode.OP_0 and pk_script[1] == Opcode.OP_DATA_20:
            return index_bytes32(pk_script, 2, 20), AddressType.TYPE_P2WPKH
    elif length == 34:
        # pay-to-witness-script-hash
        if pk_script[0] == Opcode.OP_0 and pk_script[1] == Opcode.OP_DATA_32:
            return index_bytes32(pk_script, 2, 32), AddressType.TYPE_P2WSH
        # pay-to-taproot
        if pk_script[0] == Opcode.OP_1 and pk_script[1] == Opcode.OP_DATA_32:
            return index_bytes32(pk_script, 2, 32), AddressType.TYPE_P2TAPROOT

    return b'\x00' * 20, AddressType.TYPE_UNKNOWN


def get_asset_weight(asset):
    if asset == 'coin':
        return AssetWeight.CORE_WEIGHT
    elif asset == 'power':
        return AssetWeight.POWER_WEIGHT
    elif asset == 'btc':
        return AssetWeight.BTC_WEIGHT
    else:
        return None
