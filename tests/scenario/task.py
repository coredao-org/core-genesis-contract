from abc import ABC, abstractmethod
from brownie import *
import random
import time
import rlp
from . import bitcoin_tx
from . import payment
from . import task_handler
from . import constants
from .account_mgr import AccountMgr
from .payment import BtcLSTLockWallet

get_sponsor_addr = AccountMgr.get_sponsor_addr
get_sponsee_addr = AccountMgr.get_sponsee_addr
get_operator_addr = AccountMgr.get_operator_addr
get_consensus_addr = AccountMgr.get_consensus_addr
get_fee_addr = AccountMgr.get_fee_addr
get_delegator_addr = AccountMgr.get_delegator_addr
get_contract_addr = AccountMgr.get_contract_addr


class Task(ABC):
    @abstractmethod
    def pre_execute(self, params):
        assert self.chain is not None
        self.params = params
        self.state_trackers = []

        self.init_task_handler()

    def is_supported(self, advanced_round):
        return advanced_round > 0

    def set_round(self, round):
        self.round = round

    def set_chain_state(self, chain):
        self.chain = chain

    @abstractmethod
    def execute(self):
        print(f"\r\nRound {self.round}: Execute task {self.__class__.__name__} ({self.params})")

    def init_task_handler(self):
        HandlerClass = getattr(task_handler, self.__class__.__name__)
        self.handler = HandlerClass()
        self.handler.set_chain(self.chain)
        self.handler.set_task(self)
        self.handler.init_handler()
        self.handler.init_checker()

    def notify_task_ready(self):
        self.handler.on_task_ready()

    def notify_task_finish(self):
        self.handler.on_task_finish()

    def post_execute(self):
        pass


class SponsorFund(Task):
    def is_supported(self, advanced_round):
        return True

    def pre_execute(self, params):
        super().pre_execute(params)

        self.sponsor = get_sponsor_addr("S1")

        assert len(params) >= 1, f"Invalid params"
        self.sponsee = get_sponsee_addr(params[0])

        amount = params[1] if len(params) == 2 else random.randint(1, 100)
        self.amount = int(amount * constants.CORE_DECIMALS)

        assert self.amount <= self.sponsor.balance() // 2, \
            f"The amount is too large, {self.amount}, {self.sponsor.balance() // 2}"

    def execute(self):
        super().execute()
        self.notify_task_ready()
        self.sponsor.transfer(self.sponsee, self.amount)
        self.notify_task_finish()


class RegisterCandidate(Task):
    def is_supported(self, advanced_round):
        return True

    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 2, "Invalid params"
        self.operator_addr = get_operator_addr(params[0])
        self.commission = params[1]
        self.margin = int(params[2] * constants.CORE_DECIMALS) if len(params) == 3 else CandidateHubMock[
            0].requiredMargin()
        self.consensus_addr = get_consensus_addr(params[0])
        self.fee_addr = get_fee_addr(params[0])

    def execute(self):
        super().execute()
        self.notify_task_ready()

        CandidateHubMock[0].register(
            self.consensus_addr,
            self.fee_addr,
            self.commission, {
                'from': self.operator_addr,
                'value': self.margin
            }
        )

        self.notify_task_finish()


