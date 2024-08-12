from enum import Enum
from brownie import *
import json
import random
from . import constants
from .account_mgr import AccountMgr
from .chain_state import NodeStatus, Candidate
from . import payment
from .scenario import Scenario


############### scenario generator ################
class AssetAmount:
    def __init__(self):
        self.amount = 0  # the transferable quantity
        self.transferred_in = 0  # the quantity transferred from external candidates during current round


class DelegatorStakeInfo:
    def __init__(self):
        # delegatee=>amount info
        self.cores = {}

        # delegatee=>amount info
        self.btcs = {}

        # delegator total amount
        self.btc_lst_amount = 0

        # round => power count
        self.powers = {}

    def refresh(self):
        for asset_amount in self.cores.values():
            asset_amount.amount += asset_amount.transferred_in
            asset_amount.transferred_in = 0

    def is_empty(self):
        if len(self.cores) > 0:
            return False

        if len(self.btcs) > 0:
            return False

        if len(self.powers) > 0:
            return False

        return self.btc_lst_amount == 0

    def get_btc_lst_stake_amount(self):
        return self.btc_lst_amount

    def transfer_in_core(self, delegatee, amount):
        if self.cores.get(delegatee) is None:
            self.cores[delegatee] = AssetAmount()

        asset_amount = self.cores[delegatee]
        asset_amount.transferred_in += amount

    def transfer_out_core(self, delegatee, amount):
        asset_amount = self.cores[delegatee]
        asset_amount.amount -= amount
        assert asset_amount.amount >= 0

        if asset_amount.amount == 0 and \
                asset_amount.transferred_in == 0:
            self.cores.pop(delegatee)

    def get_core_staked_candidates(self):
        if len(self.cores) == 0:
            return None

        operators = []
        for operator, asset_amount in self.cores.items():
            if asset_amount.amount > 0:
                operators.append(operator)

        return operators

    def choice_core_staked_candidate(self):
        operators = self.get_core_staked_candidates()
        if operators is None or len(operators) == 0:
            return None, 0

        operator = random.choice(operators)
        amount = self.cores[operator].amount

        return operator, amount

    def stake_one_power(self, round):
        if self.powers.get(round) is None:
            self.powers[round] = 0

        self.powers[round] += 1

    def stake_btc(self, delegatee, tx_symbol, unlock_round):
        if self.btcs.get(delegatee) is None:
            self.btcs[delegatee] = {}

        self.btcs[delegatee][tx_symbol] = unlock_round

    def transfer_btc(self, from_delegatee, to_delegatee, tx_symbol):
        if self.btcs.get(from_delegatee) is None or \
                self.btcs[from_delegatee].get(tx_symbol) is None:
            return

        unlock_round = self.btcs[from_delegatee][tx_symbol]

        self.btcs[from_delegatee].pop(tx_symbol)
        if len(self.btcs) == 0:
            self.btcs.pop(from_delegatee)

        self.stake_btc(to_delegatee, tx_symbol, unlock_round)

    def stake_btc_lst(self, amount):
        self.btc_lst_amount += amount

    def redeem_btc_lst(self, amount):
        self.btc_lst_amount -= amount
        assert self.btc_lst_amount >= 0

    def choice_transferable_btc(self):
        if len(self.btcs) == 0:
            return None, None, 0

        delegatee = random.choice(list(self.btcs.keys()))
        if len(self.btcs[delegatee]) == 0:
            return None, None, 0

        tx_symbol = random.choice(list(self.btcs[delegatee].keys()))
        return delegatee, tx_symbol, self.btcs[delegatee][tx_symbol]


