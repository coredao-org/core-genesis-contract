from collections import defaultdict
from copy import copy

from tests.constant import *
from tests.utils import get_asset_weight


class Discount:
    # month:discount
    tlp_rates = {
        12: 10000,
        8: 8000,
        5: 5000,
        1: 4000,
        0: 2000
    }
    # Core reward ratio: discount
    lp_rates = {
        15000: 12000,
        12000: 10000,
        5000: 6000,
        0: 1000
    }
    percentage = 5000
    state_map = {}

    def get_init_discount(self):
        tlp_rates = []
        lp_rates = []
        for t in list(self.tlp_rates.keys())[::-1]:
            tlp_rates.append(t)
            tlp_rates.append(self.tlp_rates[t])
        for l in list(self.lp_rates.keys())[::-1]:
            lp_rates.append(l)
            lp_rates.append(self.lp_rates[l])
        return tlp_rates, lp_rates


def set_delegate(address, value, undelegate_amount=0, stake_duration=500):
    return {"address": address, "value": value, "undelegate_amount": undelegate_amount,
            'stake_duration': stake_duration}


def set_btc_lst_delegate(delegate_amount, redeem_amount=0):
    return {"delegate_amount": delegate_amount, "redeem_amount": redeem_amount}


def get_tlp_rate(day):
    rate = Utils.DENOMINATOR
    months = day // 30
    for i in Discount.tlp_rates:
        if months >= i:
            rate = Discount.tlp_rates[i]
            break

    return months, rate


def get_lp_rate(coin_amount, asset_amount, asset):
    discount = Utils.DENOMINATOR
    level = (coin_amount * get_asset_weight(asset)) // (asset_amount * get_asset_weight('coin'))
    for l in Discount.lp_rates:
        if level >= l:
            discount = Discount.lp_rates[l]
            break
    return level, discount


def init_btc_lst_count(btc_lst_stake, validator_count):
    if btc_lst_stake is None:
        return 0, 0, 0
    btc_lst_stake_amount = sum(amount['delegate_amount'] for amount in btc_lst_stake.values())
    single_agent_btc_lst = btc_lst_stake_amount // validator_count
    agent_btc_lst = single_agent_btc_lst * validator_count
    return btc_lst_stake_amount, single_agent_btc_lst, agent_btc_lst


def init_validators_score(agents, factor_map):
    for agent in agents:
        total_power = agent['total_power']
        total_coin = agent['total_coin']
        total_btc = agent['total_btc']
        agent['validator_score'] = total_coin * factor_map['coin'] + total_power * factor_map['power'] + (
            total_btc) * factor_map['btc']


def init_current_round_factor(factor_map, stake_count, reward_cap):
    factor1 = 0
    for s in factor_map:
        factor = 1
        if s == 'coin':
            factor1 = factor
        else:
            if stake_count['coin'] > 0 and stake_count[s] > 0:
                factor = (factor1 * stake_count['coin']) * reward_cap[s] // reward_cap['coin'] // stake_count[s]
        factor_map[s] = factor


def init_stake_score(agents, total_reward, btc_lst_stake):
    stake_count = {
        'coin': 0,
        'power': 0,
        'btc': 0
    }
    validator_count = 0
    for agent in agents:
        agent['totalReward'] = total_reward
        total_power = sum([item['value'] for item in agent.get('power', [])])
        agent['total_power'] = total_power
        total_coin = sum([item['value'] for item in agent.get('coin', [])])
        agent['total_coin'] = total_coin
        total_btc = sum([item['value'] for item in agent.get('btc', [])])
        agent['total_btc'] = total_btc
        stake_count['power'] += total_power
        stake_count['coin'] += total_coin
        stake_count['btc'] += total_btc
        validator_count += 1
    btc_lst_amount, single_agent_btc_lst, agent_btc_lst = init_btc_lst_count(btc_lst_stake, validator_count)
    for agent in agents:
        agent['total_btc'] += single_agent_btc_lst
        agent['total_btc_lst'] = single_agent_btc_lst
    stake_count['btc'] += agent_btc_lst
    return stake_count


