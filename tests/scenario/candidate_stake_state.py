class CandidateStakeState:
    def __init__(self):
        # (asset name => realtime amount)
        self.realtime_amounts = {}
        # (asset name => amount)
        self.amounts = {}

        # (asset name => score)
        self.scores = {}
        # total score of the all assets
        self.total_score = 0

        # save the rewards allocated to various assets during the turnaround
        # (asset name => reward)
        self.rewards = {}

        # (asset name => [stake amount])
        # e.g. (CORE => [core stake amount])  (BTC => [btc stake amount, btc lst stake amount])
        self.round_stake_amounts = {}

        # (asset name=>(delegator=>round))
        self.delegator_stake_change_rounds = {}

        # (asset name=>(delegator=>amount))
        self.delegator_stake_amounts = {}

        # (asset name=>(delegator=>realtime amount))
        self.delegator_stake_realtime_amounts = {}

        # (asset name=>(delegator=>transferred amount))
        self.delegator_stake_transffered_amounts = {}

        # round => powers
        self.round_powers = {}

    ############# candidate asset state ###################
    def get_realtime_amount(self, asset_name):
        return self.realtime_amounts.get(asset_name, 0)

    def add_realtime_amount(self, asset_name, delta_amount):
        self.realtime_amounts[asset_name] = self.get_realtime_amount(asset_name) + delta_amount
        assert self.realtime_amounts[asset_name] >= 0

    def get_stake_amount(self, asset_name):
        return self.amounts.get(asset_name, 0)

    def add_stake_amount(self, asset_name, delta_amount):
        self.amounts[asset_name] = self.get_stake_amount(asset_name) + delta_amount
        assert self.amounts[asset_name] >= 0

    def sync_stake_amount(self, asset_name):
        self.amounts[asset_name] = self.realtime_amounts.get(asset_name, 0)

    ############### delegator asset state ####################
    def get_delegator_change_round(self, asset_name, delegator):
        if self.delegator_stake_change_rounds.get(asset_name) is None:
            return 0

        return self.delegator_stake_change_rounds[asset_name].get(delegator, 0)

    def update_delegator_change_round(self, asset_name, delegator, round):
        if self.delegator_stake_change_rounds.get(asset_name) is None:
            self.delegator_stake_change_rounds[asset_name] = {}

        assert round == 0 or round > self.get_delegator_change_round(asset_name, delegator)
        self.delegator_stake_change_rounds[asset_name][delegator] = round

    def get_delegator_realtime_amount(self, asset_name, delegator):
        if self.delegator_stake_realtime_amounts.get(asset_name) is None:
            return 0

        return self.delegator_stake_realtime_amounts[asset_name].get(delegator, 0)

    def add_delegator_realtime_amount(self, asset_name, delegator, delta_amount):
        if self.delegator_stake_realtime_amounts.get(asset_name) is None:
            self.delegator_stake_realtime_amounts[asset_name] = {}

        self.delegator_stake_realtime_amounts[asset_name][delegator] = \
            self.get_delegator_realtime_amount(asset_name, delegator) + delta_amount

        assert self.delegator_stake_realtime_amounts[asset_name][delegator] >= 0

    def get_delegator_stake_amount(self, asset_name, delegator):
        if self.delegator_stake_amounts.get(asset_name) is None:
            return 0

        return self.delegator_stake_amounts[asset_name].get(delegator, 0)

    def sync_delegator_stake_amount(self, asset_name, delegator):
        if self.delegator_stake_amounts.get(asset_name) is None:
            self.delegator_stake_amounts[asset_name] = {}

        self.delegator_stake_amounts[asset_name][delegator] = \
            self.get_delegator_realtime_amount(asset_name, delegator)

    def add_delegator_stake_amount(self, asset_name, delegator, delta_amount):
        if self.delegator_stake_amounts.get(asset_name) is None:
            self.delegator_stake_amounts[asset_name] = {}

        self.delegator_stake_amounts[asset_name][delegator] = \
            self.get_delegator_stake_amount(asset_name, delegator) + delta_amount

        assert self.delegator_stake_amounts[asset_name][delegator] >= 0

    def get_delegator_transferred_amount(self, asset_name, delegator):
        if self.delegator_stake_transffered_amounts.get(asset_name) is None:
            return 0

        return self.delegator_stake_transffered_amounts[asset_name].get(delegator, 0)

    def add_delegator_transferred_amount(self, asset_name, delegator, delta_amount):
        new_amount = self.get_delegator_transferred_amount(asset_name, delegator) + delta_amount
        self.update_delegator_transferred_amount(asset_name, delegator, new_amount)

    def update_delegator_transferred_amount(self, asset_name, delegator, amount):
        assert amount >= 0
        if self.delegator_stake_transffered_amounts.get(asset_name) is None:
            self.delegator_stake_transffered_amounts[asset_name] = {}

        self.delegator_stake_transffered_amounts[asset_name][delegator] = amount

    def set_round_powers(self, power_round, miners):
        assert self.round_powers.get(power_round) is None

        self.round_powers[power_round] = miners

    def get_round_powers(self, power_round):
        return len(self.get_round_miners(power_round))

    def get_round_miners(self, power_round):
        return self.round_powers.get(power_round, [])

    ################# asset  score ################
    # save the pledged asset quantities during the turn round
    # @param  asset_amount_list is a list, e.g. asset_name=BTC, asset_amounts=[btc realtime amount, btc lst realtime amount]
    def init_round_stake_amount_list(self, asset_name, asset_amount_list):
        self.round_stake_amounts[asset_name] = asset_amount_list

    def get_round_stake_amount_list(self, asset_name):
        return self.round_stake_amounts.get(asset_name, [])

    def update_score(self, asset_name, asset_factor):
        asset_amount_list = self.get_round_stake_amount_list(asset_name)
        self.scores[asset_name] = sum(asset_amount_list) * asset_factor

    def get_score(self, asset_name):
        return self.scores.get(asset_name, 0)

    def get_total_score(self):
        return self.total_score

    def update_total_score(self):
        self.total_score = 0
        for asset in self.scores:
            self.total_score += self.scores[asset]

    ################ asset reward ################
    def get_reward(self, asset_name):
        return self.rewards.get(asset_name, 0)

    def set_reward(self, asset_name, reward):
        self.rewards[asset_name] = reward
