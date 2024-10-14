from abc import ABC, abstractmethod
from brownie import *
from . import chain_checker
from . import chain_handler
from .account_mgr import AccountMgr

addr_to_name = AccountMgr.addr_to_name


class TaskHandler(ABC):
    def __init__(self):
        pass

    def set_chain(self, chain):
        self.chain = chain

    def set_task(self, task):
        self.task = task

    def init_checker(self):
        assert self.chain is not None
        assert self.task is not None
        self.checker = chain_checker.ChainChecker(self.chain, self.task)

    def init_handler(self):
        assert self.chain is not None
        self.chain_handler = chain_handler.ChainHandler(self.chain)

    def on_task_ready(self):
        print("on_task_ready>>>>>>")

    def on_task_finish(self):
        print(f"on_task_finish>>>>>>")

    def check_state(self):
        pass


class SponsorFund(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.sponsee)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain.add_balance(self.task.sponsee, self.task.amount)
        self.check_state()

    def check_state(self):
        self.checker.check_balance(self.task.sponsee)


class RegisterCandidate(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(CandidateHubMock[0])
        self.chain.init_balance(self.task.fee_addr)
        self.chain.init_balance(self.task.operator_addr)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.add_candidate(
            self.task.operator_addr,
            self.task.consensus_addr,
            self.task.fee_addr,
            self.task.commission,
            self.task.margin,
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(CandidateHubMock[0])
        self.checker.check_balance(self.task.operator_addr)
        self.checker.check_candidate(self.task.operator_addr)


class UnregisterCandidate(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(CandidateHubMock[0])
        self.chain.init_balance(SystemRewardMock[0])
        self.chain.init_balance(self.task.operator_addr)
        self.candidate = self.chain.get_candidate(self.task.operator_addr)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.remove_candidate(
            self.task.operator_addr
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(CandidateHubMock[0])
        self.checker.check_balance(SystemRewardMock[0])
        self.checker.check_balance(self.task.operator_addr)
        self.checker.check_candidate_removed(self.candidate)


class SlashValidator(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(Burn[0])
        self.chain.init_balance(Foundation[0])
        self.chain.init_balance(SystemRewardMock[0])
        self.chain.init_balance(CandidateHubMock[0])
        self.checker.check_slash_indicator(self.task.operator_addr)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.slash_validator(
            self.task.operator_addr,
            self.task.block_number
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(Burn[0])
        self.checker.check_balance(Foundation[0])
        self.checker.check_balance(SystemRewardMock[0])
        self.checker.check_balance(CandidateHubMock[0])
        self.checker.check_slash_indicator(self.task.operator_addr)
        self.checker.check_jailed_round(self.task.operator_addr)
        self.checker.check_candidate(self.task.operator_addr)
        self.checker.check_validator_incomes()


class AddMargin(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.operator_addr)
        self.chain.init_balance(CandidateHubMock[0])

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.add_margin(
            self.task.operator_addr,
            self.task.amount
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(self.task.operator_addr)
        self.checker.check_balance(CandidateHubMock[0])
        self.checker.check_candidate(self.task.operator_addr)


class RefuseDelegate(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.refuse_delegate(self.task.operator_addr)

        self.check_state()

    def check_state(self):
        self.checker.check_candidate(self.task.operator_addr)


class AcceptDelegate(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.accept_delegate(self.task.operator_addr)

        self.check_state()

    def check_state(self):
        self.checker.check_candidate(self.task.operator_addr)


class GenerateBlock(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(ValidatorSetMock[0])

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.deposit_block_reward(
            self.task.miner,
            self.task.tx_fee,
            self.task.block_number
        )

        self.check_state()

    def check_state(self):
        self.checker.check_balance(ValidatorSetMock[0])
        self.checker.check_validator_income(self.task.miner)
        self.checker.check_total_income()


class TurnRound(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(Burn[0])
        self.chain.init_balance(Foundation[0])
        self.chain.init_balance(SystemRewardMock[0])
        self.chain.init_balance(ValidatorSetMock[0])
        self.chain.init_balance(StakeHubMock[0])
        self.checker.check_candidate_statuses()
        self.checker.check_validator_incomes()
        self.checker.check_validator_scores()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.turn_round()

        self.check_state()

    def check_state(self):
        self.checker.check_current_round()
        self.checker.check_candidate_statuses()
        self.checker.check_validator_incomes()
        self.checker.check_validator_stake_amounts()
        self.checker.check_validator_scores()
        self.checker.check_balance(Burn[0])
        self.checker.check_balance(Foundation[0])
        self.checker.check_balance(SystemRewardMock[0])
        self.checker.check_balance(ValidatorSetMock[0])
        self.checker.check_balance(StakeHubMock[0])

        print(f"ROUND={self.chain.get_round()} validate set")
        for validator in self.chain.get_validators().values():
            print(f"validator: {addr_to_name(validator.get_operator_addr())}")


class CreateStakeLockTx(TaskHandler):
    pass


class CreateLSTLockTx(TaskHandler):
    pass


class ConfirmBtcTx(TaskHandler):
    pass


class AddWallet(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.add_wallet(self.task.payment)

        self.check_state()

    def check_state(self):
        self.checker.check_wallet(self.task.payment)


class StakeCore(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.delegator)
        self.chain.init_balance(CoreAgentMock[0])
        self.checker.check_core_history_reward(self.task.delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.delegate_core(
            self.task.delegator,
            self.task.delegatee,
            self.task.amount
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(CoreAgentMock[0])
        self.checker.check_balance(self.task.delegator)
        self.checker.check_candidate_core_realtime_amount(self.task.delegatee)
        self.checker.check_delegator_core_realtime_amount(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_change_round(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_transferred_amount(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_total_amount(self.task.delegator)
        self.checker.check_delegator_core_stake_nodes(self.task.delegator)
        self.checker.check_core_history_reward(self.task.delegator)


class UnstakeCore(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.delegator)
        self.chain.init_balance(CoreAgentMock[0])
        self.checker.check_core_history_reward(self.task.delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.undelegate_core(
            self.task.delegator,
            self.task.delegatee,
            self.task.amount
        )
        self.check_state()

    def check_state(self):
        self.checker.check_balance(CoreAgentMock[0])
        self.checker.check_balance(self.task.delegator)
        self.checker.check_candidate_core_realtime_amount(self.task.delegatee)
        self.checker.check_delegator_core_realtime_amount(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_stake_amount(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_change_round(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_transferred_amount(self.task.delegator, self.task.delegatee)
        self.checker.check_delegator_core_total_amount(self.task.delegator)
        self.checker.check_delegator_core_stake_nodes(self.task.delegator)
        self.checker.check_core_history_reward(self.task.delegator)


class TransferCore(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.delegator)
        self.chain.init_balance(CoreAgentMock[0])
        self.checker.check_core_history_reward(self.task.delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.transfer_core(
            self.task.delegator,
            self.task.from_delegatee,
            self.task.to_delegatee,
            self.task.amount
        )

        self.check_state()

    def check_state(self):
        self.checker.check_balance(CoreAgentMock[0])
        self.checker.check_balance(self.task.delegator)
        self.checker.check_candidate_core_realtime_amount(self.task.from_delegatee)
        self.checker.check_candidate_core_realtime_amount(self.task.to_delegatee)
        self.checker.check_delegator_core_total_amount(self.task.delegator)
        self.checker.check_delegator_core_stake_nodes(self.task.delegator)

        self.checker.check_delegator_core_realtime_amount(self.task.delegator, self.task.from_delegatee)
        self.checker.check_delegator_core_stake_amount(self.task.delegator, self.task.from_delegatee)
        self.checker.check_delegator_core_change_round(self.task.delegator, self.task.from_delegatee)
        self.checker.check_delegator_core_transferred_amount(self.task.delegator, self.task.from_delegatee)

        self.checker.check_delegator_core_realtime_amount(self.task.delegator, self.task.to_delegatee)
        self.checker.check_delegator_core_stake_amount(self.task.delegator, self.task.to_delegatee)
        self.checker.check_delegator_core_change_round(self.task.delegator, self.task.to_delegatee)
        self.checker.check_delegator_core_transferred_amount(self.task.delegator, self.task.to_delegatee)

        self.checker.check_core_history_reward(self.task.delegator)


class StakePower(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.delegate_power(
            self.task.power_round,
            self.task.delegatee,
            self.task.miners
        )
        self.check_state()

    def check_state(self):
        self.checker.check_round_powers(self.task.power_round, self.task.delegatee)


class StakeBtc(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_btc_stake_realtime_amount(self.task.tx_data.get_delegatee())

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.delegate_btc(self.task.tx_data)
        self.check_state()

    def check_state(self):
        txid = self.task.tx_data.get_txid()
        delegatee = self.task.tx_data.get_delegatee()
        delegator = self.task.tx_data.get_delegator()

        self.checker.check_btc_stake_tx(txid)
        self.checker.check_btc_stake_receipt(txid)
        self.checker.check_btc_stake_realtime_amount(delegatee)
        self.checker.check_delegator_btc_realtime_amount(delegator)
        self.checker.check_btc_stake_history_reward(delegator)
        self.checker.check_total_unclaimed_reward()


class TransferBtc(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.transfer_btc(
            self.task.delegator,
            self.task.txid,
            self.task.to_delegatee
        )

        self.check_state()

    def check_state(self):
        txid = self.task.tx_data.get_txid()
        from_delegatee = self.task.tx_data.get_delegatee()
        to_delegatee = self.task.to_delegatee
        delegator = self.task.tx_data.get_delegator()
        self.checker.check_btc_stake_tx(txid)
        self.checker.check_btc_stake_receipt(txid)
        self.checker.check_btc_stake_realtime_amount(from_delegatee)
        self.checker.check_btc_stake_realtime_amount(to_delegatee)
        self.checker.check_delegator_btc_realtime_amount(delegator)
        self.checker.check_btc_stake_history_reward(delegator)
        self.checker.check_total_unclaimed_reward()


class StakeLSTBtc(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        delegator = self.task.tx_data.get_delegator()
        self.chain.init_btc_lst_balance(delegator)
        self.checker.check_delegator_btc_lst_history_reward(delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.delegate_btc_lst(self.task.tx_data)

        self.check_state()

    def check_state(self):
        txid = self.task.tx_data.get_txid()
        delegator = self.task.tx_data.get_delegator()
        self.checker.check_btc_lst_balance(delegator)
        self.checker.check_btc_lst_stake_tx(txid)
        self.checker.check_btc_lst_total_realtime_amount()
        self.checker.check_delegator_btc_lst_stake_amount(delegator)
        self.checker.check_delegator_btc_lst_realtime_amount(delegator)
        self.checker.check_delegator_btc_lst_change_round(delegator)
        self.checker.check_delegator_btc_lst_history_reward(delegator)
        self.checker.check_total_unclaimed_reward()


class TransferLSTBtc(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_btc_lst_balance(self.task.from_delegator)
        self.chain.init_btc_lst_balance(self.task.to_delegator)
        self.checker.check_btc_lst_balance(self.task.from_delegator)
        self.checker.check_btc_lst_balance(self.task.to_delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.transfer_btc_lst(
            self.task.from_delegator,
            self.task.to_delegator,
            self.task.amount
        )

        self.check_state()

    def check_state(self):
        from_delegator = self.task.from_delegator
        to_delegator = self.task.to_delegator

        self.checker.check_btc_lst_balance(from_delegator)
        self.checker.check_btc_lst_balance(to_delegator)

        self.checker.check_btc_lst_total_realtime_amount()
        self.checker.check_total_unclaimed_reward()

        self.checker.check_delegator_btc_lst_stake_amount(from_delegator)
        self.checker.check_delegator_btc_lst_realtime_amount(from_delegator)
        self.checker.check_delegator_btc_lst_change_round(from_delegator)
        self.checker.check_delegator_btc_lst_history_reward(from_delegator)

        self.checker.check_delegator_btc_lst_stake_amount(to_delegator)
        self.checker.check_delegator_btc_lst_realtime_amount(to_delegator)
        self.checker.check_delegator_btc_lst_change_round(to_delegator)
        self.checker.check_delegator_btc_lst_history_reward(to_delegator)


class BurnLSTBtcAndPayBtcToRedeemer(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_btc_lst_balance(self.task.delegator)

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.redeem_btc_lst(
            self.task.delegator,
            self.task.amount,
            self.task.payment
        )
        self.check_state()

    def check_state(self):
        delegator = self.task.delegator
        self.checker.check_btc_lst_balance(delegator)
        self.checker.check_btc_lst_redeem_requests()
        self.checker.check_btc_lst_total_realtime_amount()
        self.checker.check_delegator_btc_lst_stake_amount(delegator)
        self.checker.check_delegator_btc_lst_realtime_amount(delegator)
        self.checker.check_delegator_btc_lst_change_round(delegator)
        self.checker.check_delegator_btc_lst_history_reward(delegator)


class UnstakeLSTBtc(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.undelegate_btc_lst(self.task.tx_data)
        self.check_state()

    def check_state(self):
        txid = self.task.tx_data.get_txid()
        self.checker.check_btc_lst_redeem_proof_tx(txid)
        self.checker.check_btc_lst_redeem_requests()


class ClaimReward(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.chain.init_balance(self.task.account)
        self.chain.init_balance(StakeHubMock[0])
        self.chain.init_balance(SystemRewardMock[0])

        # in fact the relayer has no rewards
        self.checker.check_creditor_contributions(self.task.account)
        self.checker.check_balance(StakeHubMock[0])
        self.checker.check_balance(SystemRewardMock[0])
        self.checker.check_history_reward(self.task.account)
        self.checker.check_balance(self.task.account)
        self.checker.check_total_unclaimed_reward()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.claim_reward(self.task.account)
        self.check_state()

    def check_state(self):
        self.checker.check_delegator_core_stake_nodes(self.task.account)
        self.checker.check_history_reward(self.task.account)
        self.checker.check_balance(self.task.account)
        self.checker.check_total_unclaimed_reward()
        self.checker.check_balance(SystemRewardMock[0])
        self.checker.check_balance(StakeHubMock[0])
        # in fact the relayer has no rewards
        self.checker.check_creditor_contributions(self.task.account)


class AddSystemRewardOperator(TaskHandler):
    pass


class UpdateCoreStakeGradeFlag(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_core_stake_grade_flag()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_core_stake_grade_flag(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_core_stake_grade_flag()


class UpdateCoreStakeGrades(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_core_stake_grades()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_core_stake_grades(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_core_stake_grades()


class UpdateBtcStakeGradeFlag(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_btc_stake_grade_flag()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_btc_stake_grade_flag(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_btc_stake_grade_flag()


class UpdateBtcStakeGrades(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_btc_stake_grades()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_btc_stake_grades(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_btc_stake_grades()


class UpdateBtcLstStakeGradeFlag(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_btc_lst_stake_grade_flag()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_btc_lst_stake_grade_flag(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_btc_lst_stake_grade_flag()


class UpdateBtcLstStakeGradePercent(TaskHandler):
    def on_task_ready(self):
        super().on_task_ready()
        self.checker.check_btc_lst_stake_grade_percent()

    def on_task_finish(self):
        super().on_task_finish()
        self.chain_handler.update_btc_lst_stake_grade_percent(
            self.task.data
        )
        self.check_state()

    def check_state(self):
        self.checker.check_btc_lst_stake_grade_percent()


class CreatePayment(TaskHandler):
    pass