def calc_agent_asset_reward_distribution(agent, asset, asset_factor):
    key_asset_amount = 'total_' + asset  # e.g. total_coin, total_power, total_btc
    key_asset_reward = asset + '_reward'  # e.g. coin_reward, power_reward, btc_reward
    key_total_score = 'validator_score'
    key_total_reward = 'totalReward'
    if agent[key_asset_amount] == 0:
        return 0
    asset_amount = agent[key_asset_amount]
    total_score = agent[key_total_score]
    total_reward = agent[key_total_reward]
    agent[key_asset_reward] = total_reward * (asset_amount * asset_factor) // total_score
    if asset == 'btc':
        agent['sum_btc'] = asset_amount
        total_btc_reward = agent[key_asset_reward]
        lst_amount = agent['total_btc_lst']
        agent['btc_lst_reward'] = total_btc_reward * lst_amount // asset_amount
        agent[key_asset_reward] = total_btc_reward - agent['btc_lst_reward']
        agent[key_asset_amount] -= lst_amount


def calc_agent_asset_reward(agent, asset, unit_amount):
    key_asset_reward = asset + '_reward'  # e.g. coin_reward, power_reward, btc_reward
    key_asset_amount = 'total_' + asset  # e.g. total_coin, total_power, total_btc,total_btc_lst
    if agent[key_asset_amount] == 0:
        return 0
    key_asset_unit_reward = 'single_' + asset + '_reward'
    agent[key_asset_unit_reward] = agent[key_asset_reward] * unit_amount // agent[key_asset_amount]
    return agent[key_asset_unit_reward]


def calc_btc_lst_asset_reward(agents, btc_lst_stake, asset, unit_amount):
    key_asset_reward = asset + '_reward'  # e.g. coin_reward, power_reward, btc_reward
    total_btc_lst_reward = 0
    total_btc_lst = sum(amount['delegate_amount'] for amount in btc_lst_stake.values())
    if total_btc_lst == 0:
        return 0
    for agent in agents:
        total_btc_lst_reward += agent[key_asset_reward]
    asset_unit_reward = total_btc_lst_reward * unit_amount // total_btc_lst
    for agent in agents:
        agent['single_btc_lst_reward'] = asset_unit_reward
    return asset_unit_reward


def calc_coin_delegator_reward(agent, stake_list, delegator_asset_reward, delegator_map):
    for item in stake_list:
        stake_amount = item['value'] - item['undelegate_amount']
        delegator = item['address']
        if delegator_map['coin'].get(delegator) is None:
            delegator_map['coin'][delegator] = stake_amount
        else:
            delegator_map['coin'][delegator] += stake_amount
        actual_account_coin_reward = agent['single_coin_reward'] * stake_amount // Utils.CORE_STAKE_DECIMAL
        if delegator_asset_reward['coin'].get(delegator) is None:
            delegator_asset_reward['coin'][delegator] = actual_account_coin_reward
        else:
            delegator_asset_reward['coin'][delegator] += actual_account_coin_reward
        print(f"coin reward: {agent['address']} on {delegator} => {actual_account_coin_reward}")


def calc_power_delegator_reward(agent, stake_list, delegator_asset_reward, delegator_map):
    for item in stake_list:
        actual_account_reward = agent['single_power_reward'] * item['value']
        if delegator_map['power'].get(item['address']) is None:
            delegator_map['power'][item['address']] = item['value']
        else:
            delegator_map['power'][item['address']] += item['value']
        if delegator_asset_reward['power'].get(item['address']) is None:
            delegator_asset_reward['power'][item['address']] = actual_account_reward
        else:
            delegator_asset_reward['power'][item['address']] += actual_account_reward
        print(f"power reward: {agent['address']} on {item['address']} => {actual_account_reward}")


def calc_btc_delegator_reward(agent, stake_list, delegator_asset_reward, bonus, delegator_map):
    for item in stake_list:
        stake_amount = item['value'] - item['undelegate_amount']
        if delegator_map['btc'].get(item['address']) is None:
            delegator_map['btc'][item['address']] = item['value']
        else:
            delegator_map['btc'][item['address']] += item['value']
        actual_account_btc_reward = agent['single_btc_reward'] * stake_amount // Utils.BTC_DECIMAL
        # staking duration discount logic
        if item['stake_duration'] < 360:
            months, duration_discount = get_tlp_rate(item['stake_duration'])
            if Discount.state_map['btc_gradeActive']:
                actual_account_btc_reward, unclaimed = calc_discounted_reward_amount(actual_account_btc_reward,
                                                                                     duration_discount)
                bonus['total_bonus'] += unclaimed
        if delegator_asset_reward['btc'].get(item['address']) is None:
            delegator_asset_reward['btc'][item['address']] = actual_account_btc_reward
        else:
            delegator_asset_reward['btc'][item['address']] += actual_account_btc_reward
        print(f"btc reward: {agent['address']} on {item['address']} => {actual_account_btc_reward}")


