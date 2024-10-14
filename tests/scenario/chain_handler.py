from brownie import *
from itertools import islice
from . import chain_state
from . import constants
from .payment import BtcLSTLockWallet
from .account_mgr import AccountMgr

addr_to_name = AccountMgr.addr_to_name


def partion(items, count, key):
    assert isinstance(items, list)

    if len(items) <= count:
        return items

    # for item in items:
    #     print(f"validator_off_chain before sorted {addr_to_name(item.get_operator_addr())} item={item}")

    count = min(len(items), count)
    partion_range(items, 0, len(items) - 1, count, key)

    # # for debug
    # for item in items:
    #     print(f"validator_off_chain {addr_to_name(item.get_operator_addr())} item={item}")

    # availableCandidates = CandidateHubMock[0].getAvailableCandidates()
    # for candidate in availableCandidates:
    #     print(f"AC_on_chain {addr_to_name(candidate[0])} {candidate} ")

    # validators = ValidatorSetMock[0].getValidatorOps()
    # for validator in validators:
    #     print(f"validator_on_chain {addr_to_name(validator)} {validator}")

    return items[:count]


def partion_range(items, left, right, count, key):
    assert left <= right, f"Invalid range=[{left, {right} }]"

    # print(f"partion_range left={left}, right={right}, count={count}")
    # for item in items:
    #     print(f"before {addr_to_name(item.get_operator_addr())} item={item}")

    if count == 0 or right - left + 1 <= count:
        return

    l = left
    r = right

    pivot = left
    pivot_item = items[pivot]
    value = key(pivot_item)

    while left < right:
        while left < right:
            if key(items[right]) < value:
                right -= 1
            else:
                items[left] = items[right]
                left += 1
                break

        while left < right:
            if key(items[left]) >= value:
                left += 1
            else:
                items[right] = items[left]
                right -= 1
                break

    items[left] = pivot_item
    left_count = left - l + 1

    if left_count == count:
        return

    if left_count > count:
        partion_range(items, l, left - 1, count, key)
    elif left_count < count:
        partion_range(items, left + 1, r, count - left_count, key)


