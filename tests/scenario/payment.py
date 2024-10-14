import os
import time
import bitcoin.core
import hashlib
import random
from enum import Enum
from abc import ABC, abstractmethod
from bitcoin.wallet import CBitcoinSecret, P2PKHBitcoinAddress, P2SHBitcoinAddress, P2WSHBitcoinAddress, \
    P2WPKHBitcoinAddress
from bitcoin.core.key import CPubKey
from bitcoin.core.script import *
from ecdsa import SigningKey, SECP256k1
from . import payment
from eth_hash.auto import keccak
from ..delegate import get_btc_lst_transaction_op_return_data, get_transaction_op_return_data


class WalletStatus(Enum):
    ACTIVE = 1
    INACTIVE = 2


class BtcLSTLockWallet:
    def __init__(self):
        self.payment = None
        self.script_pubkey = None
        self.key = None
        self.hash = None
        self.payment_type = None
        self.status = 0

    def __repr__(self):
        return f"BtcLSTLockWallet(hash={self.hash}, payment_type={self.payment_type}, status={self.status})"

    def __eq__(self, other):
        return self.hash == other.hash and \
            self.payment_type == other.payment_type and \
            self.status == other.status

    def from_on_chain_data(self, tuple_data):
        self.hash = tuple_data[0]
        self.payment_type = tuple_data[1]
        self.status = tuple_data[2]

    def from_payment(self, payment, status=WalletStatus.ACTIVE.value):
        self.payment_type = payment.get_type()
        self.status = status

        # bytes32
        self.script_pubkey = payment.get_script_pubkey()
        self.key = payment.get_key()

        assert self.key is not None

        hash_bytes = payment.get_hash()
        self.hash = '0x' + hash_bytes.hex().zfill(64)

        self.payment = payment

    def get_payment(self):
        return self.payment

    def get_payment_type(self):
        return self.payment_type

    def get_script_pubkey(self):
        assert self.script_pubkey is not None
        return self.script_pubkey

    def get_key(self):
        return self.key

    def get_hash(self):
        return self.hash

    def is_active(self):
        return self.status == WalletStatus.ACTIVE

    def is_inactive(self):
        return self.status == WalletStatus.INACTIVE


# extended opcode
OP_CLTV = CScriptOp(0xb1)


# consistent with the on-chain definition
class PaymentType(Enum):
    UNKNOWN = 0
    P2PKH = 1
    P2SH = 2
    P2WPKH = 4
    P2WSH = 8
    P2TR = 16
    P2MS = 128


class Payment(ABC):
    def __init__(self):
        self.private_key, self.public_key = self.create_random_key_pair()

        self.address = None
        self.script_pubkey = None
        self.redeem_script = None
        self.sig_script = None
        self.witness = None
        self.type = PaymentType.UNKNOWN.value
        self.amount = 0

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def get_key(self):
        assert self.script_pubkey is not None
        return keccak(self.script_pubkey).hex()

    def set_amount(self, amount):
        self.amount = amount

    def get_amount(self):
        return self.amount

    def create_random_key_pair(self):
        private_key = os.urandom(32)  # bytes
        secret = CBitcoinSecret.from_secret_bytes(private_key)
        public_key = CPubKey(secret.pub)  # bytes
        return private_key, public_key

    def get_type(self):
        return self.type

    def is_invalid(self):
        return self.type == PaymentType.UNKNOWN.value

    def get_hash(self):
        assert False, f"Unsupported payment type:{self.__class__.__name__}"

    def get_script_pubkey(self):
        return self.script_pubkey

    def get_addr(self):
        return self.address

    def get_redeem_script(self):
        return self.redeem_script

    def get_sig_script(self):
        return self.sig_script

    def get_witness(self):
        return self.witness

    def build_redeem_script(self, **kwargs):
        self.redeem_script_type = kwargs["redeem_script_type"]
        # assert self.redeem_script_type is not None, f"Invalid redeem script type"

        PaymentClass = getattr(payment, self.redeem_script_type)
        if self.redeem_script_type == "P2PKH" or self.redeem_script_type == "P2WPKH":
            paymentInst = PaymentClass()
        else:
            paymentInst = PaymentClass(**kwargs)

        self.redeem_script = paymentInst.get_script_pubkey()
        assert self.redeem_script is not None, \
            f"Redeem script is None, tyep is {self.redeem_script_type}"


########### NON-WITNESS ###########
class P2MS(Payment):
    def __init__(self, **kwargs):
        super().__init__()
        self.type = PaymentType.P2MS.value

        m = kwargs.get("m", 2)
        n = kwargs.get("n", 3)

        private_keys = []
        public_keys = []
        for _ in range(n):
            privkey, pubkey = self.create_random_key_pair()
            private_keys.append(privkey)
            public_keys.append(pubkey)

        self.script_pubkey = CScript(
            [m] + public_keys + [n, OP_CHECKMULTISIG]
        )