def calc_discounted_reward_amount(round_reward, duration_discount):
    actual_reward = round_reward * duration_discount // Utils.DENOMINATOR
    unclaimed_reward = round_reward - actual_reward
    return actual_reward, unclaimed_reward


def calc_btc_lst_delegator_reward(stake_list, asset_unit_reward_map, delegator_asset_reward, bonus, delegator_map):
    for delegator in stake_list:
        stake_amount = stake_list[delegator]['delegate_amount'] - stake_list[delegator]['redeem_amount']
        if delegator_map['btc_lst'].get(delegator) is None:
            delegator_map['btc_lst'][delegator] = stake_amount
        else:
            delegator_map['btc_lst'][delegator] += stake_amount
        account_btc_lst_reward = asset_unit_reward_map['btc_lst'] * stake_amount // Utils.BTC_DECIMAL
        if Discount.state_map['btc_lst_gradeActive']:
            account_btc_lst_reward, unclaimed = calc_discounted_reward_amount(account_btc_lst_reward,
                                                                              Discount.state_map['percentage'])
            bonus['total_bonus'] += unclaimed
        if delegator_asset_reward['btc_lst'].get(delegator) is None:
            delegator_asset_reward['btc_lst'][delegator] = account_btc_lst_reward
        else:
            delegator_asset_reward['btc_lst'][delegator] += account_btc_lst_reward
        print(f"btc lst reward: {delegator} => {account_btc_lst_reward}")


def calc_core_discounted_reward(discount_asset, delegator_asset_reward, bonus, compensation_reward, delegator_map):
    for r in discount_asset:
        delegator_reward = delegator_asset_reward.get(r, {})
        delegator_info = delegator_map.get(r, {})
        for delegator in delegator_reward:
            coin_acc_stake_amount = delegator_map['coin'].get(delegator, 0)
            asset_acc_stake_amount = delegator_info[delegator]
            asset_reward = delegator_reward[delegator]
            level, reward_discount = get_lp_rate(coin_acc_stake_amount, asset_acc_stake_amount, r)
            actual_account_btc_reward = asset_reward * reward_discount // Utils.DENOMINATOR
            if reward_discount >= Utils.DENOMINATOR:
                actual_bonus = actual_account_btc_reward - asset_reward
                system_reward = compensation_reward['system_reward']
                if actual_bonus > compensation_reward['reward_pool']:
                    system_reward -= actual_bonus * 10
                    compensation_reward['reward_pool'] += actual_bonus * 10
                compensation_reward['reward_pool'] -= actual_bonus
            if asset_reward > actual_account_btc_reward:
                compensation_reward['reward_pool'] += asset_reward - actual_account_btc_reward
            bonus['reward_pool'] = compensation_reward['reward_pool']
            delegator_reward[delegator] = actual_account_btc_reward


def calc_accrued_reward_per_asset(agents, btc_lst_stake, reward_unit_amount_map, asset_unit_reward_map):
    # calculate the reward for BTC LST separately
    asset = 'btc_lst'
    asset_unit_reward = calc_btc_lst_asset_reward(agents, btc_lst_stake, asset, reward_unit_amount_map['btc'])
    asset_unit_reward_map[asset] = asset_unit_reward
    # calculate Core Power BTC reward
    for asset in reward_unit_amount_map:
        if asset_unit_reward_map.get(asset) is None:
            asset_unit_reward_map[asset] = {}
        for agent in agents:
            unit_amount = reward_unit_amount_map[asset]
            asset_unit_reward = calc_agent_asset_reward(agent, asset, unit_amount)
            asset_unit_reward_map[asset][agent['address']] = asset_unit_reward


def update_delegator_total_reward(asset_reward_map, account_rewards_map):
    for asset in asset_reward_map:
        for delegator in asset_reward_map[asset]:
            if account_rewards_map.get(delegator) is None:
                account_rewards_map[delegator] = 0
            account_rewards_map[delegator] += asset_reward_map[asset][delegator]