class ChainHandler:
    def __init__(self, chain) -> None:
        self.chain = chain

    ################## turn round #######################
    def turn_round(self):
        self.distribute_reward()
        self.chain.incr_round()
        self.update_validator_set()
        self.clean_slash_indicator()
        self.update_candidates_status()

    def distribute_reward(self):
        remain_reward = 0

        incentive_percent = self.chain.get_incentive_percent()
        validators = self.chain.get_validators()
        for validator in validators.values():
            if validator.get_income() == 0:
                continue

            # distribute to systemreward contract
            incentive_amount = validator.get_incentive_amount(incentive_percent)
            validator.add_income(-incentive_amount)
            assert validator.get_income() > 0

            self.chain.add_total_income(-incentive_amount)

            self.chain.add_balance(ValidatorSetMock[0], -incentive_amount)
            self.chain.pay_to_system_reward(incentive_amount)

            # distribute to validator fee addr
            commission_amount = validator.get_commission_amount()
            validator.add_income(-commission_amount)

            self.chain.add_total_income(-commission_amount)
            self.chain.add_balance(ValidatorSetMock[0], -commission_amount)
            self.chain.add_balance(validator.get_fee_addr(), commission_amount)

            remain_reward += validator.get_income()

        # distribute it to the stake hub
        self.chain.add_balance(ValidatorSetMock[0], -remain_reward)
        self.distribute_reward_to_stake_hub(remain_reward)

    def distribute_reward_to_stake_hub(self, remain_reward):
        # total_income = self.chain.get_total_income()
        # assert remain_reward == total_income, \
        #     f"remain_reward={remain_reward}, remain total_income={total_income}"
        # print(f"distribute_reward_to_stake_hub {remain_reward}")

        burn_amount = 0
        assets = self.chain.get_assets()
        validators = self.chain.get_validators()
        round = self.chain.get_round()
        for asset in assets:
            for validator in validators.values():
                total_score = validator.get_stake_state().get_total_score()
                asset_score = validator.get_stake_state().get_score(asset.get_name())

                income = validator.get_income()
                if income == 0:
                    continue

                if total_score == 0:
                    if income > 0:
                        burn_amount += income
                        validator.add_income(-income)
                        self.chain.add_total_income(-income)
                    asset_reward = 0
                else:
                    asset_reward = income * asset_score // total_score

                # set reward for each asset
                validator.get_stake_state().set_reward(asset.get_name(), asset_reward)
                self.chain.add_total_income(-asset_reward)

            # # update asset subsidy
            # asset_bonus = self.chain.get_total_unclaimed_reward() * asset.get_bonus_rate() // constants.PERCENT_DECIMALS
            # self.chain.add_total_unclaimed_reward(-asset_bonus)
            # asset.add_bonus_amount(asset_bonus) # bonus amount used in claimreward

            # distribute asset reward
            asset.distribute_reward(validators, self.chain.get_delegator_stake_state(), round)

        # check income of each validator and total_income is 0
        for validator in validators.values():
            validator.update_income(0)

        if self.chain.get_total_income() > 0:
            print(f"total income != 0, dust is {self.chain.get_total_income()}")
            self.chain.update_total_income(0)

        self.chain.add_balance(StakeHubMock[0], remain_reward - burn_amount)
        self.chain.pay_to_system_reward(burn_amount)

    def update_validator_set(self):
        validators = self.select_validators_for_next_round()
        assert len(validators) > 0

        # sync stake amount
        assets = self.chain.get_assets()
        for validator in validators.values():
            validator.update_commission_in_use()

            stake_state = validator.get_stake_state()
            for asset in assets:
                stake_state.sync_stake_amount(asset.get_name())
                name = asset.get_name()

        self.chain.get_delegator_stake_state().sync_btc_lst_total_stake_amount()
        self.chain.set_validators(validators)

    def clean_up(self):
        round = self.chain.get_round()
        btc_asset_name = self.chain.get_btc_asset().get_name()
        txs = self.chain.get_delegator_stake_state().get_btc_stake_txs()

        for tx in txs.values():
            if tx.is_removed():
                continue

            lock_time = tx.get_lock_time()
            unlock_round = lock_time // constants.ROUND_SECONDS
            if unlock_round <= round:
                candidate = self.chain.get_candidate(tx.get_delegatee())
                candidate.get_stake_state().add_realtime_amount(btc_asset_name, -tx.get_amount())
                tx.remove()

    def select_validators_for_next_round(self):
        assets = self.chain.get_assets()
        core_asset = self.chain.get_core_asset()
        available_candidates = self.chain.get_available_candidates()

        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_stake_state.init_lst_validator_count(available_candidates)

        # clear expired data
        self.clean_up()

        for asset in assets:
            # calculate the total staked amount of the current asset
            total_amount = 0
            for candidate in available_candidates.values():
                amount_list = asset.calc_candidate_stake_amount_list(candidate, delegator_stake_state,
                                                                     self.chain.get_round())
                candidate.get_stake_state().init_round_stake_amount_list(asset.get_name(), amount_list)
                total_amount += sum(amount_list)

            # update the total aoount of the asset
            asset.set_total_amount(total_amount)

            # update the factor of the asset
            asset.update_factor(core_asset)
            print(f"update_candidates_score:{asset.get_name()}:{total_amount}, {asset.get_factor()}")

            # update the asset score for each candidate
            for candidate in available_candidates.values():
                candidate.get_stake_state().update_score(asset.get_name(), asset.get_factor())

        # clear tmp data, used to calc btc lst avg amounts
        delegator_stake_state.unset_lst_validator_count()

        # update the total asset score for each candidate
        for candidate in available_candidates.values():
            candidate.get_stake_state().update_total_score()

        validators = partion(
            list(available_candidates.values()),
            self.chain.get_validator_count(),
            key=lambda item: item.get_total_score()
        )

        validator_dict = {}
        for validator in validators:
            validator_dict[validator.get_operator_addr()] = validator

        return validator_dict

    def clean_slash_indicator(self):
        reduce_count = self.chain.get_felony_threshold() // 4

        candidates = self.chain.get_candidates()
        for candidate in candidates.values():
            slash_count = candidate.get_slash_count()
            if slash_count > reduce_count:
                candidate.update_slash_count(slash_count - reduce_count)
            else:
                candidate.reset_slash_count()
                candidate.reset_latest_slash_block()

    def update_candidates_status(self):
        round = self.chain.get_round()
        candidates = self.chain.get_candidates()
        validators = self.chain.get_validators()
        for candidate in candidates.values():
            if validators.get(candidate.get_operator_addr()) is None:
                candidate.unset_vldt()
            else:
                candidate.set_vldt()

            if candidate.is_freedom(round):
                candidate.unset_jail()

    ################## end turn round ########################

    ######################## slash ########################
    def slash_validator(self, operator_addr, block_number):
        validator = self.chain.get_validator(operator_addr)
        if validator is None:
            return

        if not validator.is_validator():
            return

        validator.incr_slash_count(block_number)
        if self.chain.can_be_felony(validator):
            validator.reset_slash_count()
            self.felony_validator(validator)
        elif self.chain.can_be_misdemeanor(validator):
            self.misdemeanor_validator(validator)

    def felony_validator(self, validator):
        if self.deduct_income_and_kick_out(validator, True):
            self.jail_validator(validator)

    def misdemeanor_validator(self, validator):
        self.deduct_income_and_kick_out(validator)

    def deduct_income_and_kick_out(self, validator, is_kick_out=False):
        validators = self.chain.get_validators()
        validator_count = len(validators)
        assert validator_count > 0

        operator_addr = validator.get_operator_addr()
        assert validators.get(operator_addr) is not None
        income = validator.get_income()
        validator.update_income(0)
        if validator_count == 1:
            return False

        # kick out from validator list
        if is_kick_out:
            validators.pop(operator_addr)

        # redistribute income
        avg_amount = income // (validator_count - 1)
        if avg_amount == 0:
            return True

        print(f"dnjsdjs avg amount={avg_amount}")
        for validator in validators.values():
            if is_kick_out or validator.get_operator_addr() != operator_addr:
                validator.add_income(avg_amount)

        return True

    def jail_validator(self, validator):
        candidate = self.chain.get_candidate(validator.get_operator_addr())
        assert candidate is not None
        # deduct slash amount
        margin = validator.get_margin_amount()
        slash_amount = self.chain.get_felony_slash_amount()
        min_remain_amount = self.chain.get_candidate_dues()
        if margin < slash_amount + min_remain_amount:
            slash_amount = margin

        if slash_amount > 0:
            validator.add_margin_amount(-slash_amount)
            self.chain.add_balance(CandidateHubMock[0], -slash_amount)
            self.chain.add_balance(SystemRewardMock[0], slash_amount)

        # update candidate status
        remain_amount = margin - slash_amount
        if remain_amount > 0:
            validator.set_jail(self.chain.get_round(), self.chain.get_felony_round())
            if remain_amount < self.chain.get_candidate_required_margin():
                validator.set_margin()
        else:
            self.chain.remove_candidate(validator.get_operator_addr())

    ###################### end slash ######################
    def add_candidate(self, operator_addr, consensus_addr, fee_addr, commission, margin):
        candidates = self.chain.get_candidates()
        validators = self.chain.get_validators()
        round = self.chain.get_round()

        assert validators.get(operator_addr) is None

        candidate_data = [
            operator_addr,
            consensus_addr,
            fee_addr,
            commission,
            margin,
            chain_state.NodeStatus.CANDIDATE.value,
            round,
            commission
        ]

        candidate = chain_state.Candidate(candidate_data)
        old_candidate = candidates.get(operator_addr)
        if old_candidate is not None:
            assert old_candidate.is_removed()
            candidate.set_stake_state(old_candidate.get_stake_state())
            candidate.set_slash_count(old_candidate.get_slash_count())
            candidate.set_latest_slash_block(old_candidate.get_latest_slash_block())

        self.chain.add_candidate(candidate)
        self.chain.add_balance(CandidateHubMock[0], margin)
        self.chain.add_balance(operator_addr, -margin)

    def remove_candidate(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        margin = candidate.get_margin_amount()
        dues = self.chain.get_candidate_dues()

        deduct_amount = min(margin, dues)
        refund_amount = margin - deduct_amount

        self.chain.add_balance(SystemRewardMock[0], deduct_amount)
        self.chain.add_balance(operator_addr, refund_amount)
        self.chain.add_balance(CandidateHubMock[0], -margin)

        self.chain.remove_candidate(operator_addr)

    def add_margin(self, operator_addr, amount):
        self.chain.add_balance(operator_addr, -amount)
        self.chain.add_balance(CandidateHubMock[0], amount)

        candidate = self.chain.get_candidate(operator_addr)
        candidate.add_margin_amount(amount)

        if candidate.get_margin_amount() >= \
                self.chain.get_candidate_required_margin():
            candidate.unset_margin()

    def refuse_delegate(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        candidate.disable_delegate()

    def accept_delegate(self, operator_addr):
        candidate = self.chain.get_candidate(operator_addr)
        candidate.enable_delegate()

    def deposit_block_reward(self, miner, tx_fee, block_number):
        self.chain.update_block_reward(block_number)

        full_reward = tx_fee + self.chain.get_block_reward()

        balance = self.chain.get_balance(ValidatorSetMock[0])
        if balance - self.chain.get_total_income() < full_reward:
            real_reward = tx_fee
            assert False, f"Why can't the full reward be received"
        else:
            real_reward = full_reward

        assert real_reward > 0

        # update validator set balance
        self.chain.add_balance(ValidatorSetMock[0], tx_fee)

        # update validatorset total income
        self.chain.add_total_income(real_reward)

        # update validator income
        validator = self.chain.get_candidate_by_consensus_addr(miner)
        assert validator is not None
        validator.add_income(real_reward)

    def claim_reward(self, delegator):
        total_claimable_reward = 0
        total_unclaimable_reward = 0

        round = self.chain.get_round()
        delegator_stake_state = self.chain.get_delegator_stake_state()
        candidates = self.chain.get_candidates()
        assets = self.chain.get_assets()
        core_accured_stake_amount = 0
        for asset in assets:
            claimable_reward, unclaimable_reward, accured_stake_amount = asset.claim_reward(
                round,
                delegator,
                delegator_stake_state,
                candidates,
                core_accured_stake_amount
            )

            if asset == assets[0]:
                core_accured_stake_amount = accured_stake_amount

            print(f"claim {asset.get_name()} reward, claimable={claimable_reward}, unclaimable={unclaimable_reward}")
            total_claimable_reward += claimable_reward
            total_unclaimable_reward += unclaimable_reward

        print(f"total_claimable={total_claimable_reward},total_unclaimable={total_unclaimable_reward}")

        total_claimable_reward, total_payment = \
            self.pay_delegator_debts(delegator, total_claimable_reward, delegator_stake_state)
        print(f"    pay debts={total_payment}, remain claimable={total_claimable_reward}")

        total_float_reward = self.check_float_reward_pool(total_unclaimable_reward)
        self.chain.add_total_unclaimed_reward(-total_float_reward)
        print(f"final total_unclaimed_reward = {self.chain.get_total_unclaimed_reward()}")

        self.chain.add_balance(delegator, total_claimable_reward)
        self.chain.add_balance(StakeHubMock[0], -total_claimable_reward)
        # ## for debug
        # arr, arr2 = StakeHubMock[0].getDataArr()
        # print(f"STAKEHUB Debug on chain: {arr}, {arr2}")

        # arr, arr2, arr3 = BitcoinAgentMock[0].getDataArr()
        # print(f"BITCOINAGENT Debug: {arr}, {arr2}, {arr3}")

        # arr = BitcoinStakeMock[0].getDataArr()
        # print(f"BITCOINSTAKE MOCK:{arr}")

        # delegator1 = BitcoinStakeMock[0].curDelegator();
        # delegator2 = BitcoinStakeMock[0].curDelegator2();
        # print(f"Delegator1={delegator1}, Delegator2={delegator2}")

        # curFloadRewards = StakeHubMock[0].getCurFloadRewards()
        # print(f"dnjsdjks {curFloadRewards}")

    def check_float_reward_pool(self, total_unclaimable_reward):
        float_reward_pool = self.chain.get_total_unclaimed_reward()
        total_float_reward = -total_unclaimable_reward
        if total_float_reward > float_reward_pool:
            supplementary_amount = total_float_reward * 10
            actual_supplementary_amount = \
                self.chain.claim_system_reward(StakeHubMock[0], supplementary_amount)

            # maybe actual_supplementary_amount < supplementary_amount
            self.chain.add_total_unclaimed_reward(actual_supplementary_amount)

            print(
                f"supplementary_amount={supplementary_amount}, actual_supplementary_amount={actual_supplementary_amount}, total_unclaimed_reward={self.chain.get_total_unclaimed_reward()}")

        return total_float_reward

    def pay_delegator_debts(self, delegator, reward, delegator_stake_state):
        if reward == 0:
            return 0, 0

        debts = delegator_stake_state.get_debts(delegator)
        if debts is None:
            return reward, 0

        total_payment = 0
        for debt in reversed(debts):
            relayer = debt[0]
            amount = debt[1]

            pay_amount = min(reward, amount)
            reward -= pay_amount
            total_payment += pay_amount

            debts.pop()
            if amount > pay_amount:
                debts.append((relayer, amount - pay_amount))

            delegator_stake_state.add_relayer_reward(relayer, pay_amount)

            if reward == 0:
                break

        return reward, total_payment

    def delegate_core(self, delegator, delegatee, amount, is_transfer=False):
        candidate = self.chain.get_candidate(delegatee)
        assert candidate.can_delegate()

        round = self.chain.get_round()
        core_asset = self.chain.get_core_asset()
        asset_name = core_asset.get_name()
        candidate_stake_state = candidate.get_stake_state()
        delegator_stake_state = self.chain.get_delegator_stake_state()

        change_round = candidate_stake_state.get_delegator_change_round(asset_name, delegator)
        if change_round == 0:
            candidate_stake_state.update_delegator_change_round(asset_name, delegator, round)
            delegator_stake_state.add_core_stake_candidate(delegator, delegatee)
            change_round = round

        # collect reward
        if change_round < round:
            reward, accured_stake_amount = core_asset.collect_reward_in_candidate(round, delegator, candidate)
            if reward > 0:
                delegator_stake_state.add_core_history_reward(delegator, reward)

            if accured_stake_amount > 0:
                delegator_stake_state.add_core_history_accured_stake_amount(delegator, accured_stake_amount)

        # update candidate's total realtime amount
        candidate_stake_state.add_realtime_amount(asset_name, amount)

        # update the delegator's realtime amount at the current candidate
        candidate_stake_state.add_delegator_realtime_amount(asset_name, delegator, amount)

        if not is_transfer:
            # update delegator's total staked amount in all candidates
            delegator_stake_state.add_core_amount(delegator, amount)

        # update balance
        self.chain.add_balance(delegator, -amount)
        self.chain.add_balance(CoreAgentMock[0], amount)

    def undelegate_core(self, delegator, delegatee, amount, is_transfer=False):
        candidate = self.chain.get_candidate(delegatee)
        # assert candidate.can_delegate()

        round = self.chain.get_round()
        core_asset = self.chain.get_core_asset()
        asset_name = core_asset.get_name()
        candidate_stake_state = candidate.get_stake_state()
        delegator_stake_state = self.chain.get_delegator_stake_state()

        change_round = candidate_stake_state.get_delegator_change_round(asset_name, delegator)

        # collect reward
        if change_round < round:
            reward, accured_stake_amount = core_asset.collect_reward_in_candidate(round, delegator, candidate)
            if reward > 0:
                delegator_stake_state.add_core_history_reward(delegator, reward)

            if accured_stake_amount > 0:
                delegator_stake_state.add_core_history_accured_stake_amount(delegator, accured_stake_amount)

        stake_amount = candidate_stake_state.get_delegator_stake_amount(asset_name, delegator)
        realtime_amount = candidate_stake_state.get_delegator_realtime_amount(asset_name, delegator)
        assert realtime_amount >= amount

        # update candidate's total realtime amount
        candidate_stake_state.add_realtime_amount(asset_name, -amount)  # candidate total realtime anount

        if is_transfer:
            # update delegator's transferred amount in this candidate
            candidate_stake_state.add_delegator_transferred_amount(asset_name, delegator, min(amount, stake_amount))
        else:
            # update delegator's total staked amount in all candidate
            delegator_stake_state.add_core_amount(delegator, -amount)  # delegator total amount

        # update delegator's stake amount and realtime amount in this candidate
        candidate_stake_state.add_delegator_stake_amount(asset_name, delegator,
                                                         -min(amount, stake_amount))  # delegator stake amount
        candidate_stake_state.add_delegator_realtime_amount(asset_name, delegator, -amount)  # delegator realtime amount

        # if the delegator's realtime amount and transfferd amount at the current candidate is 0, remove the related information.
        realtime_amount = candidate_stake_state.get_delegator_realtime_amount(asset_name, delegator)
        transferred_amount = candidate_stake_state.get_delegator_transferred_amount(asset_name, delegator)
        if realtime_amount == 0 and transferred_amount == 0:
            delegator_stake_state.rm_core_stake_candidate(delegator, delegatee)
            candidate_stake_state.update_delegator_change_round(asset_name, delegator, 0)

        # update balance
        self.chain.add_balance(delegator, amount)
        self.chain.add_balance(CoreAgentMock[0], -amount)

        self._deduct_transferred_amount_from_staked_candidates(delegator, amount - min(amount, stake_amount))

    def _deduct_transferred_amount_from_staked_candidates(self, delegator, amount):
        if amount <= 0:
            return

        delegator_stake_state = self.chain.get_delegator_stake_state()
        staked_candidates = delegator_stake_state.get_core_stake_candidates(delegator)
        if staked_candidates is None or len(staked_candidates) == 0:
            return

        core_asset = self.chain.get_core_asset()
        asset_name = core_asset.get_name()

        for delegatee in reversed(list(staked_candidates.keys())):
            candidate = self.chain.get_candidate(delegatee)
            candidate_stake_state = candidate.get_stake_state()
            transferred_amount = candidate_stake_state. \
                get_delegator_transferred_amount(asset_name, delegator)

            if transferred_amount == 0:
                continue

            if transferred_amount < amount:
                candidate_stake_state.update_delegator_transferred_amount(asset_name, delegator, 0)
                amount -= transferred_amount

                realtime_amount = candidate_stake_state.get_delegator_realtime_amount(asset_name, delegator)
                if realtime_amount == 0:
                    delegator_stake_state.rm_core_stake_candidate(delegator, delegatee)
                    candidate_stake_state.update_delegator_change_round(asset_name, delegator, 0)
            else:
                candidate_stake_state.add_delegator_transferred_amount(asset_name, delegator, -amount)
                break

    def transfer_core(self, delegator, from_delegatee, to_delegatee, amount):
        self.undelegate_core(delegator, from_delegatee, amount, True)
        self.delegate_core(delegator, to_delegatee, amount, True)

    def delegate_btc(self, tx):
        # add bitcoin tx and delegator debts
        tx.set_round(self.chain.get_round())
        self.chain.get_delegator_stake_state().add_btc_stake_tx(tx)

        # update realtime amount
        delegatee = tx.get_delegatee()
        candidate = self.chain.get_candidate(delegatee)
        stake_state = candidate.get_stake_state()

        btc_asset_name = self.chain.get_btc_asset().get_name()
        amount = tx.get_amount()
        stake_state.add_realtime_amount(btc_asset_name, amount)

    def transfer_btc(self, delegator, txid, to_delegatee):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        tx = delegator_stake_state.get_btc_stake_tx(txid)
        assert tx is not None
        assert delegator == tx.get_delegator()

        round = self.chain.get_round()
        lock_time = tx.get_lock_time()
        unlock_round = lock_time // constants.ROUND_SECONDS
        assert unlock_round - round >= 2

        btc_asset = self.chain.get_btc_asset()
        claimable_reward, unclaimable_reward, accured_stake_amount, expired = btc_asset.collect_btc_stake_tx_reward(tx,
                                                                                                                    delegator_stake_state,
                                                                                                                    round)
        if claimable_reward > 0:
            delegator_stake_state.add_btc_stake_history_reward(delegator, claimable_reward)

        if unclaimable_reward > 0:
            delegator_stake_state.add_btc_stake_history_unclaimable_reward(delegator, unclaimable_reward)

        if accured_stake_amount > 0:
            delegator_stake_state.add_btc_stake_history_accured_stake_amount(delegator, accured_stake_amount)

        # if expired:
        #     delegator_stake_state.remove_delegator_txid(delegator, txid)

        # update from_candidate's total realtime amount
        amount = tx.get_amount()
        from_delegatee = tx.get_delegatee()
        from_candidate = self.chain.get_candidate(from_delegatee)
        from_candidate.get_stake_state().add_realtime_amount(btc_asset.get_name(), -amount)

        # it's unnecessary to maintain expired staking information off-chain
        # since round2expireInfoMap is private data, on-chain and off-chain data comparison is not feasible

        # update to_candidate's total realtime amount
        to_candidate = self.chain.get_candidate(to_delegatee)
        assert to_candidate is not None and to_candidate.can_delegate()
        to_candidate.get_stake_state().add_realtime_amount(btc_asset.get_name(), amount)

        tx.set_delegatee(to_delegatee)
        tx.set_round(round)

    def delegate_power(self, power_round, delegatee, miners):
        assert len(miners) > 0
        candidate = self.chain.get_candidate(delegatee)
        assert candidate is not None, f"{addr_to_name(delegatee)}"
        candidate.get_stake_state().set_round_powers(power_round, miners)

    def add_wallet(self, payment):
        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_stake_state.add_wallet(payment)

    def delegate_btc_lst2(self, tx):
        # add bitcoin tx and delegator debts
        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_stake_state.add_btc_lst_stake_tx(tx)

        amount = tx.get_amount()

        # collect reward
        delegator = tx.get_delegator()
        self.chain.add_btc_lst_balance(delegator, amount)
        self.__update_btc_lst_reward(delegator)

        # update realtime amount
        delegator_stake_state.add_btc_lst_realtime_amount(delegator, amount)
        delegator_stake_state.add_btc_lst_total_realtime_amount(amount)

    def delegate_btc_lst(self, tx):
        # add bitcoin tx and delegator debts
        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_stake_state.add_btc_lst_stake_tx(tx)

        # collect reward
        delegator = tx.get_delegator()
        round = self.chain.get_round()
        change_round = delegator_stake_state.get_btc_lst_change_round(delegator)

        # collcet reward
        btc_asset = self.chain.get_btc_asset()
        if change_round < round:
            # need check history reward
            reward, accured_stake_amount = btc_asset.collect_btc_lst_reward(round, delegator, delegator_stake_state)
            if reward > 0:
                delegator_stake_state.add_btc_lst_history_reward(delegator, reward)

            if accured_stake_amount > 0:
                delegator_stake_state.add_btc_lst_history_accured_stake_amount(delegator, accured_stake_amount)

            delegator_stake_state.update_btc_lst_change_round(delegator, round)

        # update realtime amount
        delegator = tx.get_delegator()
        amount = tx.get_amount()
        delegator_stake_state.add_btc_lst_realtime_amount(delegator, amount)
        delegator_stake_state.add_btc_lst_total_realtime_amount(amount)

        self.chain.add_btc_lst_balance(delegator, amount)

    def transfer_btc_lst(self, from_delegator, to_delegator, amount):
        self.__update_btc_lst_balance(from_delegator, -amount)
        self.__update_btc_lst_balance(to_delegator, amount)

    def __update_btc_lst_balance(self, delegator, amount):
        # erc20 balance
        self.chain.add_btc_lst_balance(delegator, amount)

        # reward
        self.__update_btc_lst_reward(delegator)

        # staked amount
        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_stake_state.add_btc_lst_realtime_amount(delegator, amount)

        is_sync = delegator_stake_state.get_btc_lst_stake_amount(delegator) > \
                  delegator_stake_state.get_btc_lst_realtime_amount(delegator)
        if is_sync:
            delegator_stake_state.sync_btc_lst_stake_amount(delegator)

    def __update_btc_lst_reward(self, delegator):
        delegator_stake_state = self.chain.get_delegator_stake_state()

        change_round = delegator_stake_state.get_btc_lst_change_round(delegator)
        round = self.chain.get_round()
        if change_round >= round:
            return

        # need check history reward
        btc_asset = self.chain.get_btc_asset()
        reward, accured_stake_amount = btc_asset.collect_btc_lst_reward(round, delegator, delegator_stake_state)
        if reward > 0:
            delegator_stake_state.add_btc_lst_history_reward(delegator, reward)

        if accured_stake_amount > 0:
            delegator_stake_state.add_btc_lst_history_accured_stake_amount(delegator, accured_stake_amount)

        delegator_stake_state.update_btc_lst_change_round(delegator, round)

    def redeem_btc_lst(self, delegator, amount, payment):
        assert not payment.is_invalid()

        delegator_stake_state = self.chain.get_delegator_stake_state()
        delegator_realtime_amount = delegator_stake_state.get_btc_lst_realtime_amount(delegator)
        if amount == 0:
            amount = delegator_realtime_amount  # redeem all

        utxo_fee = delegator_stake_state.get_utxo_fee()
        assert amount <= delegator_realtime_amount
        assert amount >= utxo_fee * 2
        amount -= utxo_fee

        # add redeem request
        user_wallet = BtcLSTLockWallet()
        user_wallet.from_payment(payment)
        payment_type = payment.get_type()
        hash = user_wallet.get_hash()
        key = user_wallet.get_key()
        delegator_stake_state.add_redeem_request(key, hash, payment_type, amount)

        # collect reward
        btc_asset = self.chain.get_btc_asset()
        round = self.chain.get_round()

        history_reward, accured_stake_amount = btc_asset.collect_btc_lst_reward(round, delegator, delegator_stake_state)
        if history_reward > 0:
            delegator_stake_state.add_btc_lst_history_reward(delegator, history_reward)

        if accured_stake_amount > 0:
            delegator_stake_state.add_btc_lst_history_accured_stake_amount(delegator, accured_stake_amount)

        # update delegator realtime amount
        burn_amount = amount + utxo_fee
        self.chain.add_btc_lst_balance(delegator, -burn_amount)
        delegator_stake_state.add_btc_lst_realtime_amount(delegator, -burn_amount)

        # sync delegator stake amount
        is_sync = delegator_stake_state.get_btc_lst_stake_amount(delegator) > \
                  delegator_stake_state.get_btc_lst_realtime_amount(delegator)
        if is_sync:
            delegator_stake_state.sync_btc_lst_stake_amount(delegator)

        # update total realtime amount
        delegator_stake_state.add_btc_lst_total_realtime_amount(-burn_amount)

    def undelegate_btc_lst(self, tx):
        txid = tx.get_txid()
        delegator_stake_state = self.chain.get_delegator_stake_state()
        redeem_proof_tx = delegator_stake_state.get_redeem_proof_tx(txid)
        assert redeem_proof_tx is None or not redeem_proof_tx.is_used()

        if redeem_proof_tx is None:
            delegator_stake_state.add_empty_redeem_proof_tx(txid)
            redeem_proof_tx = delegator_stake_state.get_redeem_proof_tx(txid)

        redeem_proof_tx.set_block_number(tx.get_block_number())

        is_valid_tx = False
        vin = tx.get_vin()
        for input in vin:
            prevout_txid = input.prevout.hash
            prev_tx = delegator_stake_state.get_redeem_proof_tx(prevout_txid)
            if prev_tx.get_amount() > 0 and prev_tx.get_index() == input.prevout.n:
                is_valid_tx = True
                break

        assert is_valid_tx

        output_payments = tx.get_output_payments()
        output_index = 0
        for payment in output_payments:
            key = payment.get_key()
            pay_amount = payment.get_amount()
            redeem_request = delegator_stake_state.get_redeem_request(key)
            if redeem_request is None:
                assert delegator_stake_state.get_wallet(payment) is not None
                redeem_proof_tx.set_amount(pay_amount)
                redeem_proof_tx.set_index(output_index)
            else:
                request_amount = redeem_request.get_amount()
                assert request_amount >= pay_amount, f"{request_amount}, {pay_amount}"

                if request_amount == pay_amount:
                    delegator_stake_state.rm_redeem_request(key)
                else:
                    redeem_request.add_amount(-pay_amount)

            output_index += 1

    def update_core_stake_grade_flag(self, grade_flag):
        self.chain.get_delegator_stake_state().update_core_stake_grade_flag(grade_flag)

    def update_core_stake_grades(self, grades):
        self.chain.get_delegator_stake_state().update_core_stake_grades(grades)

    def update_btc_stake_grade_flag(self, grade_flag):
        self.chain.get_delegator_stake_state().update_btc_stake_grade_flag(grade_flag)

    def update_btc_stake_grades(self, grades):
        for grade in grades:
            grade[0] *= constants.ROUND_SECONDS
        self.chain.get_delegator_stake_state().update_btc_stake_grades(grades)

    def update_btc_lst_stake_grade_flag(self, grade_flag):
        self.chain.get_delegator_stake_state().update_btc_lst_stake_grade_flag(grade_flag)

    def update_btc_lst_stake_grade_percent(self, grade_percent):
        self.chain.get_delegator_stake_state().update_btc_lst_stake_grade_percent(grade_percent)