class P2PKH(Payment):
    def __init__(self):
        super().__init__()
        self.type = PaymentType.P2PKH.value
        self.address = P2PKHBitcoinAddress.from_pubkey(self.public_key)
        # CScript([script.OP_DUP, script.OP_HASH160, pubkey_hash, script.OP_EQUALVERIFY, script.OP_CHECKSIG])
        self.script_pubkey = self.address.to_scriptPubKey()

    def get_hash(self):
        assert self.public_key is not None
        return bitcoin.core.Hash160(self.public_key)  # 20 bytes


class P2SH(Payment):
    def __init__(self, **kwargs):
        super().__init__()
        self.type = PaymentType.P2SH.value
        self.build_redeem_script(**kwargs)

        self.address = P2SHBitcoinAddress.from_redeemScript(self.redeem_script)
        # CScript([OP_HASH160, bitcoin.core.Hash160(redeem_script), OP_EQUAL])
        self.script_pubkey = self.address.to_scriptPubKey()
        self.address.to_redeemScript

    def get_hash(self):
        assert self.redeem_script is not None
        return bitcoin.core.Hash160(self.redeem_script)  # 20bytes


########### WITNESS VER 0 ###########
class P2WSH(Payment):
    def __init__(self, **kwargs):
        super().__init__()
        self.type = PaymentType.P2WSH.value

        redeem_script_type = kwargs["redeem_script_type"]
        if redeem_script_type == "P2WSH":
            kwargs["redeem_script_type"] = "P2MS"
        self.build_redeem_script(**kwargs)

        self.witness_script_hash = hashlib.sha256(self.redeem_script).digest()
        self.script_pubkey = CScript([
            OP_0,
            self.witness_script_hash
        ])
        self.address = P2WSHBitcoinAddress.from_scriptPubKey(self.script_pubkey)

    def get_hash(self):
        assert self.witness_script_hash is not None
        return self.witness_script_hash  # 32 bytes


class P2WPKH(Payment):
    def __init__(self):
        super().__init__()
        self.type = PaymentType.P2WPKH.value

        self.pubkey_hash = bitcoin.core.Hash160(self.public_key)
        self.script_pubkey = CScript([
            OP_0,
            self.pubkey_hash
        ])
        self.address = P2WPKHBitcoinAddress.from_scriptPubKey(self.script_pubkey)
        # CScript([script.OP_DUP, script.OP_HASH160, pubkey_hash, script.OP_EQUALVERIFY, script.OP_CHECKSIG])
        self.redeem_script = self.address.to_redeemScript()

    def get_hash(self):
        assert self.pubkey_hash is not None
        return self.pubkey_hash  # 20bytes


########### WITNESS VER 1 ###########
class P2TR(Payment):
    def __init__(self):
        super().__init__()
        self.type = PaymentType.P2TR.value

        self.taproot_pubkey = self.create_taproot_pubkey()  # 32 bytes

        self.script_pubkey = CScript([
            OP_1,
            self.taproot_pubkey
        ])

    def get_hash(self):
        assert self.taproot_pubkey is not None
        return self.taproot_pubkey  # 32bytes

    def create_random_key_pair(self):
        private_key = SigningKey.generate(curve=SECP256k1)
        public_key = private_key.get_verifying_key().to_string("compressed")

        return private_key, public_key

    def create_taproot_pubkey(self):
        return hashlib.sha256(self.public_key).digest()


class P2TR_PUBKEY(P2TR):
    def __init__(self):
        super().__init__()


