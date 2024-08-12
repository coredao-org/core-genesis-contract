import random
from abc import ABC, abstractmethod
from bitcoin.core import CTransaction, CTxIn, CTxOut, lx, b2lx, COutPoint
from . import payment
from . import constants


class BitcoinTx(ABC):
    def __init__(self):
        self.tx = None
        self.txid = None
        self.lock_output_payment = None
        self.lock_output_script_pubkey = None
        self.lock_output_redeem_script = None
        self.op_return = None
        self.delegator = None
        self.relayer = None
        self.amount = 0
        self.fee = 0
        self.lock_output_index = 0
        self.round = 0
        self.block_time = 0
        self.block_number = 0

    def __repr__(self):
        return f"{self.__class__.__name__}(delegator={self.delegator},amount={self.amount},output_index={self.lock_output_index},fee={self.fee})"

    def get_txid(self):
        return self.txid

    def get_delegator(self):
        return self.delegator

    def get_amount(self):
        return self.amount

    def set_lock_output_payment(self, output_payment):
        self.lock_output_payment = output_payment

    def get_lock_output_payment(self):
        return self.lock_output_payment

    def get_lock_output_index(self):
        return self.lock_output_index

    def get_fee(self):
        return self.fee

    def get_round(self):
        return self.round

    def set_round(self, round):
        self.round = round

    def get_relayer(self):
        return self.relayer

    def set_relayer(self, relayer):
        self.relayer = relayer

    def get_block_time(self):
        return self.block_time

    def set_block_time(self, block_time):
        self.block_time = block_time

    def get_block_number(self):
        return self.block_number

    def set_block_number(self, block_number):
        self.block_number = block_number

    def build_inputs(self):
        vin = []
        input_count = random.randint(1, 3)
        for i in range(input_count):
            # fake prevout
            ch = random.choice('123456789abcdef')
            prevout_txid = lx(ch * 64)
            # default scriptSig and nSequence
            txin = CTxIn(COutPoint(prevout_txid, i))
            vin.append(txin)

        return vin

    def build_pay_output(self, amount, payment_type, **kwargs):
        txout, script_pubkey, redeem_script, payment_inst = self.build_output(amount, payment_type, **kwargs)

        self.lock_output_script_pubkey = script_pubkey
        self.lock_output_redeem_script = redeem_script
        self.lock_output_payment = payment_inst
        return txout

    def build_change_output(self):
        amount = random.randint(0, constants.CHANGE_OUTPUT_MAX_AMOUNT)
        if amount == 0:
            return None

        payment_inst = payment.P2PKH()
        script_pubkey = payment_inst.get_script_pubkey()
        return CTxOut(amount, script_pubkey)

    def build_op_return(self, **kwargs):
        pass

    def build(self, amount, payment_type, **kwargs):
        vin = self.build_inputs()
        vout = []

        # lock output
        lock_output = self.build_pay_output(amount, payment_type, **kwargs)

        # change output
        change_output = self.build_change_output()

        if random.randint(0, 1) == 0:
            vout.append(lock_output)
            lock_output_index = 0
            if change_output is not None:
                vout.append(change_output)
        else:
            if change_output is not None:
                vout.append(change_output)
            vout.append(lock_output)
            lock_output_index = len(vout) - 1

        # op_reutn output
        op_return_output = self.build_op_return(**kwargs)
        vout.append(op_return_output)

        self.tx = CTransaction(vin, vout)
        self.txid = self.tx.GetTxid()
        self.lock_output_index = lock_output_index

    def build_output(self, amount, payment_type, **kwargs):
        PaymentClass = getattr(payment, payment_type)
        redeem_script_type = kwargs.get("redeem_script_type")
        if redeem_script_type is None:
            payment_inst = PaymentClass()
        else:
            payment_inst = PaymentClass(**kwargs)

        script_pubkey = payment_inst.get_script_pubkey()
        redeem_script = payment_inst.get_redeem_script()

        assert script_pubkey is not None, \
            f"Build scriptPubkey fail, payment type is {payment_type}"

        return CTxOut(amount, script_pubkey), script_pubkey, redeem_script, payment_inst


