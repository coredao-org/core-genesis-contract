from brownie import *
from .payment import BtcLSTLockWallet
import random
from . import constants


class RedeemRequest:
    def __init__(self, hash, payment_type, amount):
        self.hash = hash
        self.payment_type = payment_type
        self.amount = amount

    def __repr__(self):
        return f"RedeemRequest(hash={self.hash},payment={self.payment_type},amount={self.amount})"

    def __eq__(self, other):
        return self.hash == other.hash and \
            self.payment_type == other.payment_type and \
            self.amount == other.amount

    def get_amount(self):
        return self.amount

    def get_hash(self):
        return self.hash

    def get_payment_type(self):
        return self.payment_type

    def add_amount(self, delta_amount):
        self.amount += delta_amount
        assert self.amount >= 0


class RedeemProofTx:
    def __init__(self):
        self.txid = None
        self.change_output_index = 0
        self.change_output_amount = 0
        self.block_number = 0
        self.spent = False

    def is_used(self):
        return self.block_number > 0

    def get_txid(self):
        return self.txid

    def set_txid(self, txid):
        self.txid = txid

    def get_amount(self):
        return self.change_output_amount

    def set_amount(self, amount):
        self.change_output_amount = amount

    def get_index(self):
        return self.change_output_index

    def set_index(self, index):
        self.change_output_index = index

    def set_block_number(self, block_number):
        self.block_number = block_number

    def is_valid_utxo(self, output_index):
        return self.change_output_amount > 0 and self.change_output_index == output_index

    def spend(self):
        self.spent = True

    def is_spent(self):
        return self.spent


