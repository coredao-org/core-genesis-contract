from brownie import *
from .payment import BtcLSTLockWallet
from .delegator_stake_state import RedeemRequest
from .account_mgr import AccountMgr

addr_to_name = AccountMgr.addr_to_name


def assert_result(key, val_off_chain, val_on_chain):
    assert val_off_chain == val_on_chain, f"{key}={val_off_chain}, {key}_on_chain={val_on_chain}"


class ChainChecker:
    def __init__(self, chain, task):
        self.chain = chain
        self.task = task

    def check_current_round(self):
        assert_result(
            "round",
            self.chain.get_round(),
            self.chain.get_round_on_chain()
        )

    def check_candidate_statuses(self):
        candidates = self.chain.get_candidates()
        operator_addr_list = CandidateHubMock[0].getCandidates()
        # dataArr = CandidateHubMock[0].getDataArr()
        # print(f"dataArr={dataArr}")

        for i in range(len(operator_addr_list)):
            tuple_data = CandidateHubMock[0].candidateSet(i)
            operator_addr = tuple_data[0]

            candidate_off_chain = candidates[operator_addr]
            commission_on_chain = tuple_data[3]
            status_on_chain = tuple_data[5]

            commission = candidate_off_chain.get_commission()
            status = candidate_off_chain.get_status()
            # print(f"{addr_to_name(operator_addr)}, status_on_chain={status_on_chain}, status_off_chain={status}")

            assert_result(f"{addr_to_name(operator_addr)}_commission", commission, commission_on_chain)
            assert_result(f"{addr_to_name(operator_addr)}_status", status, status_on_chain)

    def check_validator_incomes(self):
        validators = self.chain.get_validators()
        operator_addr_list = ValidatorSetMock[0].getValidatorOps()
        assert len(operator_addr_list) == len(validators), f"{len(operator_addr_list)},{len(validators)}"

        for i in range(len(operator_addr_list)):
            validator_on_chain = ValidatorSetMock[0].currentValidatorSet(i)
            operator_addr = validator_on_chain[0]

            commission_on_chain = validator_on_chain[3]
            income_on_chain = validator_on_chain[4]

            validator_off_chain = validators[operator_addr]
            commission_in_use = validator_off_chain.get_commission_in_use()
            income = validator_off_chain.get_income()

            assert_result(f"{addr_to_name(operator_addr)}_commission", commission_in_use, commission_on_chain)
            assert_result(f"{addr_to_name(operator_addr)}_income", income, income_on_chain)
            self.check_balance(validator_off_chain.get_fee_addr())

    def check_validator_scores(self):
        validators = self.chain.get_validators()
        operator_addr_list = ValidatorSetMock[0].getValidatorOps()
        assert len(operator_addr_list) == len(validators)

        for i in range(len(operator_addr_list)):
            validator_on_chain = ValidatorSetMock[0].currentValidatorSet(i)
            operator_addr = validator_on_chain[0]

            validator = validators[operator_addr]
            stake_state = validator.get_stake_state()

            scores = [
                stake_state.get_total_score(),
                stake_state.get_score(self.chain.core_asset.name),
                stake_state.get_score(self.chain.power_asset.name),
                stake_state.get_score(self.chain.btc_asset.name)
            ]

            scores_on_chain = StakeHubMock[0].getCandidateScores(operator_addr)

            assert_result("scores", scores, list(scores_on_chain))

    def check_validator_stake_amounts(self):
        validators = self.chain.get_validators()
        operator_addr_list = ValidatorSetMock[0].getValidatorOps()
        assert len(operator_addr_list) == len(validators)

        for i in range(len(operator_addr_list)):
            operator_addr = operator_addr_list[i]
            self.check_candidate_core_stake_amount(operator_addr)
            self.check_candidate_btc_stake_amount(operator_addr)

        self.check_btc_lst_total_stake_amount()

    def check_validator_income(self, consensus_addr):
        income = self.chain.get_validator_income(consensus_addr)
        income_on_chain = self.chain.get_validator_income_on_chain(consensus_addr)

        assert_result("income", income, income_on_chain)

    def check_total_income(self):
        total_income = self.chain.get_total_income()
        total_income_on_chain = self.chain.get_total_income_on_chain()

        assert_result("total_income", total_income, total_income_on_chain)

    def check_balance(self, addr):
        balance = self.chain.get_balance(addr)
        balance_on_chain = self.chain.get_balance_on_chain(addr)

        assert_result(f"{addr_to_name(addr)}_balance", balance, balance_on_chain)

    def check_btc_lst_balance(self, addr):
        btc_lst_balance = self.chain.get_btc_lst_balance(addr)
        btc_lst_balance_on_chain = self.chain.get_btc_lst_balance_on_chain(addr)

        assert_result(f"{addr_to_name(addr)}_btc_lst_balance", btc_lst_balance, btc_lst_balance_on_chain)

    def check_candidate(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        candidate_on_chain = self.chain.get_candidate_on_chain(operator_addr)

        assert_result("candidate", candidate, candidate_on_chain)

    def check_candidate_removed(self, candidate):
        idx = CandidateHubMock[0].operateMap(candidate.get_operator_addr())
        assert idx == 0

    def check_slash_indicator(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        slash_count = candidate.get_slash_count()
        latest_slash_block = candidate.get_latest_slash_block()

        indicator_on_chain = \
            self.chain.get_slash_indicator_on_chain(candidate.get_consensus_addr())
        slash_count_on_chain = indicator_on_chain[1]
        latest_slash_block_on_chain = indicator_on_chain[0]

        assert_result(f"{addr_to_name(operator_addr)}_indicator_count", slash_count, slash_count_on_chain)
        assert_result(f"{addr_to_name(operator_addr)}_indicator_block", latest_slash_block, latest_slash_block_on_chain)

    def check_jailed_round(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        jailed_round = candidate.get_jailed_round()

        jailed_round_on_chain = self.chain.get_jailed_round_on_chain(operator_addr)

        assert_result(f"{addr_to_name(operator_addr)}_jailed_round", jailed_round, jailed_round_on_chain)

    def check_delegator_core_realtime_amount(self, delegator, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        candidate_stake_state = candidate.get_stake_state()
        core_asset_name = self.chain.get_core_asset().get_name()
        realtime_amount = candidate_stake_state.get_delegator_realtime_amount(core_asset_name, delegator)

        tuple_data = self.chain.get_delegator_core_stake_state_on_chain(delegator, delegatee)
        realtime_amount_on_chain = tuple_data[1]

        assert_result(
            f"{addr_to_name(delegator)}_{addr_to_name(delegatee)}_realtime_amount",
            realtime_amount,
            realtime_amount_on_chain
        )

    def check_delegator_core_stake_amount(self, delegator, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        candidate_stake_state = candidate.get_stake_state()
        core_asset_name = self.chain.get_core_asset().get_name()
        stake_amount = candidate_stake_state.get_delegator_stake_amount(core_asset_name, delegator)

        tuple_data = self.chain.get_delegator_core_stake_state_on_chain(delegator, delegatee)
        stake_amount_on_chain = tuple_data[0]

        assert_result(
            f"{addr_to_name(delegator)}_{addr_to_name(delegatee)}_stake_amount",
            stake_amount,
            stake_amount_on_chain
        )

    def check_candidate_core_realtime_amount(self, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        candidate_stake_state = candidate.get_stake_state()
        core_asset_name = self.chain.get_core_asset().get_name()
        realtime_amount = candidate_stake_state.get_realtime_amount(core_asset_name)

        tuple_data = self.chain.get_candidate_core_stake_state_on_chain(delegatee)
        realtime_amount_on_chain = tuple_data[1]

        assert_result("realtime_amount", realtime_amount, realtime_amount_on_chain)

    def check_candidate_core_stake_amount(self, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        core_asset_name = self.chain.get_core_asset().get_name()
        amount = candidate.get_stake_state().get_stake_amount(core_asset_name)

        tuple_data = self.chain.get_candidate_core_stake_state_on_chain(delegatee)
        amount_on_chain = tuple_data[0]

        assert_result("amount", amount, amount_on_chain)

    def check_candidate_btc_stake_amount(self, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        assert candidate.can_delegate()

        btc_asset_name = self.chain.get_btc_asset().get_name()
        amount = candidate.get_stake_state().get_stake_amount(btc_asset_name)
        amount_on_chain = self.chain.get_btc_stake_amount_on_chain(delegatee)

        assert_result(f"{addr_to_name(delegatee)}_btc_stake_amount", amount, amount_on_chain)

    def check_btc_lst_total_stake_amount(self):
        amount = self.chain.get_delegator_stake_state().get_btc_lst_total_stake_amount()
        amount_on_chain = self.chain.get_btc_lst_total_stake_amount_on_chain()

        assert_result("amount", amount, amount_on_chain)

    def check_delegator_core_change_round(self, delegator, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        candidate_stake_state = candidate.get_stake_state()
        core_asset_name = self.chain.get_core_asset().get_name()
        change_round = candidate_stake_state.get_delegator_change_round(core_asset_name, delegator)

        tuple_data = self.chain.get_delegator_core_stake_state_on_chain(delegator, delegatee)
        change_round_on_chain = tuple_data[3]

        assert_result(
            f"{addr_to_name(delegator)}_{addr_to_name(delegatee)}_change_round",
            change_round,
            change_round_on_chain
        )

    def check_delegator_core_transferred_amount(self, delegator, delegatee):
        candidate = self.chain.get_candidate(delegatee)
        candidate_stake_state = candidate.get_stake_state()
        core_asset_name = self.chain.get_core_asset().get_name()
        transferred_amount = candidate_stake_state.get_delegator_transferred_amount(core_asset_name, delegator)

        tuple_data = self.chain.get_delegator_core_stake_state_on_chain(delegator, delegatee)
        transferred_amount_on_chain = tuple_data[2]

        assert_result(
            f"{addr_to_name(delegator)}_{addr_to_name(delegatee)}_transferred_amount",
            transferred_amount,
            transferred_amount_on_chain
        )

    def check_delegator_core_total_amount(self, delegator):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        total_amount = delegator_stake_state.get_core_amount(delegator)
        total_amount_on_chain = self.chain.get_core_stake_total_amount_on_chain(delegator)

        assert_result("total_amount", total_amount, total_amount_on_chain)

    def check_delegator_core_stake_nodes(self, delegator):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        nodes = delegator_stake_state.get_core_stake_candidates(delegator)
        nodes_on_chain = self.chain.get_core_stake_candidates_on_chain(delegator)

        if len(nodes) != len(nodes_on_chain):
            assert False, f"{addr_to_name(delegator)}_stake_nodes off_chain={nodes.keys()}, on_chain={nodes_on_chain}"

        assert_result(f"{addr_to_name(delegator)}_stake_nodes", list(nodes.keys()), list(nodes_on_chain))
        # for node in nodes_on_chain:
        #     if nodes.get(node) is None:
        #         assert False, f"{addr_to_name(delegator)}_stake_nodes {addr_to_name(node)} does not exist"

    def check_core_history_reward(self, delegator):
        reward = self.chain.get_delegator_stake_state().get_core_history_reward(delegator)
        reward_on_chain = self.chain.get_core_history_reward_on_chain(delegator)

        assert_result(addr_to_name(delegator) + "_core_history_reward", reward, reward_on_chain)

    def check_btc_lst_history_reward(self, delegator):
        reward = self.chain.get_delegator_stake_state().get_btc_lst_history_reward(delegator)
        reward_on_chain = self.chain.get_btc_lst_history_reward_on_chain(delegator)

        assert_result(addr_to_name(delegator) + "_btc_lst_history_reward", reward, reward_on_chain)

    def check_btc_stake_history_reward(self, delegator):
        claimable_reward = self.chain.get_delegator_stake_state().get_btc_stake_history_reward(delegator)
        unclaimable_reward = self.chain.get_delegator_stake_state().get_btc_stake_history_unclaimable_reward(delegator)

        reward_on_chain = self.chain.get_btc_stake_history_reward_on_chain(delegator)
        claimable_reward_on_chain = reward_on_chain[0]
        unclaimable_reward_on_chain = reward_on_chain[1]

        assert_result(addr_to_name(delegator) + "_btc_stake_claimable_reward", claimable_reward,
                      claimable_reward_on_chain)
        assert_result(addr_to_name(delegator) + "_btc_stake_unclaimable_reward", unclaimable_reward,
                      unclaimable_reward_on_chain)

    def check_power_history_reward(self, delegator):
        reward = self.chain.get_delegator_stake_state().get_power_history_reward(delegator)
        reward_on_chain = self.chain.get_power_history_reward_on_chain(delegator)

        assert_result(addr_to_name(delegator) + "_power_history_reward", reward, reward_on_chain)

    def check_history_reward(self, delegator):
        self.check_core_history_reward(delegator)
        self.check_btc_lst_history_reward(delegator)
        self.check_power_history_reward(delegator)
        self.check_btc_stake_history_reward(delegator)

    def check_btc_lst_stake_tx(self, txid):
        tuple_data = self.chain.get_btc_lst_stake_tx_on_chain(txid)

        amount_on_chain = tuple_data[0]
        output_index_on_chain = tuple_data[1]

        tx = self.chain.get_btc_lst_stake_tx(txid)
        amount = tx.get_amount()
        output_index = tx.get_lock_output_index()

        assert_result("amount", amount, amount_on_chain)
        assert_result("output_index", output_index, output_index_on_chain)

    def check_btc_lst_redeem_proof_tx(self, txid):
        tuple_data = self.chain.get_btc_lst_stake_tx_on_chain(txid)

        amount_on_chain = tuple_data[0]
        output_index_on_chain = tuple_data[1]

        redeem_proof_tx = \
            self.chain.get_delegator_stake_state().get_redeem_proof_tx(txid)
        amount = redeem_proof_tx.get_amount()
        output_index = redeem_proof_tx.get_index()

        assert_result("amount", amount, amount_on_chain)
        assert_result("output_index", output_index, output_index_on_chain)

    def check_btc_lst_redeem_requests(self):
        redeem_requests = \
            self.chain.get_delegator_stake_state().get_redeem_requests()

        for key, request in redeem_requests.items():
            tuple_data = self.chain.get_redeem_request_on_chain(key)
            request_on_chain = RedeemRequest(tuple_data[0], tuple_data[1], tuple_data[2])
            assert_result("reddem_request", request, request_on_chain)

    def check_btc_lst_total_realtime_amount(self):
        realtime_amount = \
            self.chain.get_delegator_stake_state().get_btc_lst_total_realtime_amount()
        realtime_amount_on_chain = self.chain.get_btc_lst_total_realtime_amount_on_chain()

        assert_result("realtime_amount", realtime_amount, realtime_amount_on_chain)

    def check_delegator_btc_lst_change_round(self, delegator):
        tuple_data = self.chain.get_btc_lst_stake_info_on_chain(delegator)
        change_round_on_chain = tuple_data[0]

        change_round = \
            self.chain.get_delegator_stake_state().get_btc_lst_change_round(delegator)

        assert_result("change_round", change_round, change_round_on_chain)

    def check_delegator_btc_lst_history_reward(self, delegator):
        history_reward = self.chain.get_delegator_stake_state().get_btc_lst_history_reward(delegator)
        history_reward_on_chain = self.chain.get_btc_lst_history_reward_on_chain(delegator)

        assert_result(f"{addr_to_name(delegator)}_history_reward", history_reward, history_reward_on_chain)

    def check_delegator_btc_lst_realtime_amount(self, delegator):
        tuple_data = self.chain.get_btc_lst_stake_info_on_chain(delegator)
        realtime_amount_on_chain = tuple_data[1]

        realtime_amount = \
            self.chain.get_delegator_stake_state().get_btc_lst_realtime_amount(delegator)

        assert_result("realtime_amount", realtime_amount, realtime_amount_on_chain)

    def check_delegator_btc_lst_stake_amount(self, delegator):
        tuple_data = self.chain.get_btc_lst_stake_info_on_chain(delegator)
        stake_amount_on_chain = tuple_data[2]

        stake_amount = \
            self.chain.get_delegator_stake_state().get_btc_lst_stake_amount(delegator)

        assert_result("stake_amount", stake_amount, stake_amount_on_chain)

    def check_btc_stake_tx(self, txid, log=False):
        tuple_data = self.chain.get_btc_stake_tx_on_chain(txid)

        amount_on_chain = tuple_data[0]
        output_index_on_chain = tuple_data[1]
        block_time_on_chain = tuple_data[2]
        lock_time_on_chain = tuple_data[3]

        tx = self.chain.get_btc_stake_tx(txid)
        amount = tx.get_amount()
        output_index = tx.get_lock_output_index()
        block_time = tx.get_block_time()
        lock_time = tx.get_lock_time()

        assert_result("amount", amount, amount_on_chain)
        assert_result("output_index", output_index, output_index_on_chain)
        assert_result("block_time", block_time, block_time_on_chain)
        assert_result("lock_time", lock_time, lock_time_on_chain)

    def check_btc_stake_receipt(self, txid, log=False):
        tuple_data = self.chain.get_btc_stake_tx_receipt_on_chain(txid)

        delegatee_on_chain = tuple_data[0]
        delegator_on_chain = tuple_data[1]
        round_on_chain = tuple_data[2]

        tx = self.chain.get_btc_stake_tx(txid)
        delegatee = tx.get_delegatee()
        delegator = tx.get_delegator()
        round = tx.get_round()

        assert_result("tx_delegatee", addr_to_name(delegatee), addr_to_name(delegatee_on_chain))
        assert_result("tx_delegator", addr_to_name(delegator), addr_to_name(delegator_on_chain))
        assert_result("tx_round", round, round_on_chain)

    def check_btc_stake_realtime_amount(self, delegatee):
        realtime_amount = self.chain.get_btc_stake_realtime_amount(delegatee)
        realtime_amount_on_chain = self.chain.get_btc_stake_realtime_amount_on_chain(delegatee)

        assert_result(f"{addr_to_name(delegatee)}_realtime_amount", realtime_amount, realtime_amount_on_chain)

    def check_delegator_btc_realtime_amount(self, delegator):
        # cannot check, delegatorMap on chain is private
        return True

    def check_creditor_contributions(self, delegator):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        debts = delegator_stake_state.get_debts(delegator)
        if debts is None:
            return True

        creditors = {}
        for debt in debts:
            creditor = debt[0]
            creditors[creditor] = 1

        if len(creditors) == 0:
            return True

        for creditor in creditors:
            amount = delegator_stake_state.get_relayer_reward(creditor)
            amount_on_chain = self.chain.get_contribution_on_chain(creditor)

            assert_result("amount", amount, amount_on_chain)

    def check_total_unclaimed_reward(self):
        unclaim_reward = self.chain.get_total_unclaimed_reward()
        unclaim_reward_on_chain = self.chain.get_total_unclaimed_reward_on_chain()

        print(f"total_unclaimed_reward off_chain={unclaim_reward}, on_chain={unclaim_reward_on_chain}")

        assert_result("total_unclaim_reward", unclaim_reward, unclaim_reward_on_chain)

    def check_wallet(self, payment):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        wallet_off_chain = delegator_stake_state.get_wallet(payment)

        wallets = self.chain.get_wallets_on_chain()
        for data in wallets:
            wallet_on_chain = BtcLSTLockWallet()
            wallet_on_chain.from_on_chain_data(data)

            if wallet_off_chain == wallet_on_chain:
                return

        assert_result("wallet", wallet_off_chain, wallets)

    def check_round_powers(self, power_round, delegatee):
        amounts, total_amount = self.chain.get_round_powers_on_chain(power_round, delegatee)
        amount_on_chain = total_amount

        candidate = self.chain.get_candidate(delegatee)
        amount = candidate.get_stake_state().get_round_powers(power_round)

        assert_result(addr_to_name(delegatee) + f"_{power_round}_power", amount, amount_on_chain)

    def check_core_stake_grade_flag(self):
        grade_flag, grades = self.chain.get_delegator_stake_state().get_core_stake_grade_data()
        grade_flag_on_chain = self.chain.get_core_stake_grade_flag_on_chain()

        assert_result("core_stake_grade_flag", grade_flag, grade_flag_on_chain)

    def check_core_stake_grades(self):
        grade_flag, grades = self.chain.get_delegator_stake_state().get_core_stake_grade_data()
        grades_on_chain = self.chain.get_core_stake_grades_on_chain()

        assert_result("core_stake_grades", grades, grades_on_chain)

    def check_btc_stake_grade_flag(self):
        grade_flag, grades = self.chain.get_delegator_stake_state().get_btc_stake_grade_data()
        grade_flag_on_chain = self.chain.get_btc_stake_grade_flag_on_chain()

        assert_result("btc_stake_grade_flag", grade_flag, grade_flag_on_chain)

    def check_btc_stake_grades(self):
        grade_flag, grades = self.chain.get_delegator_stake_state().get_btc_stake_grade_data()
        grades_on_chain = self.chain.get_btc_stake_grades_on_chain()

        assert_result("btc_stake_grades", grades, grades_on_chain)

    def check_btc_lst_stake_grade_flag(self):
        grade_flag, grade_percent = self.chain.get_delegator_stake_state().get_btc_lst_stake_grade_data()
        grade_flag_on_chain = self.chain.get_btc_lst_stake_grade_flag_on_chain()

        assert_result("btc_lst_stake_grade_flag", grade_flag, grade_flag_on_chain)

    def check_btc_lst_stake_grade_percent(self):
        grade_flag, grade_percent = self.chain.get_delegator_stake_state().get_btc_lst_stake_grade_data()
        grade_percent_on_chain = self.chain.get_btc_lst_stake_grade_percent_on_chain()

        assert_result("btc_lst_stake_grade_percent", grade_percent, grade_percent_on_chain)