class P2TR_SCRIPT(P2TR):
    def __init__(self):
        super().__init__()

    def create_taproot_pubkey(self):
        merkle_root = self.__build_merkle_root()  # bytes

        tweak = self.__build_taproot_tweak("TapTweak", self.public_key, merkle_root)
        tweaked_pubkey = int.from_bytes(self.public_key, 'big') + int.from_bytes(tweak, 'big')
        tweaked_pubkey = tweaked_pubkey % SECP256k1.order
        return tweaked_pubkey.to_bytes(32, 'big')

    def __random_build_merkle_node(self):
        # P2PKH P2MS P2SH-P2PKH, P2SH-P2MS, P2SH-P2WPKH, P2SH-P2WSH, P2WPKH, P2WSH ,P2WSH-P2MS
        avaliable_lock_script_list = ["P2PKH", "P2MS", "P2SH", "P2WPKH", "P2WSH"]
        avaliable_redeem_script_map = {
            "P2SH": ["P2PKH", "P2MS", "P2WPKH", "P2WSH"],
            "P2WSH": ["P2MS"]
        }

        lock_script_list = []
        merkle_nodes = []

        # build 4 ~ 8 lock scripts
        count = random.randint(4, 8)
        for i in range(count):
            lock_script_type = random.choice(avaliable_lock_script_list)
            redeem_script_type = None
            if avaliable_redeem_script_map.get(lock_script_type) is not None:
                redeem_script_type = random.choice(avaliable_redeem_script_map[lock_script_type])

            PaymentClass = getattr(payment, lock_script_type)

            if redeem_script_type is None:
                paymentInst = PaymentClass()
            else:
                paymentInst = PaymentClass(
                    redeem_script_type=redeem_script_type
                )

            script_pubkey = paymentInst.get_script_pubkey()
            redeem_script = paymentInst.get_redeem_script()

            lock_script_list.append({
                script_pubkey: script_pubkey,
                redeem_script: redeem_script
            })

            merkle_nodes.append(self.__build_node_hash(script_pubkey))

        return merkle_nodes

    def __build_node_hash(self, script_pubkey, version="c0"):
        return hashlib.sha256(bytes.fromhex(version) + script_pubkey)

    def __build_merkle_root(self):
        merkle_nodes = self.__random_build_merkle_node()
        assert merkle_nodes is not None, f"Script list is None"

        node_count = len(merkle_nodes)
        nodes = merkle_nodes

        while node_count > 1:
            for i in range(0, node_count, 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < node_count else left

                # reuse nodes
                # (i,i+1) -> i/2
                nodes[i // 2] = hashlib.sha256(hashlib.sha256(left.digest() + right.digest()).digest())
            node_count //= 2

        return nodes[0].digest()

    def __build_taproot_tweak(self, tag, public_key, merkle_root):
        assert len(public_key) == 33 and len(merkle_root) == 32, \
            f"Invalid pubkey or merkle root"

        tag_hash = hashlib.sha256(tag.encode("utf-8")).digest()
        h = hashlib.sha256()
        h.update(tag_hash)
        h.update(tag_hash)
        h.update(public_key)
        h.update(merkle_root)

        return h.digest()


import struct


########### CLTV_PAYMENT ###########
class CLTV_SCRIPT(Payment):
    def __init__(self, **kwargs):
        super().__init__()
        lock_timestamp = kwargs.get("lock_timestamp", int(time.time()))
        self.lock_timestamp = struct.pack('I', lock_timestamp)


class CLTV_P2PK(CLTV_SCRIPT):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.script_pubkey = CScript([
            self.lock_timestamp,
            OP_CLTV,
            OP_DROP,
            self.public_key,
            OP_CHECKSIG
        ])


class CLTV_P2PKH(CLTV_SCRIPT):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        pubkey_hash = bitcoin.core.Hash160(self.public_key)
        self.script_pubkey = CScript([
            self.lock_timestamp,
            OP_CLTV,
            OP_DROP,
            OP_DUP,
            OP_HASH160,
            pubkey_hash,
            OP_EQUALVERIFY,
            OP_CHECKSIG
        ])


class CLTV_P2MS(CLTV_SCRIPT):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        m = kwargs.get("m", random.randint(2, 3))
        n = kwargs.get("n", random.randint(m + 1, m * 2 - 1))

        private_keys = []
        public_keys = []
        for _ in range(n):
            privkey, pubkey = self.create_random_key_pair()
            private_keys.append(privkey)
            public_keys.append(pubkey)

        self.script_pubkey = CScript([
                                         self.lock_timestamp,
                                         OP_CLTV,
                                         OP_DROP,
                                         m] + public_keys + [n,
                                                             OP_CHECKMULTISIG
                                                             ])


########## OP_RETURN ###########
class STAKE_OP_RETURN(Payment):
    def __init__(self, **kwargs):
        chain_id = kwargs.get("chain_id", 1112)
        delegator = kwargs["delegator"]
        delegatee = kwargs["delegatee"]
        lock_timestamp_hex = kwargs["lock_timestamp"].to_bytes(4, byteorder='little').hex()
        fee = kwargs.get("fee", 1)

        assert delegator is not None and delegatee is not None, \
            f"Invalid delegator or delegatee"

        print(f"lock_timestamp_hex={lock_timestamp_hex}")
        op_return_hex = get_transaction_op_return_data(chain_id, delegatee, delegator, lock_timestamp_hex, fee)

        self.script_pubkey = CScript([
            OP_RETURN,
            bytes.fromhex(op_return_hex)
        ])

    def get_redeem_script(self):
        pass


class LST_OP_RETURN(Payment):
    def __init__(self, **kwargs):
        version = 2
        chain_id = kwargs.get("chain_id", 1112)
        fee = kwargs.get("fee", 1)
        delegator = kwargs["delegator"]
        op_return_hex = get_btc_lst_transaction_op_return_data(delegator, fee, version, chain_id)

        self.script_pubkey = CScript([
            OP_RETURN,
            bytes.fromhex(op_return_hex)
        ])

    def get_redeem_script(self):
        pass