class DelegatorStakeState:
    def __init__(self):
        # (delegator addr=>amount)
        self.core_amounts = {}
        # (delegator addr=>candidate addr list)
        self.core_stake_candidates = {}

        # (txid => tx obj)
        self.btc_stake_txs = {}  # btc stake tx info
        # (delegator=>txid list)
        self.btc_stake_txids = {}

        # (txid => tx obj)
        self.btc_lst_stake_txs = {}  # btc lst tx info

        # btc lst total info
        self.btc_lst_total_stake_amount = 0
        self.btc_lst_total_realtime_amount = 0
        self.utxo_fee = 0

        # btc lst user info
        self.delegator_btc_lst_change_round = {}
        self.delegator_btc_lst_stake_amount = {}
        self.delegator_btc_lst_realtime_amount = {}

        # history reward
        self.delegator_core_history_reward = {}
        self.delegator_core_history_accured_stake_amount = {}

        self.delegator_btc_lst_history_reward = {}
        self.delegator_btc_lst_history_accured_stake_amount = {}

        self.delegator_btc_stake_history_reward = {}
        self.delegator_btc_stake_history_unclaimable_reward = {}
        self.delegator_btc_stake_history_accured_stake_amount = {}

        self.delegator_power_history_reward = {}
        self.delegator_power_history_accured_stake_amount = {}

        # (delegator=>[(relayer1,amount1),(relayer2,amount2)])
        self.debts = {}

        # (relayer=>reward amount)
        self.contributions = {}

        #  reward level is related to the lock-up duration
        self.btc_stake_grade_flag = False
        self.btc_stake_grades = []

        self.btc_lst_stake_grade_flag = False
        self.btc_lst_stake_percent = 0

        # dual staking level
        self.core_stake_grade_flag = False
        self.core_stake_grades = []

        # wallets (script_pubkey => flag)   flag(0,1):is active
        self.wallets = {}

        # btc lst redeem request
        self.redeem_requests = {}

        # redeem proof txs
        self.redeem_proof_txs = {}

        self.init_data_on_chain()

    def init_data_on_chain(self):
        self.core_stake_grade_flag = BitcoinAgentMock[0].gradeActive()
        self.core_stake_grades = BitcoinAgentMock[0].getGrades()

        self.btc_stake_grade_flag = BitcoinStakeMock[0].gradeActive()
        self.btc_stake_grades = BitcoinStakeMock[0].getGrades()

        self.btc_lst_stake_grade_flag = True
        self.btc_lst_stake_percent = BitcoinAgentMock[0].lstGradePercentage()

        if self.btc_lst_stake_grade_flag:
            assert self.btc_lst_stake_percent > 0

        self.utxo_fee = BitcoinLSTStakeMock[0].utxoFee()

    def update_core_stake_grade_flag(self, grade_flag):
        self.core_stake_grade_flag = grade_flag

    def get_core_stake_grade_data(self):
        return self.core_stake_grade_flag, self.core_stake_grades

    def update_core_stake_grades(self, grades):
        self.core_stake_grades = grades

    def get_btc_stake_grade_data(self):
        return self.btc_stake_grade_flag, self.btc_stake_grades

    def update_btc_stake_grade_flag(self, grade_flag):
        self.btc_stake_grade_flag = grade_flag

    def update_btc_stake_grades(self, grades):
        self.btc_stake_grades = grades

    def get_btc_lst_stake_grade_data(self):
        return self.btc_lst_stake_grade_flag, self.btc_lst_stake_percent

    def update_btc_lst_stake_grade_flag(self, grade_flag):
        self.btc_lst_stake_grade_flag = grade_flag

    def update_btc_lst_stake_grade_percent(self, grade_percent):
        self.btc_lst_stake_percent = grade_percent

    def get_utxo_fee(self):
        return self.utxo_fee

    def get_redeem_requests(self):
        return self.redeem_requests

    def get_redeem_request(self, key):
        return self.redeem_requests.get(key)

    def rm_redeem_request(self, key):
        assert self.redeem_requests.get(key) is not None
        self.redeem_requests.pop(key)

    def add_redeem_request(self, key, hash, payment_type, amount):
        assert amount >= 0

        if self.redeem_requests.get(key) is None:
            self.redeem_requests[key] = RedeemRequest(
                hash,
                payment_type,
                amount
            )
        else:
            self.redeem_requests[key].add_amount(amount)

    def random_select_wallet(self):
        return random.choice(list(self.wallets.values()))

    def get_wallet(self, payment):
        assert payment is not None
        return self.wallets.get(payment.get_key())

    def add_wallet(self, payment):
        assert payment is not None

        wallet = BtcLSTLockWallet()
        wallet.from_payment(payment)

        key = payment.get_key()
        if self.wallets.get(key) is None:
            self.wallets[key] = wallet
        else:
            self.wallets[key].set_status(wallet.get_status())

    def init_lst_validator_count(self, available_candidates):
        count = 0
        for candidate in available_candidates.values():
            if candidate.is_validator():
                count += 1

        self.lst_validator_count = count

    def unset_lst_validator_count(self):
        self.lst_validator_count = 0

    def get_btc_lst_avg_stake_amount(self):
        if self.btc_lst_total_realtime_amount == 0:
            return 0

        assert self.lst_validator_count > 0
        return self.btc_lst_total_realtime_amount // self.lst_validator_count

    def get_core_amount(self, delegator):
        return self.core_amounts.get(delegator, 0)

    def add_core_amount(self, delegator, delta_amount):
        self.core_amounts[delegator] = self.core_amounts.get(delegator, 0) + delta_amount
        assert self.core_amounts[delegator] >= 0

    def get_core_stake_candidates(self, delegator):
        return self.core_stake_candidates.get(delegator, {})

    def add_core_stake_candidate(self, delegator, delegatee):
        if self.core_stake_candidates.get(delegator) is None:
            self.core_stake_candidates[delegator] = {}

        self.core_stake_candidates[delegator][delegatee] = True

    def rm_core_stake_candidate(self, delegator, delegatee):
        delegatees = self.get_core_stake_candidates(delegator)

        candidate_count = len(delegatees)
        if candidate_count == 0:
            return

        if candidate_count == 1:
            delegatees.pop(delegatee)
            return

        idx = 0
        for addr in delegatees.keys():
            if addr == delegatee:
                break
            idx += 1

        assert idx < candidate_count
        items = list(delegatees.items())
        if idx < candidate_count - 1:
            items[idx] = items[candidate_count - 1]

        items.pop()
        self.core_stake_candidates[delegator] = dict(items)

    def get_btc_lst_total_stake_amount(self):
        return self.btc_lst_total_stake_amount

    def sync_btc_lst_total_stake_amount(self):
        self.btc_lst_total_stake_amount = self.btc_lst_total_realtime_amount

    def get_btc_lst_total_realtime_amount(self):
        return self.btc_lst_total_realtime_amount

    def add_btc_lst_total_realtime_amount(self, delta_amount):
        self.btc_lst_total_realtime_amount += delta_amount
        assert self.btc_lst_total_realtime_amount >= 0

    def get_btc_lst_change_round(self, delegator):
        return self.delegator_btc_lst_change_round.get(delegator, 0)

    def update_btc_lst_change_round(self, delegator, round):
        assert round >= self.get_btc_lst_change_round(delegator)
        self.delegator_btc_lst_change_round[delegator] = round

    def get_btc_lst_stake_amount(self, delegator):
        return self.delegator_btc_lst_stake_amount.get(delegator, 0)

    def get_btc_lst_realtime_amount(self, delegator):
        return self.delegator_btc_lst_realtime_amount.get(delegator, 0)

    def sync_btc_lst_stake_amount(self, delegator):
        self.delegator_btc_lst_stake_amount[delegator] = \
            self.get_btc_lst_realtime_amount(delegator)

    def add_btc_lst_realtime_amount(self, delegator, delta_amout):
        self.delegator_btc_lst_realtime_amount[delegator] = \
            self.get_btc_lst_realtime_amount(delegator) + delta_amout

        assert self.delegator_btc_lst_realtime_amount[delegator] >= 0

    def add_btc_lst_total_realtime_amount(self, delta_amount):
        self.btc_lst_total_realtime_amount += delta_amount
        assert self.btc_lst_total_realtime_amount >= 0

    def get_btc_lst_history_reward(self, delegator):
        return self.delegator_btc_lst_history_reward.get(delegator, 0)

    def add_btc_lst_history_reward(self, delegator, delta_amount):
        self.delegator_btc_lst_history_reward[delegator] = \
            self.get_btc_lst_history_reward(delegator) + delta_amount

        assert self.delegator_btc_lst_history_reward[delegator] >= 0

    def update_btc_lst_history_reward(self, delegator, amount):
        assert amount >= 0
        self.delegator_btc_lst_history_reward[delegator] = amount

    def get_btc_lst_history_accured_stake_amount(self, delegator):
        return self.delegator_btc_lst_history_accured_stake_amount.get(delegator, 0)

    def add_btc_lst_history_accured_stake_amount(self, delegator, delta_amount):
        self.delegator_btc_lst_history_accured_stake_amount[delegator] = \
            self.get_btc_lst_history_accured_stake_amount(delegator) + delta_amount

        assert self.delegator_btc_lst_history_accured_stake_amount[delegator] >= 0

    def update_btc_lst_history_accured_stake_amount(self, delegator, amount):
        assert amount >= 0
        self.delegator_btc_lst_history_accured_stake_amount[delegator] = amount

    def get_btc_stake_history_reward(self, delegator):
        return self.delegator_btc_stake_history_reward.get(delegator, 0)

    def add_btc_stake_history_reward(self, delegator, delta_amount):
        self.delegator_btc_stake_history_reward[delegator] = \
            self.get_btc_stake_history_reward(delegator) + delta_amount

        assert self.delegator_btc_stake_history_reward[delegator] >= 0

    def update_btc_stake_history_reward(self, delegator, amount):
        assert amount >= 0
        self.delegator_btc_stake_history_reward[delegator] = amount

    def get_btc_stake_history_unclaimable_reward(self, delegator):
        return self.delegator_btc_stake_history_unclaimable_reward.get(delegator, 0)

    def add_btc_stake_history_unclaimable_reward(self, delegator, delta_amount):
        self.delegator_btc_stake_history_unclaimable_reward[delegator] = \
            self.get_btc_stake_history_unclaimable_reward(delegator) + delta_amount

        assert self.delegator_btc_stake_history_unclaimable_reward[delegator] >= 0

    def update_btc_stake_history_unclaimable_reward(self, delegator, amount):
        assert amount >= 0
        self.delegator_btc_stake_history_unclaimable_reward[delegator] = amount

    def get_btc_stake_history_accured_stake_amount(self, delegator):
        return self.delegator_btc_stake_history_accured_stake_amount.get(delegator, 0)

    def add_btc_stake_history_accured_stake_amount(self, delegator, delta_amount):
        self.delegator_btc_stake_history_accured_stake_amount[delegator] = \
            self.get_btc_stake_history_accured_stake_amount(delegator) + delta_amount

        assert self.delegator_btc_stake_history_accured_stake_amount[delegator] >= 0

    def update_btc_stake_history_accured_stake_amount(self, delegator, amount):
        assert amount >= 0
        self.delegator_btc_stake_history_accured_stake_amount[delegator] = amount

    def get_power_history_reward(self, delegator):
        return self.delegator_power_history_reward.get(delegator, 0)

    def add_power_history_reward(self, delegator, delta_amount):
        self.delegator_power_history_reward[delegator] = \
            self.get_power_history_reward(delegator) + delta_amount

        assert self.delegator_power_history_reward[delegator] >= 0

    def update_power_history_reward(self, delegator, amount):
        assert amount >= 0
        self.delegator_power_history_reward[delegator] = amount

    def get_power_history_accured_stake_amount(self, delegator):
        return self.delegator_power_history_accured_stake_amount.get(delegator, 0)

    def add_power_history_accured_stake_amount(self, delegator, delta_amount):
        self.delegator_power_history_accured_stake_amount[delegator] = \
            self.get_power_history_accured_stake_amount(delegator) + delta_amount

        assert self.delegator_power_history_accured_stake_amount[delegator] >= 0

    def update_power_history_accured_stake_amount(self, delegator, amount):
        assert amount >= 0
        self.delegator_power_history_accured_stake_amount[delegator] = amount

    def get_core_history_reward(self, delegator):
        return self.delegator_core_history_reward.get(delegator, 0)

    def add_core_history_reward(self, delegator, delta_amount):
        self.delegator_core_history_reward[delegator] = \
            self.get_core_history_reward(delegator) + delta_amount

        assert self.delegator_core_history_reward[delegator] >= 0

    def update_core_history_reward(self, delegator, amount):
        assert amount >= 0
        self.delegator_core_history_reward[delegator] = amount

    def get_core_history_accured_stake_amount(self, delegator):
        return self.delegator_core_history_accured_stake_amount.get(delegator, 0)

    def add_core_history_accured_stake_amount(self, delegator, delta_amount):
        self.delegator_core_history_accured_stake_amount[delegator] = \
            self.get_core_history_accured_stake_amount(delegator) + delta_amount

        assert self.delegator_core_history_accured_stake_amount[delegator] >= 0

    def update_core_history_accured_stake_amount(self, delegator, amount):
        assert amount >= 0
        self.delegator_core_history_accured_stake_amount[delegator] = amount

    def get_btc_lst_stake_tx(self, txid):
        return self.btc_lst_stake_txs.get(txid)

    def add_btc_lst_stake_tx(self, tx):
        txid = tx.get_txid()
        amount = tx.get_amount()
        assert self.btc_lst_stake_txs.get(txid) is None
        assert amount >= self.utxo_fee * 2

        self.btc_lst_stake_txs[txid] = tx
        # no relayer reward
        # self.add_debt(tx)

        self.add_redeem_proof_tx(tx)

    def get_redeem_proof_tx(self, txid):
        return self.redeem_proof_txs.get(txid)

    def add_redeem_proof_tx(self, tx):
        txid = tx.get_txid()
        assert self.redeem_proof_txs.get(txid) is None

        redeem_proof_tx = RedeemProofTx()
        redeem_proof_tx.set_txid(txid)
        redeem_proof_tx.set_amount(tx.get_amount())
        redeem_proof_tx.set_index(tx.get_lock_output_index())
        assert tx.get_block_number() > 0
        redeem_proof_tx.set_block_number(tx.get_block_number())

        self.redeem_proof_txs[txid] = redeem_proof_tx

    def add_empty_redeem_proof_tx(self, txid):
        assert self.redeem_proof_txs.get(txid) is None

        redeem_proof_tx = RedeemProofTx()
        redeem_proof_tx.set_txid(txid)

        self.redeem_proof_txs[txid] = redeem_proof_tx

    def get_btc_stake_tx(self, txid):
        return self.btc_stake_txs.get(txid)

    def get_btc_stake_txs(self):
        return self.btc_stake_txs

    def add_btc_stake_tx(self, tx):
        txid = tx.get_txid()
        assert self.btc_stake_txs.get(txid) is None

        self.btc_stake_txs[txid] = tx
        self.add_btc_stake_txid(tx)
        # no relayer reward
        # self.add_debt(tx)

    def remove_btc_stake_txid(self, delegator, txid):
        self.btc_stake_txids[delegator].pop(txid)
        # self.btc_stake_txs.pop(txid)

    def get_btc_stake_txids(self, delegator):
        return self.btc_stake_txids.get(delegator)

    def add_btc_stake_txid(self, tx):
        delegator = tx.get_delegator()
        if self.btc_stake_txids.get(delegator) is None:
            self.btc_stake_txids[delegator] = {}

        txid = tx.get_txid()
        self.btc_stake_txids[delegator][txid] = 1

    def add_debt(self, tx):
        delegator = tx.get_delegator()
        relayer = tx.get_relayer()
        fee = tx.get_fee()

        if self.debts.get(delegator) is None:
            self.debts[delegator] = []

        print(f"add_delegator_debt: {fee}")
        self.debts[delegator].append((relayer, fee * constants.FEE_DECIMALS))

    def get_debts(self, delegator):
        return self.debts.get(delegator)

    def get_relayer_reward(self, relayer):
        return self.contributions.get(relayer, 0)

    def add_relayer_reward(self, relayer, delta_amount):
        self.contributions[relayer] = self.get_relayer_reward(relayer) + delta_amount
        assert self.contributions[relayer] >= 0

    def get_all_relayer_rewards(self):
        return self.contributions

    def apply_btc_stake_grade_to_reward(self, reward, tx):
        if not self.btc_stake_grade_flag:
            return reward, 0

        if len(self.btc_stake_grades) == 0:
            return reward, 0

        lock_duration = tx.get_lock_time() - tx.get_block_time()

        print(f"lock duration={lock_duration}")

        percent = self.btc_stake_grades[0][1]
        for grade in reversed(self.btc_stake_grades):
            if lock_duration >= grade[0]:
                percent = grade[1]
                break

        claimable_reward = reward * percent // constants.PERCENT_DECIMALS
        return claimable_reward, reward - claimable_reward

    def apply_holding_time_to_reward(self, reward):
        if not self.btc_lst_stake_grade_flag:
            return reward, 0

        if reward == 0:
            return 0, 0

        assert self.btc_lst_stake_percent > 0

        claimable_reward = reward * self.btc_lst_stake_percent // constants.PERCENT_DECIMALS
        print(f"HOLDING:  percent={self.btc_lst_stake_percent}")

        return claimable_reward, reward - claimable_reward

    def select_utxo_from_redeem_proof_txs(self, amount):
        total_amount = 0
        utxos = {}
        for tx in self.redeem_proof_txs.values():
            if tx.is_spent():
                continue

            utxos[tx.get_txid()] = tx
            tx.spend()

            total_amount += tx.get_amount()
            if total_amount >= amount:
                break
        return utxos
