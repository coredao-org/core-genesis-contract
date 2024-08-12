from brownie import *
from enum import Enum
from . import stake_asset
from . import constants
from .candidate_stake_state import CandidateStakeState
from .delegator_stake_state import DelegatorStakeState


class NodeStatus(Enum):
    CANDIDATE = 0b00000001
    INACTIVE = 0b00000010
    JAIL = 0b00000100
    MARGIN = 0b00001000
    VALIDATOR = 0b00010000


class Candidate:
    def __init__(self, tuple_data=None):
        self.income = 0
        self.jailed_round = 0
        self.operator = None
        self.slash_count = 0
        self.latest_slash_block = 0
        self.removed = False

        if tuple_data is None:
            self.commission = 0
            self.margin = 0
            self.status = 0
            return

        assert len(tuple_data) == 8

        self.operator_addr = accounts.at(tuple_data[0], force=True)
        self.consensus_addr = accounts.at(tuple_data[1], force=True)
        self.fee_addr = accounts.at(tuple_data[2], force=True)
        self.commission = tuple_data[3]
        self.margin = tuple_data[4]
        self.status = tuple_data[5]
        self.commission_last_change_round = tuple_data[6]
        self.commission_last_round_value = tuple_data[7]

        self.stake_state = CandidateStakeState()
        self.commission_in_use = tuple_data[3]

    def __repr__(self):
        return f"Candidate(operator_addr={self.operator_addr},score={self.get_total_score()},commission={self.commission},commission_in_use={self.commission_in_use},status={self.status},income={self.income})"

    def __eq__(self, other):
        if isinstance(other, Candidate):
            return self.operator_addr == other.operator_addr and \
                self.consensus_addr == other.consensus_addr and \
                self.fee_addr == other.fee_addr and \
                self.commission == other.commission and \
                self.margin == other.margin and \
                self.status == other.status and \
                self.commission_last_change_round == other.commission_last_change_round and \
                self.commission_last_round_value == other.commission_last_round_value
        return False

    def is_freedom(self, round):
        if self.jailed_round == 0:
            return True

        return self.jailed_round <= round

    def disable_delegate(self):
        assert not self.is_removed()
        self.status = self.status | NodeStatus.INACTIVE.value

    def enable_delegate(self):
        assert not self.is_removed()
        self.status = self.status & ~NodeStatus.INACTIVE.value

    def set_vldt(self):
        assert not self.is_removed()
        self.status = self.status | NodeStatus.VALIDATOR.value

    def unset_vldt(self):
        if self.is_removed():
            return

        self.status = self.status & ~NodeStatus.VALIDATOR.value

    def set_jail(self, round, jail_round):
        assert not self.is_removed()
        self.status = self.status | NodeStatus.JAIL.value
        if self.jailed_round == 0:
            self.jailed_round = round + jail_round
        else:
            self.jailed_round += jail_round

    def get_jailed_round(self):
        return self.jailed_round

    def unset_jail(self):
        if self.is_removed():
            return

        self.status = self.status & ~NodeStatus.JAIL.value
        self.jailed_round = 0

    def set_removed(self):
        self.removed = True

    def is_removed(self):
        return self.removed

    def set_margin(self):
        assert not self.is_removed()
        self.status = self.status | NodeStatus.MARGIN.value

    def unset_margin(self):
        assert not self.is_removed()
        self.status = self.status & ~NodeStatus.MARGIN.value

    def is_lack_of_collateral(self):
        return (self.status & NodeStatus.MARGIN.value) == NodeStatus.MARGIN.value

    def can_delegate(self):
        assert not self.is_removed()

        return self.status == NodeStatus.CANDIDATE.value or \
            self.status == NodeStatus.VALIDATOR.value or \
            self.status == (NodeStatus.CANDIDATE.value | NodeStatus.VALIDATOR.value)

    def can_unregister(self):
        assert not self.is_removed()

        return self.status == (
                    self.status & (NodeStatus.CANDIDATE.value | NodeStatus.MARGIN.value | NodeStatus.INACTIVE.value))

    def is_validator(self):
        assert not self.is_removed()
        return NodeStatus.VALIDATOR.value == (self.status & NodeStatus.VALIDATOR.value)

    def is_available(self):
        if self.is_removed():
            return False

        return self.status == NodeStatus.CANDIDATE.value or \
            self.status == (NodeStatus.CANDIDATE.value | NodeStatus.VALIDATOR.value)

    def set_operator_name(self, operator):
        self.operator = operator

    def get_operator_name(self):
        return self.operator

    def get_stake_state(self):
        return self.stake_state

    def set_stake_state(self, stake_state):
        self.stake_state = stake_state

    def get_total_score(self):
        return self.stake_state.get_total_score()

    def get_status(self):
        return self.status

    def set_status(self, status):
        self.status = status

    def get_operator_addr(self):
        return self.operator_addr

    def get_consensus_addr(self):
        return self.consensus_addr

    def get_fee_addr(self):
        return self.fee_addr

    def get_income(self):
        return self.income

    def add_income(self, delta_amount):
        self.income += delta_amount
        assert self.income >= 0

    def update_income(self, amount):
        assert amount >= 0
        self.income = amount

    def get_commission(self):
        return self.commission

    def get_incentive_amount(self, incentive_percent):
        return self.income * incentive_percent // 100

    def get_commission_in_use(self):
        return self.commission_in_use

    def get_commission_amount(self):
        return self.income * self.commission_in_use // 1000

    def update_commission_in_use(self):
        total_score = self.stake_state.get_total_score()
        if total_score == 0:
            self.commission_in_use = 1000
        else:
            self.commission_in_use = self.commission

    def incr_slash_count(self, block_number=0):
        self.slash_count += 1

        if block_number == 0:
            return

        assert block_number > self.latest_slash_block
        self.latest_slash_block = block_number

    def get_slash_count(self):
        return self.slash_count

    def update_slash_count(self, count):
        assert count >= 0
        self.slash_count = count

    def add_slash_count(self, delta_count):
        self.slash_count += delta_count
        assert self.slash_count >= 0

    def reset_slash_count(self):
        self.slash_count = 0

    def set_slash_count(self, count):
        self.slash_count = count

    def get_latest_slash_block(self):
        return self.latest_slash_block

    def set_latest_slash_block(self, block):
        self.latest_slash_block = block

    def reset_latest_slash_block(self):
        self.latest_slash_block = 0

    def get_margin_amount(self):
        return self.margin

    def add_margin_amount(self, delta_amount):
        self.margin += delta_amount
        assert self.margin >= 0

    def update_margin_amount(self, amount):
        self.margin = amount
        assert self.margin >= 0