def get_core_lp_asset(n):
    mapping = {1: 'coin', 2: 'power', 4: 'btc'}
    result = ','.join(value for key, value in mapping.items() if n & key)
    return result


def set_coin_delegator(coin_delegator, validator, delegator, remain_coin, transfer_out_deposit, total_coin):
    coin_delegator[validator] = {delegator: {'remain_coin': remain_coin, 'transferOutDeposit': transfer_out_deposit,
                                             'total_pledged_amount': total_coin}}


def calculate_coin_rewards(score, sum_score, coin_reward):
    return coin_reward * score // sum_score


def parse_delegation(agents, block_reward, btc_lst_stake=None, state_map=None, compensation_reward=None,
                     reward_cap=None):
    if btc_lst_stake is None:
        btc_lst_stake = {}
    if compensation_reward is None:
        compensation_reward = {
            'reward_pool': 0,
            'system_reward': 100000000
        }
    new_state_map = state_map
    if new_state_map is None:
        new_state_map = {}
    state_map = {
        'percentage': Discount.percentage,
        'core_lp': 0,
        'btc_lst_gradeActive': 1,
        'btc_gradeActive': 1
    }

    for i in new_state_map:
        state_map[i] = new_state_map[i]
    Discount.state_map = state_map
    total_reward = block_reward
    if reward_cap is None:
        reward_cap = {
            'coin': HardCap.CORE_HARD_CAP,
            'power': HardCap.POWER_HARD_CAP,
            'btc': HardCap.BTC_HARD_CAP
        }
    factor_map = {
        'coin': 1,
        'power': 0,
        'btc': 0
    }
    reward_unit_amount_map = {
        'coin': Utils.CORE_STAKE_DECIMAL,
        'power': 1,
        'btc': Utils.BTC_DECIMAL
    }

    # init asset score for 3 assets: coin, power, btc
    stake_count = init_stake_score(agents, total_reward, btc_lst_stake)

    # init asset factor for 3 assets: coin, power, btc
    init_current_round_factor(factor_map, stake_count, reward_cap)

    # calculate the total score for each validator
    init_validators_score(agents, factor_map)
    # calc the reward distribution of each asset for each agent
    for asset in factor_map:
        for agent in agents:
            calc_agent_asset_reward_distribution(agent, asset, factor_map[asset])

    asset_unit_reward_map = {}
    # calculate the accrued reward for each asset (coin power btc btc_lst)
    calc_accrued_reward_per_asset(agents, btc_lst_stake, reward_unit_amount_map, asset_unit_reward_map)

    # keys coin & power & btc & btc_lst
    delegator_asset_reward = defaultdict(dict)

    # keys total_bonus
    bonus = defaultdict(int)

    # keys coin & power & btc
    delegator_map = defaultdict(dict)

    # calculate rewards for each asset of the delegator
    calc_btc_lst_delegator_reward(btc_lst_stake, asset_unit_reward_map, delegator_asset_reward, bonus, delegator_map)
    for agent in agents:
        calc_coin_delegator_reward(agent, agent.get('coin', []), delegator_asset_reward, delegator_map)
        calc_power_delegator_reward(agent, agent.get('power', []), delegator_asset_reward, delegator_map)
        calc_btc_delegator_reward(agent, agent.get('btc', []), delegator_asset_reward, bonus, delegator_map)
    total_bonus = bonus.get('total_bonus', 0)
    compensation_reward['reward_pool'] += total_bonus
    # calculate Core reward ratio discount
    core_lp = Discount.state_map['core_lp']
    if core_lp:
        asset = ['btc']
        calc_core_discounted_reward(asset, delegator_asset_reward, bonus, compensation_reward, delegator_map)
    bonus['btc'] = bonus.get('reward_pool')
    bonus['total_bonus'] = bonus.get('reward_pool')
    # distribute the bonus proportionally to assets (coin, power, btc)
    account_claimed_rewards = {}
    update_delegator_total_reward(delegator_asset_reward, account_claimed_rewards)
    print(f'parse_delegation account_rewards: {account_claimed_rewards}')
    return delegator_asset_reward, bonus, account_claimed_rewards, asset_unit_reward_map


if __name__ == '__main__':
    reward, unclaimed_reward, account_rewards, round_reward = parse_delegation([{
        "address": 'v0',
        "active": True,
        "coin": [set_delegate('a1', 1000)],
        "btc": [set_delegate('a0', 200)]
    }], 13545)