class UnregisterCandidate(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, f"Invalid params"
        self.operator_addr = get_operator_addr(params[0])

    def execute(self):
        super().execute()
        self.notify_task_ready()

        candidate = self.chain.get_candidate(self.operator_addr)
        CandidateHubMock[0].unregister(
            {
                'from': self.operator_addr
            }
        )

        self.notify_task_finish()


class SlashValidator(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 2, "Invalid params"

        self.operator_addr = get_operator_addr(params[0])
        self.consensus_addr = \
            self.chain.get_candidate(self.operator_addr).get_consensus_addr()
        self.slash_count = params[1]

    def execute(self):
        super().execute()

        for i in range(self.slash_count):
            self.notify_task_ready()
            tx = SlashIndicatorMock[0].slash(self.consensus_addr)
            self.block_number = tx.block_number
            self.notify_task_finish()


class AddMargin(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) > 0, f"Invalid params"

        self.operator_addr = get_operator_addr(params[0])
        self.amount = int(params[1] * constants.CORE_DECIMALS) if len(params) == 2 else CandidateHubMock[
            0].requiredMargin()

    def execute(self):
        super().execute()

        self.notify_task_ready()
        CandidateHubMock[0].addMargin({
            "value": self.amount,
            "from": self.operator_addr
        })
        self.notify_task_finish()


class RefuseDelegate(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, f"Invalid params"
        self.operator_addr = get_operator_addr(params[0])

    def execute(self):
        super().execute()
        self.notify_task_ready()
        CandidateHubMock[0].refuseDelegate({
            "from": self.operator_addr
        })
        self.notify_task_finish()


class AcceptDelegate(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, f"Invalid params"
        self.operator_addr = get_operator_addr(params[0])

    def execute(self):
        super().execute()
        self.notify_task_ready()
        CandidateHubMock[0].acceptDelegate({
            "from": self.operator_addr
        })
        self.notify_task_finish()


class GenerateBlock(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, "Invalid params"
        self.block_count = params[0]
        self.sponsor = get_sponsor_addr("S0")

    def execute(self):
        super().execute()

        # get consensus address list
        miners = ValidatorSetMock[0].getValidators()
        miner_count = len(miners)

        for i in range(self.block_count):
            self.miner = miners[i % miner_count]
            self.tx_fee = int(random.uniform(0.01, 2) * constants.CORE_DECIMALS)
            self.notify_task_ready()
            tx = ValidatorSetMock[0].deposit(
                self.miner, {
                    "value": self.tx_fee,
                    "from": self.sponsor
                })
            self.block_number = tx.block_number
            print(f"slash count: {i}")
            self.notify_task_finish()


class TurnRound(Task):
    def is_supported(self, advanced_round):
        return True

    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, "Invalid params"
        self.count = self.params[0]

    def execute(self):
        super().execute()

        for i in range(self.count):
            self.notify_task_ready()
            CandidateHubMock[0].turnRound()
            self.round += 1
            self.notify_task_finish()


class StakeCore(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 3, f"Invalid params"
        self.delegator = get_delegator_addr(params[0])
        self.delegatee = get_operator_addr(params[1])
        self.amount = int(params[2] * constants.CORE_DECIMALS)

    def execute(self):
        super().execute()
        self.notify_task_ready()
        tx = CoreAgentMock[0].delegateCoin(
            self.delegatee, {
                "value": self.amount,
                "from": self.delegator
            })
        self.notify_task_finish()


class UnstakeCore(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 3, f"Invalid params"
        self.delegator = get_delegator_addr(params[0])
        self.delegatee = get_operator_addr(params[1])
        self.amount = int(params[2] * constants.CORE_DECIMALS)

    def execute(self):
        super().execute()
        self.notify_task_ready()
        tx = CoreAgentMock[0].undelegateCoin(
            self.delegatee,
            self.amount, {
                "from": self.delegator
            })
        self.notify_task_finish()


class TransferCore(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 4, f"Invalid params"
        self.delegator = get_delegator_addr(params[0])
        self.from_delegatee = get_operator_addr(params[1])
        self.to_delegatee = get_operator_addr(params[2])
        self.amount = int(params[3] * constants.CORE_DECIMALS)

    def execute(self):
        super().execute()
        self.notify_task_ready()
        tx = CoreAgentMock[0].transferCoin(
            self.from_delegatee,
            self.to_delegatee,
            self.amount, {
                "from": self.delegator
            })
        self.notify_task_finish()


class StakePower(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) > 2, f"Invalid params"
        self.delegatee = get_operator_addr(params[0])

        lagged_round = params[1]
        assert lagged_round >= 0 and lagged_round < 7
        self.power_round = self.round - lagged_round

        self.miners = []
        for i in range(2, len(params)):
            self.miners.append(get_delegator_addr(params[i]))

    def execute(self):
        super().execute()
        self.notify_task_ready()
        BtcLightClientMock[0].setMiners(
            self.power_round,
            self.delegatee,
            self.miners
        )
        self.notify_task_finish()


class CreateStakeLockTx(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 7, f"Invalid params"
        self.storage_key = params[0]
        self.delegator = get_delegator_addr(params[1])
        self.delegatee = get_operator_addr(params[2])
        self.amount = params[3] * constants.BTC_DECIMALS
        self.locked_round = params[4]
        self.payment_type = params[5]
        self.redeem_script_type = params[6]

        assert self.payment_type == "P2SH" or self.payment_type == "P2WSH", \
            f"Invalid payment {self.payment_type}"

        assert self.redeem_script_type == "CLTV_P2PK" or self.redeem_script_type == "CLTV_P2PKH" or \
               self.redeem_script_type == "CLTV_P2MS", f"Invalid redeem script {self.redeem_script_type}"

    def execute(self):
        super().execute()

        lock_timestamp = (self.round + self.locked_round) * constants.ROUND_SECONDS + 1
        fee = random.randint(0, 255)

        self.notify_task_ready()
        txobj = bitcoin_tx.StakeTx(
            self.delegator,
            self.delegatee,
            self.amount,
            self.payment_type,
            redeem_script_type=self.redeem_script_type,
            lock_timestamp=lock_timestamp,
            fee=fee
        )

        self.chain.add_btc_tx(self.storage_key, txobj)
        self.notify_task_finish()


class CreateLSTLockTx(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 4, f"Invalid params"
        self.storage_key = params[0]
        self.delegator = get_delegator_addr(params[1])
        self.amount = int(params[2] * constants.BTC_DECIMALS)
        self.payment_type = params[3]
        self.redeem_script_type = params[4] if len(params) == 5 else None

    def execute(self):
        super().execute()

        fee = random.randint(0, 255)
        self.notify_task_ready()
        txobj = bitcoin_tx.LSTStakeTx(
            self.delegator,
            self.amount,
            self.payment_type,
            redeem_script_type=self.redeem_script_type,
            fee=fee
        )
        self.chain.add_btc_tx(self.storage_key, txobj)
        self.notify_task_finish()


class ConfirmBtcTx(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 2, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)

        self.tx = tx_data.tx
        self.check_time = params[1] * 60 + self.round * constants.ROUND_SECONDS
        self.tx_data = tx_data

    def execute(self):
        super().execute()
        self.notify_task_ready()
        BtcLightClientMock[0].setCheckResult(True, self.check_time)
        self.tx_data.set_block_time(self.check_time)
        self.notify_task_finish()


class StakeBtc(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 2, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)

        self.tx = tx_data.tx
        self.redeem_script = tx_data.lock_output_redeem_script
        self.op_return = tx_data.op_return
        self.relayer = get_delegator_addr(params[1])
        self.tx_data = tx_data

    def execute(self):
        super().execute()

        fake_block_height = 100
        fake_merkle_nodes = []
        fake_tx_index = 0

        self.notify_task_ready()
        print(f"redeem_script={self.redeem_script.hex()}")
        tx = BitcoinStakeMock[0].delegate(
            self.tx.serialize().hex(),
            fake_block_height,
            fake_merkle_nodes,
            fake_tx_index,
            self.redeem_script, {
                'from': self.relayer
            })
        self.tx_data.set_block_number(tx.block_number)
        self.tx_data.set_relayer(self.relayer)
        self.notify_task_finish()


class TransferBtc(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 3, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)
        self.txid = tx_data.txid
        self.delegator = get_delegator_addr(params[1])
        self.to_delegatee = get_operator_addr(params[2])
        self.tx_data = tx_data

    def execute(self):
        super().execute()

        self.notify_task_ready()
        BitcoinStakeMock[0].transfer(
            self.txid,
            self.to_delegatee, {
                'from': self.delegator
            })
        self.notify_task_finish()


class AddWallet(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 1, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)

        self.tx = tx_data.tx
        self.script_pubkey = tx_data.lock_output_script_pubkey
        self.payment = tx_data.lock_output_payment

    def execute(self):
        super().execute()

        self.notify_task_ready()
        BitcoinLSTStakeMock[0].updateParam(
            'add',
            self.script_pubkey,
            {'from': GovHubMock[0].address}
        )
        self.notify_task_finish()


class StakeLSTBtc(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 2, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)

        self.tx = tx_data.tx
        self.script_pubkey = tx_data.lock_output_script_pubkey
        self.relayer = get_delegator_addr(params[1])
        self.auto_add_wallet = False
        if len(params) == 3:
            self.auto_add_wallet = bool(params[2])

        self.tx_data = tx_data

    def execute(self):
        super().execute()

        fake_block_height = 100
        fake_merkle_nodes = []
        fake_tx_index = 0

        if self.auto_add_wallet:
            BitcoinLSTStakeMock[0].updateParam(
                'add',
                self.script_pubkey,
                {'from': GovHubMock[0].address}
            )
            time.sleep(1)

        self.notify_task_ready()
        tx = BitcoinLSTStakeMock[0].delegate(
            self.tx.serialize().hex(),
            fake_block_height,
            fake_merkle_nodes,
            fake_tx_index,
            self.script_pubkey, {
                'from': self.relayer
            })

        self.tx_data.set_block_number(tx.block_number)
        self.tx_data.set_relayer(self.relayer)
        self.notify_task_finish()


class TransferLSTBtc(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 3, f"Invalid params"

        self.from_delegator = get_delegator_addr(params[0])
        self.to_delegator = get_delegator_addr(params[1])
        self.amount = int(params[2] * constants.BTC_DECIMALS)

    def execute(self):
        super().execute()

        self.notify_task_ready()
        BitcoinLSTToken[0].transfer(
            self.to_delegator,
            self.amount,
            {'from': self.from_delegator}
        )
        self.notify_task_finish()


class BurnLSTBtcAndPayBtcToRedeemer(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 4, f"Invalid params"

        self.storage_key = params[0]
        self.delegator = get_delegator_addr(params[1])
        self.amount = int(params[2] * constants.BTC_DECIMALS)
        self.payment_type = params[3]
        self.redeem_script_type = params[4] if len(params) == 5 else None

    def create_redeemer_script_pubkey(self):
        PaymentClass = getattr(payment, self.payment_type)
        if self.redeem_script_type is None:
            payment_inst = PaymentClass()
        else:
            payment_inst = PaymentClass(
                redeem_script_type=self.redeem_script_type
            )
        self.payment = payment_inst
        self.script_pubkey = self.payment.get_script_pubkey()

    def pay_btc_to_redeemer(self):
        self.chain.get_utxo_fee()
        utxos = self.chain.select_utxo_from_redeem_proof_txs(self.amount)
        wallet = self.chain.random_select_wallet()
        utxo_fee = self.chain.get_utxo_fee()
        txobj = bitcoin_tx.LSTUnstakeTx(
            utxos,
            self.amount - utxo_fee,
            self.payment,
            wallet
        )

        self.chain.add_btc_tx(self.storage_key, txobj)

    def execute(self):
        super().execute()

        self.notify_task_ready()
        self.create_redeemer_script_pubkey()
        BitcoinLSTStakeMock[0].redeem(
            self.amount,
            self.script_pubkey, {
                'from': self.delegator
            })
        self.pay_btc_to_redeemer()
        self.notify_task_finish()


class UnstakeLSTBtc(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) == 2, f"Invalid params"
        tx_data_key = params[0]
        tx_data = self.chain.get_btc_tx(tx_data_key)

        self.tx = tx_data.tx
        self.script_pubkey = tx_data.lock_output_script_pubkey
        self.relayer = get_delegator_addr(params[1])
        self.tx_data = tx_data

    def execute(self):
        super().execute()

        fake_block_height = 100
        fake_merkle_nodes = []
        fake_tx_index = 0

        self.notify_task_ready()
        tx = BitcoinLSTStakeMock[0].undelegate(
            self.tx.serialize().hex(),
            fake_block_height,
            fake_merkle_nodes,
            fake_tx_index, {
                'from': self.relayer
            })
        self.tx_data.set_relayer(self.relayer)
        self.tx_data.set_block_number(tx.block_number)
        self.notify_task_finish()


class ClaimReward(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) > 0, f"Invalid params"

        self.accounts = []
        for account_name in params:
            account = get_delegator_addr(account_name)
            self.accounts.append(account)

    def execute(self):
        super().execute()

        for account in self.accounts:
            self.account = account
            self.notify_task_ready()
            tx = StakeHubMock[0].claimReward({'from': account})
            self.notify_task_finish()


class UpdateParams(Task):
    def pre_execute(self, params):
        super().pre_execute(params)
        assert len(params) > 0, f"Invalid params"
        self.key = self.get_key()
        self.value = self.build_value(params)
        assert self.key is not None
        assert self.value is not None

    def get_key(self):
        pass

    def build_value(self, params):
        pass

    def get_contract(self):
        pass

    def execute(self):
        super().execute()
        self.notify_task_ready()
        self.get_contract().updateParam(
            self.key,
            self.value,
            {'from': GovHubMock[0].address}
        )
        self.notify_task_finish()


class AddSystemRewardOperator(UpdateParams):
    def is_supported(self, advanced_round):
        return True

    def build_value(self, params):
        assert len(params) == 1
        self.data = get_contract_addr(params[0])
        return bytes.fromhex(self.data.address[2:])

    def get_key(self):
        return constants.ADD_OPERATOR_KEY

    def get_contract(self):
        return SystemRewardMock[0]


class UpdateCoreStakeGrades(UpdateParams):
    def build_value(self, params):
        groups = len(params) // 2
        assert groups * 2 == len(params)

        data = []
        for idx in range(groups):
            data.append([params[idx * 2], params[idx * 2 + 1]])

        self.data = data
        return rlp.encode(data)

    def get_key(self):
        return constants.GRADES_KEY

    def get_contract(self):
        return BitcoinAgentMock[0]


class UpdateCoreStakeGradeFlag(UpdateParams):
    def build_value(self, params):
        assert len(params) == 1
        self.data = params[0]
        assert self.data <= 1
        return params[0].to_bytes(1)

    def get_key(self):
        return constants.GRADE_FLAG_KEY

    def get_contract(self):
        return BitcoinAgentMock[0]


class UpdateBtcStakeGradeFlag(UpdateParams):
    def build_value(self, params):
        assert len(params) == 1
        self.data = params[0]
        assert self.data <= 1
        return params[0].to_bytes(1)

    def get_key(self):
        return constants.GRADE_FLAG_KEY

    def get_contract(self):
        return BitcoinStakeMock[0]


class UpdateBtcStakeGrades(UpdateCoreStakeGrades):
    def get_contract(self):
        return BitcoinStakeMock[0]


class UpdateBtcLstStakeGradeFlag(UpdateParams):
    def is_supported(self, advanced_round):
        return False

    def build_value(self, params):
        assert len(params) == 1
        self.data = params[0]
        assert self.data <= 1
        return params[0].to_bytes(1)

    def get_key(self):
        return constants.GRADE_FLAG_KEY


class UpdateBtcLstStakeGradePercent(UpdateParams):
    def build_value(self, params):
        assert len(params) == 1
        self.data = params[0]
        assert self.data <= constants.MAX_BTC_LST_STAKE_GRADE_PERCENT
        return params[0].to_bytes(32)

    def get_key(self):
        return constants.GRADE_PERCENT_KEY

    def get_contract(self):
        return BitcoinAgentMock[0]


#### for test ####
class CreatePayment(Task):
    def pre_execute(self, params):
        super().pre_execute(params)

        assert len(params) >= 1
        self.payment_type = params[0]
        self.redeem_script_type = params[1] if len(params) > 1 else None

    def execute(self):
        super().execute()
        PaymentClass = getattr(payment, self.payment_type)
        if self.redeem_script_type is None:
            paymentInst = PaymentClass()
        else:
            paymentInst = PaymentClass(
                redeem_script_type=self.redeem_script_type
            )
        self.script_pubkey = paymentInst.get_script_pubkey()
        self.redeem_script = paymentInst.get_redeem_script()

        # wallet = BtcLSTLockWallet()
        # wallet.from_payment(paymentInst)

        # BitcoinLSTStakeMock[0].buildPkScript(wallet.get_hash(), wallet.get_payment_type())
        # dataArr = BitcoinLSTStakeMock[0].getDataArr()
        # print(f"type={wallet.get_payment_type()}")
        # print(f"hash={wallet.get_hash()}")
        # print(f"dataArr={dataArr}")
        # print(f"part1={part1}")
        # print(f"part2={part2}")