class DataCenter:
    def __init__(self, round, candidate_count, delegator_count):
        # update when a candidate is registered or its status changes
        self.candidates = {}

        # can delegate candidates, update when dirty_available_candidates = True
        self.available_candidates = {}
        self.dirty_available_candidates = False

        # delegator => delegator stake info
        self.stake_infos = {}

        self.round = round
        self.candidate_count = candidate_count
        self.delegator_count = delegator_count
        self.next_tx_symbol_id = 1

        self.sponsees = None
        self.operators = None
        self.delegators = None

        self.btc_stake_payments = None

        self.btc_lst_stake_payments = None

        self.btc_lst_redeem_max_amount = 0

        self.utxo_fee = 0

        self.unavailable_round = {}

        self.init_sponsees()
        self.init_delegators()
        self.init_operators()
        self.init_btc_stake_payments()
        self.init_btc_lst_stake_payments()
        self.init_btc_lst_redeem_max_amount()
        self.init_random_task_probabilities()
        self.init_utxo_fee()
        self.init_slash_params()

    ################# initialization ################
    def init_sponsees(self):
        self.sponsees = {
            "ValidatorSet": 10000000,
            "SystemReward": 40000000
        }

    def init_delegators(self):
        delegators = []
        for i in range(self.delegator_count):
            delegators.append(f"{constants.DELEGATOR_NAME_PREFIX}{i}")

        self.delegators = delegators

    def init_operators(self):
        operators = []
        for i in range(self.candidate_count):
            operators.append(f"{constants.OPERATOR_NAME_PREFIX}{i}")

        self.operators = operators

    def init_btc_stake_payments(self):
        self.btc_stake_payments = {
            payment.P2SH.__name__: [
                payment.CLTV_P2PK.__name__,
                payment.CLTV_P2PKH.__name__,
                payment.CLTV_P2MS.__name__
            ],

            payment.P2WSH.__name__: [
                payment.CLTV_P2PK.__name__,
                payment.CLTV_P2PKH.__name__,
                payment.CLTV_P2MS.__name__
            ]
        }

    def init_btc_lst_stake_payments(self):
        self.btc_lst_stake_payments = {
            payment.P2PKH.__name__: [],
            payment.P2WPKH.__name__: [],
            payment.P2SH.__name__: [
                payment.P2MS.__name__,
                payment.P2PKH.__name__,
                payment.P2WPKH.__name__,
                payment.P2WSH.__name__
            ],
            payment.P2WSH.__name__: [
                payment.P2MS.__name__
            ],
            payment.P2TR_SCRIPT.__name__: [],
            payment.P2TR_PUBKEY.__name__: []

        }

    def init_random_task_probabilities(self):
        self.random_task_probabilities = {
            GenerateBlock.__name__: 100,
            UpdateCoreStakeGradeFlag.__name__: 20,
            UpdateBtcStakeGradeFlag.__name__: 10,
            UpdateBtcLstStakeGradePercent.__name__: 10,
            RegisterCandidate.__name__: 50,
            SlashValidator.__name__: 5,
            AddMargin.__name__: 90,
            RefuseDelegate.__name__: 5,
            AcceptDelegate.__name__: 50,
            StakeCore.__name__: 30
        }

    def init_btc_lst_redeem_max_amount(self):
        self.btc_lst_redeem_max_amount = BitcoinLSTStakeMock[0].burnBTCLimit()

    def init_utxo_fee(self):
        self.utxo_fee = BitcoinLSTStakeMock[0].utxoFee()

    def init_slash_params(self):
        self.felony_round = SlashIndicatorMock[0].felonyRound()
        self.felony_deposit = SlashIndicatorMock[0].felonyDeposit()
        self.felony_threshold = SlashIndicatorMock[0].felonyThreshold()
        self.dues = CandidateHubMock[0].dues()
        self.required_margin = CandidateHubMock[0].requiredMargin()

    def refresh(self):
        self.round += 1
        for stake_info in self.stake_infos.values():
            stake_info.refresh()

        for candidate in self.candidates.values():
            slash_count = candidate.get_slash_count() - self.felony_threshold // 4
            if slash_count > 0:
                candidate.update_slash_count(slash_count)
            else:
                candidate.reset_slash_count()

            jailed_round = candidate.get_jailed_round()
            if jailed_round <= self.round:
                candidate.unset_jail()

        self.dirty_available_candidates = True

    ############### end initialization ################

    ############### getter and setter #################
    def get_probability(self, name):
        return self.random_task_probabilities.get(name, constants.DEFAULT_PROBABILITY)

    def get_sponsees(self):
        return self.sponsees

    def get_candidates(self):
        return self.candidates

    def get_available_candidates(self):
        if not self.dirty_available_candidates:
            return self.available_candidates

        self.available_candidates = {}
        for candidate in self.candidates.values():
            if candidate.can_delegate():
                self.available_candidates[candidate.get_operator_name()] = candidate

        self.dirty_available_candidates = False
        return self.available_candidates

    def get_candidate_count(self):
        return len(self.candidates)

    def get_stake_info(self, delegator, init_if_none=True):
        if self.stake_infos.get(delegator) is None and init_if_none:
            self.stake_infos[delegator] = DelegatorStakeInfo()

        return self.stake_infos.get(delegator)

    def get_core_staked_candidates(self, delegator):
        stake_info = self.get_stake_info(delegator)
        return stake_info.get_core_staked_candidates()

    def get_felony_threshold(self):
        return self.felony_threshold

    ############# end getter and setter ###############

    ################### candidate #####################
    def is_registered(self, operator):
        return self.candidates.get(operator) is not None

    def can_unregistered(self, operator):
        if not self.is_registered(operator):
            return False

        round = self.get_unavailable_round(operator)
        if round == 0:
            return False

        return self.round > round

    def is_available(self, operator):
        candidates = self.get_available_candidates()
        if len(candidates) == 0:
            return False

        return candidates.get(operator) is not None

    def register_candidate(self, operator):
        candidate = Candidate()
        candidate.set_status(NodeStatus.CANDIDATE.value)
        candidate.update_margin_amount(self.required_margin)
        candidate.set_operator_name(operator)

        self.candidates[operator] = candidate

        self.unset_unavailable_round(operator)
        self.dirty_available_candidates = True

    def unregister_candidate(self, operator):
        self.candidates.pop(operator)
        self.dirty_available_candidates = True

    def slash_validator(self, operator, count):
        for i in range(count):
            self.slash_validator_once(operator)

    def slash_validator_once(self, operator):
        candidates = self.get_available_candidates()
        candidate = candidates.get(operator)

        if candidate is None:
            return

        candidate.incr_slash_count()

        slash_count = candidate.get_slash_count()
        if slash_count % self.felony_threshold == 0:
            candidate.reset_slash_count()
            margin_amount = candidate.get_margin_amount()
            slash_amount = self.felony_deposit
            if margin_amount < self.dues + slash_amount:
                slash_amount = margin_amount

            candidate.set_jail(self.round, self.felony_round)
            candidate.add_margin_amount(-slash_amount)

            if candidate.get_margin_amount() < self.required_margin:
                candidate.set_margin()

            self.dirty_available_candidates = True

    def can_delegate(self, operator):
        candidate = self.candidates.get(operator)
        assert candidate is not None

        return candidate.can_delegate()

    def is_lack_of_collateral(self, operator):
        candidate = self.candidates.get(operator)
        assert candidate is not None

        return candidate.is_lack_of_collateral()

    def unset_margin(self, operator):
        candidate = self.candidates.get(operator)
        amount = self.required_margin - candidate.get_margin_amount()
        candidate.add_margin_amount(amount)
        candidate.unset_margin()

        self.dirty_available_candidates = True

    def set_unavailable_round(self, operator):
        self.unavailable_round[operator] = self.round

    def unset_unavailable_round(self, operator):
        if self.unavailable_round.get(operator) is None:
            return

        self.unavailable_round.pop(operator)

    def get_unavailable_round(self, operator):
        return self.unavailable_round.get(operator, 0)

    def refuse_delegate(self, operator):
        candidate = self.candidates.get(operator)
        candidate.disable_delegate()

        self.set_unavailable_round(operator)
        self.dirty_available_candidates = True

    def accept_delegate(self, operator):
        candidate = self.candidates.get(operator)
        candidate.enable_delegate()

        self.unset_unavailable_round(operator)
        self.dirty_available_candidates = True

    def choice_candidate(self):
        candidates = self.get_candidates()
        if len(candidates) == 0:
            return

        return random.choice(list(candidates.keys()))

    # delegateable candidate
    def choice_available_candidate(self):
        candidates = self.get_available_candidates()
        if len(candidates) == 0:
            return

        return random.choice(list(candidates.keys()))

    # delegateable candidate
    def choice_available_candidate_exclude(self, excluded_operator):
        operator = self.choice_available_candidate()
        if operator is None or operator == excluded_operator:
            return

        return operator

    def choice_core_staked_candidate(self, delegator):
        stake_info = self.get_stake_info(delegator)
        return stake_info.choice_core_staked_candidate()

    ################# end candidate #################

    ################ delegator ######################
    def choice_miners(self):
        assert self.delegator_count > 0
        max_count = max(self.delegator_count // 2, 1)
        count = random.randint(1, max_count)

        return random.choices(self.delegators, k=count)

    def choice_delegator(self):
        return random.choice(self.delegators)

    ############## end delegator ####################

    ################## stake asset #################
    def stake_core(self, delegator, delegatee, amount):
        stake_info = self.get_stake_info(delegator)
        stake_info.transfer_in_core(delegatee, amount)

    def unstake_core(self, delegator, delegatee, amount):
        stake_info = self.get_stake_info(delegator)
        stake_info.transfer_out_core(delegatee, amount)

    def transfer_core(self, delegator, from_delegatee, to_delegatee, amount):
        stake_info = self.get_stake_info(delegator)
        stake_info.transfer_out_core(from_delegatee, amount)
        stake_info.transfer_in_core(to_delegatee, amount)

    def stake_power(self, lagged_round, miners):
        stake_round = self.round - lagged_round
        for miner in miners:
            stake_info = self.get_stake_info(miner)
            stake_info.stake_one_power(stake_round)

    def stake_btc(self, delegator, delegatee, tx_symbol, lock_round):
        stake_info = self.get_stake_info(delegator)

        unlock_round = self.round + lock_round
        stake_info.stake_btc(delegatee, tx_symbol, unlock_round)

    def transfer_btc(self, delegator, from_delegatee, to_delegatee, tx_symbol):
        stake_info = self.get_stake_info(delegator)
        stake_info.transfer_btc(from_delegatee, to_delegatee, tx_symbol)

    def stake_btc_lst(self, delegator, tx_symbol, amount):
        stake_info = self.get_stake_info(delegator)
        stake_info.stake_btc_lst(amount)

    def redeem_btc_lst(self, redeemer, amount):
        stake_info = self.get_stake_info(redeemer)
        stake_info.redeem_btc_lst(amount)

    def transfer_btc_lst(self, from_delegator, to_delegator, amount):
        self.redeem_btc_lst(from_delegator, amount)
        self.stake_btc_lst(to_delegator, "", amount)

    def choice_transferable_btc(self, delegator):
        stake_info = self.get_stake_info(delegator)
        delegatee, tx_symbol, unlock_round = stake_info.choice_transferable_btc()
        if delegatee is None or tx_symbol is None:
            return None, None

        if unlock_round <= self.round + 1:
            return None, None

        return delegatee, tx_symbol

    def choice_redeem_amount(self, redeemer):
        stake_info = self.get_stake_info(redeemer)

        max_amount = min(stake_info.get_btc_lst_stake_amount(),
                         self.btc_lst_redeem_max_amount // constants.BTC_DECIMALS)
        if max_amount == 0:
            return 0

        min_amount = self.utxo_fee * 2 / constants.BTC_DECIMALS
        if max_amount < min_amount:
            return 0

        amount = round(random.uniform(min_amount, max_amount), 8)
        return amount

    def is_staked_asset(self, delegator):
        stake_info = self.get_stake_info(delegator)
        return not stake_info.is_empty()

    ################# end stake asset ##################

    ################## lock script ###################
    def alloc_tx_symbol(self):
        cur_symbol = f"{constants.BITCOIN_TX_SYMBOL_PREFIX}{self.next_tx_symbol_id}"
        self.next_tx_symbol_id += 1
        return cur_symbol

    def choice_btc_stake_lock_script(self):
        payment_type = random.choice(list(self.btc_stake_payments.keys()))
        redeem_script_type = random.choice(list(self.btc_stake_payments[payment_type]))

        return payment_type, redeem_script_type

    def choice_btc_lst_stake_lock_script(self):
        payment_type = random.choice(list(self.btc_lst_stake_payments.keys()))

        redeem_script_types = self.btc_lst_stake_payments[payment_type]
        if len(redeem_script_types) == 0:
            return payment_type, None

        redeem_script_type = random.choice(redeem_script_types)
        return payment_type, redeem_script_type

    ################ end lock script #################


class ScenarioGenerator:
    def __init__(self):
        self.start_round = 0
        self.stop_round = 0

        self.init_round = 0
        self.task_generators = None
        self.data_center = None

    def add_generator(self, generator):
        assert generator is not None
        assert self.data_center is not None

        generator.set_data_center(self.data_center)
        self.task_generators[generator.get_id()] = generator

    def generate(self, start_round, stop_round, candidate_count, delegator_count):
        # check params
        assert start_round >= constants.MIN_ROUND and stop_round > start_round
        assert candidate_count > 0 and delegator_count > 0

        # init data members
        self.start_round = start_round
        self.stop_round = stop_round

        self.init_round = start_round
        self.task_generators = {}
        self.round_tasks = {}

        self.data_center = DataCenter(start_round, candidate_count, delegator_count)

        # init global task builder for each task generator
        ChainTaskGenerator.init_supported_task_builders()
        CandidateTaskGenerator.init_supported_task_builders()
        DelegatorTaskGenerator.init_supported_task_builders()

        # init chain task generators
        self.chain_task_generator = ChainTaskGenerator()
        self.add_generator(self.chain_task_generator)

        # init candidate task generators
        for i in range(candidate_count):
            generator = CandidateTaskGenerator()
            self.add_generator(generator)

        # init delegator task generators
        for i in range(delegator_count):
            generator = DelegatorTaskGenerator()
            self.add_generator(generator)

        # generate round task
        round_count = stop_round - start_round + 1
        for advanced_round in range(round_count):
            self.data_center.refresh()

            tasks = []
            for generator in self.task_generators.values():
                res = generator.generate_one_time_task(advanced_round)
                if res is None or len(res) == 0:
                    continue

                tasks.extend(res)

            for generator in self.task_generators.values():
                res = generator.generate_mandatory_task(advanced_round)
                if res is None or len(res) == 0:
                    continue

                tasks.extend(res)

            for generator in self.task_generators.values():
                res = generator.generate_random_task(advanced_round)
                if res is None or len(res) == 0:
                    continue

                tasks.extend(res)

            self.round_tasks[advanced_round] = tasks

        scenario = Scenario()
        scenario.set_init_round(self.init_round)
        scenario.set_round_tasks(self.round_tasks)

        ChainTaskGenerator.reset()
        CandidateTaskGenerator.reset()
        DelegatorTaskGenerator.reset()
        TaskGenerator.reset()
        return scenario


############# end scenario generator ##############


################ task generator ###################
class TaskGenerator:
    __next_id = 0

    @classmethod
    def reset(cls):
        cls.__next_id = 0

    @classmethod
    def __alloc_id(cls):
        cur_id = cls.__next_id
        cls.__next_id += 1
        return cur_id

    def __init__(self):
        self.id = TaskGenerator.__alloc_id()
        self.advanced_round = 0
        self.data_center = None

    def get_id(self):
        return self.id

    def set_advanced_round(self, advanced_round):
        self.advanced_round = advanced_round

    def get_advanced_round(self):
        return self.advanced_round

    def set_data_center(self, data_center):
        self.data_center = data_center

    def get_data_center(self):
        return self.data_center

    def generate_one_time_task(self, advanced_round):
        self.set_advanced_round(advanced_round)

    def generate_mandatory_task(self, advanced_round):
        self.set_advanced_round(advanced_round)

    def generate_random_task(self, advanced_round):
        self.set_advanced_round(advanced_round)


class ChainTaskGenerator(TaskGenerator):
    __one_time_task_builders = None
    __mandatory_task_builders = None
    __random_task_builders = None

    @classmethod
    def reset(cls):
        cls.__one_time_task_builders = None
        cls.__mandatory_task_builders = None
        cls.__random_task_builders = None

    @classmethod
    def init_supported_task_builders(cls):
        if cls.__random_task_builders is not None:
            return

        cls.__one_time_task_builders = [
            SponsorFund(),
            AddSystemRewardOperator()
        ]

        cls.__mandatory_task_builders = [
            GenerateBlock()
        ]

        cls.__random_task_builders = [
            UpdateCoreStakeGradeFlag(),
            UpdateBtcStakeGradeFlag(),
            UpdateBtcLstStakeGradePercent()
        ]

    def __init__(self):
        super().__init__()

    def generate_one_time_task(self, advanced_round):
        super().generate_one_time_task(advanced_round)

        tasks = []
        for builder in ChainTaskGenerator.__one_time_task_builders:
            res = builder.build(self)
            if res is not None and len(res) > 0:
                tasks.extend(res)

            builder.disable()

        return tasks

    def generate_mandatory_task(self, advanced_round):
        super().generate_one_time_task(advanced_round)

        tasks = []
        for builder in ChainTaskGenerator.__mandatory_task_builders:
            res = builder.build(self)
            if res is not None and len(res) > 0:
                tasks.extend(res)

        return tasks

    def generate_random_task(self, advanced_round):
        super().generate_one_time_task(advanced_round)

        tasks = []
        for builder in ChainTaskGenerator.__random_task_builders:
            res = builder.build(self)
            if res is not None and len(res) > 0:
                tasks.extend(res)

        return tasks


class CandidateTaskGenerator(TaskGenerator):
    __next_operator_id = 0
    __random_task_builders = None

    @classmethod
    def reset(cls):
        cls.__next_operator_id = 0
        cls.__random_task_builders = None

    @classmethod
    def init_supported_task_builders(cls):
        if cls.__random_task_builders is not None:
            return

        cls.__random_task_builders = [
            RegisterCandidate(),
            AddMargin(),
            AcceptDelegate(),
            SlashValidator(),
            RefuseDelegate(),
            UnregisterCandidate(),
            StakePower()
        ]

    @classmethod
    def __alloc_operator_id(cls):
        cur_id = cls.__next_operator_id
        cls.__next_operator_id += 1
        return cur_id

    def __init__(self):
        super().__init__()
        self.operator_id = CandidateTaskGenerator.__alloc_operator_id()
        self.operator = f"{constants.OPERATOR_NAME_PREFIX}{self.operator_id}"

    def get_operator(self):
        return self.operator

    def generate_random_task(self, advanced_round):
        super().generate_one_time_task(advanced_round)

        tasks = []
        for builder in CandidateTaskGenerator.__random_task_builders:
            res = builder.build(self)
            if res is not None and len(res) > 0:
                tasks.extend(res)

        return tasks


class DelegatorTaskGenerator(TaskGenerator):
    __next_delegator_id = 0
    __random_task_builders = None

    @classmethod
    def reset(cls):
        cls.__next_delegator_id = 0
        cls.__random_task_builders = None

    @classmethod
    def init_supported_task_builders(cls):
        if cls.__random_task_builders is not None:
            return

        cls.__random_task_builders = [
            StakeCore(),
            UnstakeCore(),
            TransferCore(),
            StakeBtc(),
            TransferBtc(),
            StakeLSTBtc(),
            TransferLSTBtc(),
            BurnLSTBtcAndPayBtcToRedeemer(),
            ClaimReward()
        ]

    @classmethod
    def __alloc_delegator_id(cls):
        cur_id = cls.__next_delegator_id
        cls.__next_delegator_id += 1
        return cur_id

    def __init__(self):
        super().__init__()
        self.delegator_id = DelegatorTaskGenerator.__alloc_delegator_id()
        self.delegator = f"{constants.DELEGATOR_NAME_PREFIX}{self.delegator_id}"

    def get_delegator(self):
        return self.delegator

    def generate_random_task(self, advanced_round):
        super().generate_one_time_task(advanced_round)

        tasks = []
        for builder in DelegatorTaskGenerator.__random_task_builders:
            res = builder.build(self)
            if res is not None and len(res) > 0:
                tasks.extend(res)

        return tasks


############### end task generator ################


CHAIN_TASK_BASE_TYPE = constants.CHAIN_TASK_BASE_TYPE
CANDIDATE_TASK_BASE_TYPE = constants.CANDIDATE_TASK_BASE_TYPE
DELEGATOR_TASK_BASE_TYPE = constants.DELEGATOR_TASK_BASE_TYPE


class TaskType(Enum):
    Unknown = 0
    SponsorFund = CHAIN_TASK_BASE_TYPE
    GenerateBlock = CHAIN_TASK_BASE_TYPE + 1
    UpdateCoreStakeGradeFlag = CHAIN_TASK_BASE_TYPE + 2
    UpdateCoreStakeGrades = CHAIN_TASK_BASE_TYPE + 3
    UpdateBtcStakeGradeFlag = CHAIN_TASK_BASE_TYPE + 4
    UpdateBtcStakeGrades = CHAIN_TASK_BASE_TYPE + 5
    UpdateBtcLstStakeGradeFlag = CHAIN_TASK_BASE_TYPE + 6
    UpdateBtcLstStakeGradePercent = CHAIN_TASK_BASE_TYPE + 7
    AddSystemRewardOperator = CHAIN_TASK_BASE_TYPE + 8
    RegisterCandidate = CANDIDATE_TASK_BASE_TYPE
    SlashValidator = CANDIDATE_TASK_BASE_TYPE + 1
    AddMargin = CANDIDATE_TASK_BASE_TYPE + 2
    RefuseDelegate = CANDIDATE_TASK_BASE_TYPE + 3
    AcceptDelegate = CANDIDATE_TASK_BASE_TYPE + 4
    UnregisterCandidate = CANDIDATE_TASK_BASE_TYPE + 5
    StakeCore = DELEGATOR_TASK_BASE_TYPE
    UnstakeCore = DELEGATOR_TASK_BASE_TYPE + 1
    TransferCore = DELEGATOR_TASK_BASE_TYPE + 2
    StakePower = DELEGATOR_TASK_BASE_TYPE + 3
    StakeBtc = DELEGATOR_TASK_BASE_TYPE + 4
    TransferBtc = DELEGATOR_TASK_BASE_TYPE + 5
    StakeLSTBtc = DELEGATOR_TASK_BASE_TYPE + 6
    TransferLSTBtc = DELEGATOR_TASK_BASE_TYPE + 7
    BurnLSTBtcAndPayBtcToRedeemer = DELEGATOR_TASK_BASE_TYPE + 8
    UnstakeLSTBtc = DELEGATOR_TASK_BASE_TYPE + 9
    ClaimReward = DELEGATOR_TASK_BASE_TYPE + 10


class TaskBuilder:
    def __init__(self):
        self.type = TaskType.Unknown.value
        self.next_builder = None
        self.enabled = True

    def __repr__(self):
        return f"({self.__class__.__name__})"

    def disable(self):
        self.enabled = False

    def enable(self):
        self.enabled = True

    def is_enabled(self, task_generator):
        if not self.enabled:
            return False

        advanced_round = task_generator.get_advanced_round()
        if advanced_round == 0:
            return False

        data_center = task_generator.get_data_center()
        probability = data_center.get_probability(self.__class__.__name__)

        print(f"{self.__class__.__name__}:{probability}")
        p = random.randint(1, constants.PROBABILITY_DECIMALS)
        return p <= probability

    def build(self, task_generator):
        if not self.is_enabled(task_generator):
            return

        tasks = self.self_build(task_generator)
        if tasks is None:
            return

        next_tasks = self.next_build(task_generator)
        if next_tasks is not None and len(next_tasks) > 0:
            tasks.extend(next_tasks)

        return tasks

    def self_build(self, task_generator):
        pass

    def next_build(self, task_generator):
        if self.next_builder is None or \
                not self.next_builder.is_enabled(task_generator):
            return

        return self.next_builder.build(task_generator)

    def build_confirm_btc_tx_task(self, tx_symbol):
        delay_minutes = random.randint(12, 60)
        return [ConfirmBtcTx.__name__, tx_symbol, delay_minutes]


############## chain task builder ################
class SponsorFund(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.SponsorFund.value

    def is_enabled(self, task_generator):
        return self.enabled

    def self_build(self, task_generator):
        tasks = []

        data_center = task_generator.get_data_center()
        sponsees = data_center.get_sponsees()

        for sponsee, fund_amount in sponsees.items():
            assert fund_amount is not None

            if fund_amount > 0:
                task = [self.__class__.__name__, sponsee, fund_amount]
                tasks.append(task)

        return tasks


# it is only used to add StakeHub as the operator of SystemReward
class AddSystemRewardOperator(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.AddSystemRewardOperator.value

    def is_enabled(self, task_generator):
        return self.enabled

    def self_build(self, task_generator):
        task = [self.__class__.__name__, "StakeHub"]
        return [task]


class GenerateBlock(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.GenerateBlock.value

    def self_build(self, task_generator):
        data_center = task_generator.get_data_center()
        candidate_count = data_center.get_candidate_count()
        assert candidate_count > 0

        block_count_per_validator = random.randint(1, constants.MAX_BLOCK_COUNT_PER_VALIDATOR)
        block_count = block_count_per_validator * candidate_count
        block_count += random.randint(0, candidate_count)

        task = [self.__class__.__name__, block_count]
        return [task]


class UpdateCoreStakeGradeFlag(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateCoreStakeGradeFlag.value

        self.next_builder = UpdateCoreStakeGrades()

    def self_build(self, task_generator):
        value = random.randint(0, 1)
        if value > 0:
            self.next_builder.enable()
        else:
            self.next_builder.disable()

        task = [self.__class__.__name__, value]
        return [task]


class UpdateCoreStakeGrades(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateCoreStakeGrades.value

    def is_enabled(self, task_generator):
        return self.enabled

    def self_build(self, task_generator):
        # discount grades
        grade_count = random.randint(constants.MIN_GRADE_COUNT, constants.MAX_GRADE_COUNT)
        level_step = constants.PERCENT_DECIMALS // (grade_count - 1)
        percent_step = level_step

        min_level = 0
        min_percent = random.randint(1, percent_step - 1)
        grades = [min_level, min_percent]
        for i in range(1, grade_count):
            level = min_level + i * level_step

            percent = min(min_percent + i * percent_step, constants.PERCENT_DECIMALS)
            assert percent > grades[len(grades) - 1]

            grades.append(level);
            grades.append(percent)

        # multiple grades
        multiple = random.randint(1, constants.MAX_CORE_STAKE_GRADE_PERCENT // constants.PERCENT_DECIMALS)
        if multiple > 1:
            percent = constants.PERCENT_DECIMALS * multiple
            level = constants.PERCENT_DECIMALS * multiple * (
                        constants.MAX_CORE_STAKE_GRADE_LEVEL // constants.MAX_CORE_STAKE_GRADE_PERCENT)
            grades.append(level)
            grades.append(percent)

        task = [self.__class__.__name__] + grades
        return [task]


class UpdateBtcStakeGradeFlag(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateBtcStakeGradeFlag.value

        self.next_builder = UpdateBtcStakeGrades()

    def self_build(self, task_generator):
        value = random.randint(0, 1)
        if value > 0:
            self.next_builder.enable()
        else:
            self.next_builder.disable()

        task = [self.__class__.__name__, value]
        return [task]


class UpdateBtcStakeGrades(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateBtcStakeGrades.value

    def is_enabled(self, task_generator):
        return self.enabled

    def self_build(self, task_generator):
        max_level = random.randint(0, constants.MAX_BTC_STAKE_GRADE_LEVEL)
        max_percent = constants.PERCENT_DECIMALS
        grade_count = random.randint(5, 10)

        level_step = max_level // grade_count
        percent_step = max_percent // grade_count

        level = 0
        percent = 1
        grades = [level, percent]
        for i in range(grade_count):
            level += level_step
            percent += percent_step

            if i == grade_count - 1:
                assert level <= max_level, f"level={level}, max_level={max_level}, i={i}, level_step={level_step}, grade_count={grade_count}"
                level = max(max_level, level)
                percent = max_percent
                assert percent >= grades[len(grades) - 1]

            grades.append(level)
            grades.append(percent)

        task = [self.__class__.__name__] + grades
        return [task]


class UpdateBtcLstStakeGradeFlag(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateBtcLstStakeGradeFlag.value

        self.next_builder = UpdateBtcLstStakeGradePercent()

    def self_build(self, task_generator):
        value = random.randint(0, 1)
        if value > 0:
            self.next_builder.enable()
        else:
            self.next_builder.disable()

        task = [self.__class__.__name__, value]
        return [task]


class UpdateBtcLstStakeGradePercent(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UpdateBtcLstStakeGradePercent.value

    def self_build(self, task_generator):
        value = random.randint(1, constants.MAX_BTC_LST_STAKE_GRADE_PERCENT)
        task = [self.__class__.__name__, value]
        return [task]


############### end chain task build #############


############ candidate task builder ##############
class RegisterCandidate(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.RegisterCandidate.value

    def is_enabled(self, task_generator):
        if not self.enabled:
            return False

        data_center = task_generator.get_data_center()
        probability = data_center.get_probability(self.__class__.__name__)
        p = random.randint(1, constants.PROBABILITY_DECIMALS)
        return p <= probability

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if data_center.is_registered(operator):
            return

        data_center.register_candidate(operator)

        commission = random.randint(1, constants.MAX_CANDIDATE_COMMISSION)
        task = [self.__class__.__name__, operator, commission]

        return [task]


class SlashValidator(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.SlashValidator.value

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.is_available(operator):
            return

        max_count = data_center.get_felony_threshold()
        count = random.randint(1, max_count * 2)
        task = [self.__class__.__name__, operator, count]

        data_center.slash_validator(operator, count)
        return [task]


class AddMargin(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.AddMargin.value

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.is_registered(operator):
            return

        if not data_center.is_lack_of_collateral(operator):
            return

        task = [self.__class__.__name__, operator]

        data_center.unset_margin(operator)
        return [task]


class RefuseDelegate(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.RefuseDelegate.value

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.is_registered(operator):
            return

        if not data_center.can_delegate(operator):
            return

        task = [self.__class__.__name__, operator]

        data_center.refuse_delegate(operator)
        return [task]


class UnregisterCandidate(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UnregisterCandidate.value

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.can_unregistered(operator):
            return

        data_center.unregister_candidate(operator)

        task = [self.__class__.__name__, operator]
        return [task]


class AcceptDelegate(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.AcceptDelegate.value

    def self_build(self, task_generator):
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.is_registered(operator):
            return

        if data_center.can_delegate(operator):
            return

        task = [self.__class__.__name__, operator]

        data_center.accept_delegate(operator)
        return [task]


class StakePower(TaskBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.StakePower.value

    def self_build(self, task_generator):
        # delegatee
        operator = task_generator.get_operator()

        data_center = task_generator.get_data_center()
        if not data_center.is_registered(operator):
            return

        # lagged round
        # lagged_round = random.randint(0, 6)
        lagged_round = 6

        # random generate miner list
        data_center = task_generator.get_data_center()
        miners = data_center.choice_miners()
        task = [self.__class__.__name__, operator, lagged_round] + miners

        data_center.stake_power(lagged_round, miners)
        return [task]


######### end candidate task builder ############


############ delegator task builder #############
class AssetOperationBuilder(TaskBuilder):
    def __init__(self):
        super().__init__()

    def random_stake_amount(self, delegator):
        delegator_addr = AccountMgr.get_delegator_addr(delegator)
        delegator_balance = delegator_addr.balance()
        return random.randint(1, min(delegator_balance // 100, 1000))


class StakeCore(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.StakeCore.value

    def self_build(self, task_generator):
        # random choice a candidate
        data_center = task_generator.get_data_center()
        delegatee = data_center.choice_available_candidate()
        if delegatee is None:
            return

        # delegator
        delegator = task_generator.get_delegator()

        # init amount by delegator balance
        amount = self.random_stake_amount(delegator)
        task = [self.__class__.__name__, delegator, delegatee, amount]

        data_center.stake_core(delegator, delegatee, amount)
        return [task]


class UnstakeCore(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.UnstakeCore.value

    def self_build(self, task_generator):
        # delegator
        delegator = task_generator.get_delegator()

        # random choice a staked candidate
        data_center = task_generator.get_data_center()
        delegatee, staked_amount = data_center.choice_core_staked_candidate(delegator)
        if delegatee is None:
            return

        # random init undelegate amount
        amount = random.randint(1, staked_amount)
        task = [self.__class__.__name__, delegator, delegatee, amount]

        data_center.unstake_core(delegator, delegatee, amount)
        return [task]


class TransferCore(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.TransferCore.value

    def self_build(self, task_generator):
        # delegator
        delegator = task_generator.get_delegator()

        # random choice a staked candidate
        data_center = task_generator.get_data_center()
        from_delegatee, staked_amount = data_center.choice_core_staked_candidate(delegator)
        if from_delegatee is None:
            return

        # random choice a candidate to stake
        to_delegatee = data_center.choice_available_candidate_exclude(from_delegatee)
        if to_delegatee is None:
            return

        # random init amount
        amount = random.randint(1, staked_amount)
        task = [self.__class__.__name__, delegator, from_delegatee, to_delegatee, amount]

        data_center.transfer_core(delegator, from_delegatee, to_delegatee, amount)
        return [task]


class CreateStakeLockTx(TaskBuilder):
    pass


class ConfirmBtcTx(TaskBuilder):
    pass


class StakeBtc(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.StakeBtc.value

    def self_build(self, task_generator):
        lock_tx_task, tx_symbol, delegator, delegatee, lock_round = self.build_lock_tx_task(task_generator)
        confirm_tx_task = self.build_confirm_btc_tx_task(tx_symbol)
        stake_btc_task = [self.__class__.__name__, tx_symbol, delegator]

        data_center = task_generator.get_data_center()
        data_center.stake_btc(delegator, delegatee, tx_symbol, lock_round)
        return [lock_tx_task, confirm_tx_task, stake_btc_task]

    def build_lock_tx_task(self, task_generator):
        # tx symbol
        data_center = task_generator.get_data_center()
        tx_symbol = data_center.alloc_tx_symbol()

        # delegator
        delegator = task_generator.get_delegator()

        # delegatee
        data_center = task_generator.get_data_center()
        delegatee = data_center.choice_candidate()

        # bitcoin amount 0.01 ~ 2
        amount = random.randint(1, 200) / 100

        # lock round
        lock_round = random.randint(5, 365)

        # payment type
        payment_type, redeem_script_type = \
            data_center.choice_btc_stake_lock_script()
        assert payment_type is not None and \
               redeem_script_type is not None

        return [
            CreateStakeLockTx.__name__,
            tx_symbol,
            delegator,
            delegatee,
            amount,
            lock_round,
            payment_type,
            redeem_script_type
        ], tx_symbol, delegator, delegatee, lock_round


class TransferBtc(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.TransferBtc.value

    def self_build(self, task_generator):
        # delegator
        delegator = task_generator.get_delegator()

        # from delegatee and transferable tx
        data_center = task_generator.get_data_center()
        from_delegatee, tx_symbol = data_center.choice_transferable_btc(delegator)
        if from_delegatee is None or tx_symbol is None:
            return

        # to delegatee
        to_delegatee = data_center.choice_available_candidate_exclude(from_delegatee)
        if to_delegatee is None:
            return

        task = [self.__class__.__name__, tx_symbol, delegator, to_delegatee]

        data_center.transfer_btc(delegator, from_delegatee, to_delegatee, tx_symbol)
        return [task]


class CreateLSTLockTx(TaskBuilder):
    pass


class AddWallet(TaskBuilder):
    pass


class StakeLSTBtc(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.StakeLSTBtc.value

    def self_build(self, task_generator):
        lst_lock_tx_task, tx_symbol, amount, delegator = self.build_lock_tx_task(task_generator)
        confirm_tx_task = self.build_confirm_btc_tx_task(tx_symbol)
        add_wallet_task = [AddWallet.__name__, tx_symbol]
        stake_btc_lst_task = [self.__class__.__name__, tx_symbol, delegator]

        data_center = task_generator.get_data_center()
        data_center.stake_btc_lst(delegator, tx_symbol, amount)

        return [lst_lock_tx_task, confirm_tx_task, add_wallet_task, stake_btc_lst_task]

    def build_lock_tx_task(self, task_generator):
        # tx symbol
        data_center = task_generator.get_data_center()
        tx_symbol = data_center.alloc_tx_symbol()

        # delegator
        delegator = task_generator.get_delegator()

        # bitcoin amount 0.01 ~ 2
        amount = random.randint(1, 200) / 100

        # payment type
        payment_type, redeem_script_type = \
            data_center.choice_btc_lst_stake_lock_script()
        assert payment_type is not None

        if redeem_script_type is not None:
            return [
                CreateLSTLockTx.__name__,
                tx_symbol,
                delegator,
                amount,
                payment_type,
                redeem_script_type
            ], tx_symbol, amount, delegator
        else:
            return [
                CreateLSTLockTx.__name__,
                tx_symbol,
                delegator,
                amount,
                payment_type
            ], tx_symbol, amount, delegator


class TransferLSTBtc(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.TransferLSTBtc.value

    def self_build(self, task_generator):
        from_delegator = task_generator.get_delegator()

        data_center = task_generator.get_data_center()
        stake_amount = data_center.get_stake_info(from_delegator).get_btc_lst_stake_amount()
        if stake_amount == 0:
            return

        transfer_amount = round(random.uniform(0, stake_amount), 8)

        to_delegator = data_center.choice_delegator()
        if to_delegator == from_delegator:
            return

        task = [self.__class__.__name__, from_delegator, to_delegator, transfer_amount]

        data_center.transfer_btc_lst(from_delegator, to_delegator, transfer_amount)
        return [task]


class UnstakeLSTBtc(TaskBuilder):
    pass


class BurnLSTBtcAndPayBtcToRedeemer(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.BurnLSTBtcAndPayBtcToRedeemer.value

    def self_build(self, task_generator):
        pay_to_redeemer_tx_task, tx_symbol, amount, redeemer = self.build_redeem_and_pay_task(task_generator)
        if amount == 0:
            return

        confirm_tx_task = self.build_confirm_btc_tx_task(tx_symbol)
        unstake_btc_lst_task = [UnstakeLSTBtc.__name__, tx_symbol, redeemer]

        data_center = task_generator.get_data_center()
        data_center.redeem_btc_lst(redeemer, amount)

        return [pay_to_redeemer_tx_task, confirm_tx_task, unstake_btc_lst_task]

    def build_redeem_and_pay_task(self, task_generator):
        # tx symbol
        data_center = task_generator.get_data_center()
        tx_symbol = data_center.alloc_tx_symbol()

        # redeemer
        redeemer = task_generator.get_delegator()

        # redeem amount
        amount = data_center.choice_redeem_amount(redeemer)

        # payment type
        payment_type, redeem_script_type = \
            data_center.choice_btc_lst_stake_lock_script()
        assert payment_type is not None

        if redeem_script_type is not None:
            return [
                self.__class__.__name__,
                tx_symbol,
                redeemer,
                amount,
                payment_type,
                redeem_script_type
            ], tx_symbol, amount, redeemer
        else:
            return [
                self.__class__.__name__,
                tx_symbol,
                redeemer,
                amount,
                payment_type
            ], tx_symbol, amount, redeemer


class ClaimReward(AssetOperationBuilder):
    def __init__(self):
        super().__init__()
        self.type = TaskType.ClaimReward.value

    def self_build(self, task_generator):
        delegator = task_generator.get_delegator()

        data_center = task_generator.get_data_center()
        if not data_center.is_staked_asset(delegator):
            return

        task = [self.__class__.__name__, delegator]
        return [task]
########## end delegator task builder ############