class ChainState:
    def __init__(self, round):
        self.round = round
        self.core_asset = None
        self.power_asset = None
        self.btc_asset = None

        self.candidates = {}
        self.validators = None

        self.balances = {}
        self.btc_lst_balances = {}

        self.total_income = 0
        self.block_reward = 0
        self.incentive_percent = 0
        self.incentive_balance_cap = 0
        self.is_burn_out_of_cap = False
        self.burn_cap = 0
        self.total_unclaimed_reward = 0

        self.delegator_stake_state = DelegatorStakeState()

        # store BTC transactions shared between tasks
        self.shared_btc_txs = {}

        self.init_required_margin()
        self.init_validator_count()
        self.init_candidates()
        self.init_validators()
        self.init_block_reward()
        self.init_core_asset()
        self.init_power_asset()
        self.init_btc_asset()
        self.init_incentive_params()
        self.init_slash_threshold()

    ############# initialization ########################
    def init_balance(self, addr):
        if self.balances.get(addr) is None:
            self.balances[addr] = self.get_balance_on_chain(addr)

    def init_btc_lst_balance(self, addr):
        if self.btc_lst_balances.get(addr) is None:
            self.btc_lst_balances[addr] = self.get_btc_lst_balance_on_chain(addr)

    def init_required_margin(self):
        self.candidate_required_margin = \
            CandidateHubMock[0].requiredMargin()
        self.candidate_dues = CandidateHubMock[0].dues()

    def init_candidates(self):
        operator_addr_list = CandidateHubMock[0].getCandidates()
        assert len(operator_addr_list) == 0, f"{operator_addr_list}"
        self.candidates = {}

    def init_validators(self):
        assert self.validators is None
        self.validators = {}

        operator_addr_list = ValidatorSetMock[0].getValidatorOps()

        status = NodeStatus.CANDIDATE.value | NodeStatus.VALIDATOR.value
        for i in range(len(operator_addr_list)):
            tuple_data = ValidatorSetMock[0].currentValidatorSet(i)
            reorg_tuple_data = [
                tuple_data[0],
                tuple_data[1],
                tuple_data[2],
                tuple_data[3],
                self.candidate_required_margin,
                status,
                0,
                tuple_data[3]
            ]

            self.validators[reorg_tuple_data[0]] = Candidate(reorg_tuple_data)

    def init_block_reward(self):
        if self.block_reward == 0:
            self.block_reward = ValidatorSetMock[0].blockReward()

    def init_core_asset(self):
        self.core_asset = stake_asset.CoreAsset()
        print(f"core asset init state: {self.core_asset}")

    def init_power_asset(self):
        self.power_asset = stake_asset.PowerAsset()
        print(f"power asset init state: {self.power_asset}")

    def init_btc_asset(self):
        self.btc_asset = stake_asset.BtcAsset()
        print(f"btc asset init state: {self.btc_asset}")

    def init_validator_count(self):
        self.validator_count = CandidateHubMock[0].validatorCount()
        print(f"validator_count: {self.validator_count}")

    def init_incentive_params(self):
        self.incentive_percent = ValidatorSetMock[0].blockRewardIncentivePercent()
        self.incentive_balance_cap = SystemRewardMock[0].incentiveBalanceCap()
        self.is_burn_out_of_cap = SystemRewardMock[0].isBurn()
        self.burn_cap = Burn[0].burnCap()

    def init_slash_threshold(self):
        contract = SlashIndicatorMock[0]
        self.felony_threshold = contract.felonyThreshold()
        self.misdemeanor_threshold = contract.misdemeanorThreshold()
        self.felony_deposit = contract.felonyDeposit()
        self.felony_round = contract.felonyRound()
        self.reward_for_report_double_sign = contract.rewardForReportDoubleSign()

    ############# end initialization ########################

    ############## getter and setter #########################
    def get_balance(self, addr):
        return self.balances.get(addr, 0)

    def add_balance(self, addr, delta_amount):
        old_balance = self.get_balance(addr)
        self.balances[addr] = old_balance + delta_amount
        assert self.balances[addr] >= 0, f"old_balance={old_balance} delta_amount={delta_amount}"

    def update_balance(self, addr, amount):
        assert amount >= 0
        self.balances[addr] = amount

    def get_btc_lst_balance(self, addr):
        return self.btc_lst_balances.get(addr, 0)

    def add_btc_lst_balance(self, addr, delta_amount):
        self.btc_lst_balances[addr] = self.get_btc_lst_balance(addr) + delta_amount
        assert self.btc_lst_balances[addr] >= 0

    def update_btc_lst_balance(self, addr, amount):
        assert amount >= 0
        self.btc_lst_balances[addr] = amount

    def get_assets(self):
        return [self.core_asset, self.power_asset, self.btc_asset]

    def get_core_asset(self):
        return self.core_asset

    def get_btc_asset(self):
        return self.btc_asset

    def get_candidates(self):
        return self.candidates

    def get_candidate(self, operator_addr):
        if self.candidates.get(operator_addr) is None:
            return

        return self.candidates[operator_addr]

    def add_candidate(self, candidate):
        operator_addr = candidate.get_operator_addr()
        if self.candidates.get(operator_addr) is not None:
            self.candidates.pop(operator_addr)

        self.candidates[operator_addr] = candidate

    def remove_candidate(self, operator_addr):
        self.candidates[operator_addr].set_removed()

        # swap with last item, because quick sort is not stable
        candidate_count = len(self.candidates)
        if candidate_count == 1:
            return

        idx = 0
        for addr in self.candidates.keys():
            if addr == operator_addr:
                break
            idx += 1

        if idx == candidate_count - 1:
            return

        items = list(self.candidates.items())
        last_item = items[candidate_count - 1]
        items[candidate_count - 1] = items[idx]
        items[idx] = last_item

        self.candidates = dict(items)

    def get_validator(self, operator_addr):
        return self.validators.get(operator_addr)

    def get_available_candidates(self):
        validator_count = 0
        available_candidates = {}
        for candidate in self.candidates.values():
            if candidate.is_available():
                available_candidates[candidate.operator_addr] = candidate

        return available_candidates

    def get_candidate_by_consensus_addr(self, consensus_addr):
        for candidate in self.candidates.values():
            if candidate.consensus_addr == consensus_addr:
                return candidate

    def get_validators(self):
        return self.validators

    def set_validators(self, validators):
        self.validators = validators

    def get_validator_count(self):
        return self.validator_count

    def get_validator_income(self, consensus_addr):
        validator = self.get_candidate_by_consensus_addr(consensus_addr)
        assert validator is not None

        return validator.get_income()

    def get_round(self):
        return self.round

    def incr_round(self):
        self.round += 1

    def get_total_unclaimed_reward(self):
        return self.total_unclaimed_reward

    def add_total_unclaimed_reward(self, delta_amount):
        self.total_unclaimed_reward += delta_amount
        assert self.total_unclaimed_reward >= 0

    def get_incentive_percent(self):
        return self.incentive_percent

    def get_block_reward(self):
        return self.block_reward

    def update_block_reward(self, block_number):
        assert self.block_reward > 0
        reduce_interval = ValidatorSetMock[0].SUBSIDY_REDUCE_INTERVAL()
        reduce_factor = ValidatorSetMock[0].REDUCE_FACTOR()
        if block_number % reduce_interval == 0:
            self.block_reward = self.block_reward * reduce_factor // constants.PERCENT_DECIMALS

    def get_total_income(self):
        return self.total_income

    def add_total_income(self, delta_amount):
        self.total_income += delta_amount
        assert self.total_income >= 0

    def update_total_income(self, amount):
        assert amount >= 0
        self.total_income = amount

    def get_delegator_stake_state(self):
        return self.delegator_stake_state

    def get_btc_lst_stake_tx(self, txid):
        return self.delegator_stake_state.get_btc_lst_stake_tx(txid)

    def get_btc_stake_tx(self, txid):
        return self.delegator_stake_state.get_btc_stake_tx(txid)

    def get_btc_stake_realtime_amount(self, delegatee):
        candidate = self.get_candidate(delegatee)
        return candidate.get_stake_state().get_realtime_amount(self.btc_asset.get_name())

    def can_be_felony(self, candidate):
        return candidate.get_slash_count() % self.felony_threshold == 0

    def can_be_misdemeanor(self, candidate):
        return candidate.get_slash_count() % self.misdemeanor_threshold == 0

    def get_felony_threshold(self):
        return self.felony_threshold

    def get_felony_slash_amount(self):
        return self.felony_deposit

    def get_felony_round(self):
        return self.felony_round

    def get_candidate_dues(self):
        return self.candidate_dues

    def get_candidate_required_margin(self):
        return self.candidate_required_margin

    ############## getter and setter ########################

    ############### on-chain state getter #####################
    def get_balance_on_chain(self, addr):
        if isinstance(addr, str):
            addr = accounts.at(addr, force=True)

        return addr.balance()

    def get_btc_lst_balance_on_chain(self, addr):
        if isinstance(addr, str):
            addr = accounts.at(addr, force=True)

        return BitcoinLSTToken[0].balanceOf(addr)

    def get_candidate_on_chain(self, operator_addr):
        idx = CandidateHubMock[0].operateMap(operator_addr)
        assert idx > 0, f"Invalid operator address"
        candidate = CandidateHubMock[0].candidateSet(idx - 1)

        return Candidate(candidate)

    def get_validator_on_chain(self, consensus_addr):
        idx = ValidatorSetMock[0].currentValidatorSetMap(consensus_addr)
        return ValidatorSetMock[0].currentValidatorSet(idx - 1)

    def get_validator_income_on_chain(self, consensus_addr):
        return ValidatorSetMock[0].getIncoming(consensus_addr)

    def get_total_income_on_chain(self):
        return ValidatorSetMock[0].totalInCome()

    def get_delegator_core_stake_state_on_chain(self, delegator, delegatee):
        return CoreAgentMock[0].getDelegator(delegatee, delegator)

    def get_candidate_core_stake_state_on_chain(self, delegatee):
        return CoreAgentMock[0].candidateMap(delegatee)

    def get_core_stake_total_amount_on_chain(self, delegator):
        return CoreAgentMock[0].delegatorMap(delegator)

    def get_core_stake_candidates_on_chain(self, delegator):
        return CoreAgentMock[0].getCandidateListByDelegator(delegator)

    def get_core_history_reward_on_chain(self, delegator):
        return CoreAgentMock[0].rewardMap(delegator)[0]

    def get_btc_lst_stake_tx_on_chain(self, txid):
        return BitcoinLSTStakeMock[0].btcTxMap(txid)

    def get_btc_lst_total_stake_amount_on_chain(self):
        return BitcoinLSTStakeMock[0].stakedAmount()

    def get_btc_lst_total_realtime_amount_on_chain(self):
        return BitcoinLSTStakeMock[0].realtimeAmount()

    def get_btc_lst_stake_info_on_chain(self, delegator):
        return BitcoinLSTStakeMock[0].userStakeInfo(delegator)

    def get_btc_lst_history_reward_on_chain(self, delegator):
        return BitcoinLSTStakeMock[0].rewardMap(delegator)[0]

    def get_btc_stake_history_reward_on_chain(self, delegator):
        return BitcoinStakeMock[0].rewardMap(delegator)

    def get_power_history_reward_on_chain(self, delegator):
        return HashPowerAgentMock[0].rewardMap(delegator)[0]

    def get_btc_stake_tx_on_chain(self, txid):
        return BitcoinStakeMock[0].btcTxMap(txid)

    def get_btc_stake_tx_receipt_on_chain(self, txid):
        return BitcoinStakeMock[0].receiptMap(txid)

    def get_btc_stake_amount_on_chain(self, delegatee):
        tuple_data = BitcoinStakeMock[0].candidateMap(delegatee)
        return tuple_data[0]

    def get_btc_stake_realtime_amount_on_chain(self, delegatee):
        tuple_data = BitcoinStakeMock[0].candidateMap(delegatee)
        return tuple_data[1]

    def get_contribution_on_chain(self, contributor):
        return StakeHubMock[0].payableNotes(contributor)

    def get_total_unclaimed_reward_on_chain(self):
        return StakeHubMock[0].surplus()

    def get_wallets_on_chain(self):
        return BitcoinLSTStakeMock[0].getWallets()

    def get_round_powers_on_chain(self, power_round, delegatee):
        return HashPowerAgentMock[0].getStakeAmounts([delegatee], power_round + 7)

    def get_round_on_chain(self):
        return CandidateHubMock[0].roundTag()

    def get_redeem_request_on_chain(self, key):
        index = BitcoinLSTStakeMock[0].redeemMap(key)
        assert index > 0

        return BitcoinLSTStakeMock[0].redeemRequests(index - 1)

    def get_redeem_request_by_index_on_chain(self, index):
        return BitcoinLSTStakeMock[0].redeemRequests(index)

    def get_core_stake_grade_flag_on_chain(self):
        return BitcoinAgentMock[0].gradeActive()

    def get_core_stake_grades_on_chain(self):
        return BitcoinAgentMock[0].getGrades()

    def get_btc_stake_grade_flag_on_chain(self):
        return BitcoinStakeMock[0].gradeActive()

    def get_btc_stake_grades_on_chain(self):
        return BitcoinStakeMock[0].getGrades()

    def get_btc_lst_stake_grade_flag_on_chain(self):
        return BitcoinLSTStakeMock[0].gradeActive()

    def get_btc_lst_stake_grade_percent_on_chain(self):
        return BitcoinAgentMock[0].lstGradePercentage()

    def get_slash_indicator_on_chain(self, consensus_addr):
        return SlashIndicatorMock[0].indicators(consensus_addr)

    def get_jailed_round_on_chain(self, operator_addr):
        return CandidateHubMock[0].jailMap(operator_addr)

    ################ end on-chain state getter #####################

    ################## asset transfer #####################
    def pay_to_system_reward(self, amount):
        if amount == 0:
            return

        print(f"Pay to systemreward:{amount}")
        old_balance = self.get_balance(SystemRewardMock[0])
        if old_balance + amount <= self.incentive_balance_cap:
            self.add_balance(SystemRewardMock[0], amount)
            return

        self.update_balance(SystemRewardMock[0], self.incentive_balance_cap)
        out_of_cap_amount = old_balance + amount - self.incentive_balance_cap
        if self.is_burn_out_of_cap:
            refund_amount = self.pay_to_burn(out_of_cap_amount)
            self.add_balance(SystemRewardMock[0], refund_amount)
        else:
            self.add_balance(Foundation[0], out_of_cap_amount)

    def claim_system_reward(self, receiver, amount):
        balance = self.get_balance(SystemRewardMock[0])
        assert amount <= balance, f"insufficient balance"
        print(
            f"SystemReward balance off_chain={balance}, on_chain={self.get_balance_on_chain(SystemRewardMock[0])}, expect claim={amount}")
        amount = min(balance, amount)
        self.add_balance(receiver, amount)
        self.add_balance(SystemRewardMock[0], -amount)

        assert amount >= 0
        return amount

    def pay_to_burn(self, amount):
        if amount == 0:
            return 0

        old_balance = self.get_balance(Burn[0])
        if old_balance + amount <= self.burn_cap:
            self.add_balance(Burn[0], amount)
            return 0

        out_of_cap_amount = old_balance + amount - self.burn_cap
        if out_of_cap_amount > amount:
            refund_amount = amount
        else:
            refund_amount = out_of_cap_amount

        self.update_balance(Burn[0], self.burn_cap)

        return refund_amount

    def select_utxo_from_redeem_proof_txs(self, amount):
        return self.delegator_stake_state.select_utxo_from_redeem_proof_txs(amount)

    def random_select_wallet(self):
        return self.delegator_stake_state.random_select_wallet()

    def get_utxo_fee(self):
        return self.delegator_stake_state.get_utxo_fee()

    ################## end asset transfer #####################

    ################# tmp btc tx #############################
    def add_btc_tx(self, key, tx):
        self.shared_btc_txs[key] = tx

    def get_btc_tx(self, key):
        return self.shared_btc_txs[key]