class StakeTx(BitcoinTx):
    def __init__(self, delegator, delegatee, amount, payment_type, **kwargs):
        super().__init__()

        self.delegator = delegator
        self.delegatee = delegatee
        self.amount = int(amount)
        self.fee = kwargs.get("fee", 1)
        self.lock_time = kwargs["lock_timestamp"]
        self.removed = False
        self.build(
            amount,
            payment_type,
            **kwargs
        )

    def __repr__(self):
        return f"{self.__class__.__name__}(delegator={self.delegator},delegatee={self.delegatee},amount={self.amount},output_index={self.lock_output_index},lock_time={self.lock_time},fee={self.fee})"

    def remove(self):
        self.removed = True

    def is_removed(self):
        return self.removed

    def get_delegatee(self):
        return self.delegatee

    def set_delegatee(self, delegatee):
        self.delegatee = delegatee

    def get_lock_time(self):
        return self.lock_time

    def build_op_return(self, **kwargs):
        script_pubkey = payment.STAKE_OP_RETURN(
            delegator=self.delegator,
            delegatee=self.delegatee,
            **kwargs
        ).get_script_pubkey()
        assert script_pubkey is not None, f"Build scriptPubkey fail"

        self.op_return = script_pubkey
        return CTxOut(0, script_pubkey)


class LSTStakeTx(BitcoinTx):
    def __init__(self, delegator, amount, payment_type, **kwargs):
        super().__init__()

        self.delegator = delegator
        self.amount = int(amount)
        self.fee = kwargs.get("fee", 1)
        self.build(
            amount,
            payment_type,
            **kwargs
        )

    def build_op_return(self, **kwargs):
        script_pubkey = payment.LST_OP_RETURN(
            delegator=self.delegator,
            **kwargs
        ).get_script_pubkey()
        assert script_pubkey is not None, f"Build scriptPubkey fail"

        self.op_return = script_pubkey
        return CTxOut(0, script_pubkey)


class LSTUnstakeTx(BitcoinTx):
    def __init__(self, utxos, amount, payment, wallet):
        super().__init__()
        self.output_payments = []

        vin, total_amount = self.build_inputs(utxos)
        vout = self.build_outputs(total_amount, amount, payment, wallet)

        self.tx = CTransaction(vin, vout)
        self.txid = self.tx.GetTxid()
        self.amount = amount
        self.vin = vin

    def __repr__(self):
        return f"{self.__class__.__name__}(txid={self.txid},prevout_txid={self.prevout_txid},prevout_index={self.prevout_index},output_index={self.lock_output_index},amount={self.amount})"

    def get_output_payments(self):
        return self.output_payments

    def get_vin(self):
        return self.vin

    def build_inputs(self, utxos):
        vin = []
        total_amount = 0
        for utxo in utxos.values():
            total_amount += utxo.get_amount()
            txin = CTxIn(COutPoint(utxo.get_txid(), utxo.get_index()))
            vin.append(txin)

        return vin, total_amount

    def build_outputs(self, total_amount, amount, payment, wallet):
        vout = []

        # lock output
        lock_output = CTxOut(amount, payment.get_script_pubkey())
        vout.append(lock_output)

        payment.set_amount(amount)
        self.output_payments.append(payment)

        # change output
        change_amount = total_amount - amount
        if change_amount > 0:
            change_output = CTxOut(change_amount, wallet.get_script_pubkey())
            vout.append(change_output)
            self.change_output_index = 1
            assert wallet.get_payment() is not None
            wallet.get_payment().set_amount(change_amount)
            self.output_payments.append(wallet.get_payment())

        self.lock_output_index = 0
        self.lock_output_payment = payment

        return vout
