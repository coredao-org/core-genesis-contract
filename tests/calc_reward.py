from tests.constant import *


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
        12000: 10000,
        5000: 6000,
        0: 1000
    }

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

def set_delegate(address, value, undelegate_amount=0, stake_duration=False):
    return {"address": address, "value": value, "undelegate_amount": undelegate_amount,
            'stake_duration': stake_duration}


def get_tlp_rate(day):
    rate = Utils.DENOMINATOR
    months = day // 30
    for i in Discount.tlp_rates:
        if months >= i:
            rate = Discount.tlp_rates[i]
            break

    return months, rate


def get_lp_rate(coin_reward, btc_reward):
    discount = Utils.DENOMINATOR
    level = coin_reward * Utils.DENOMINATOR // btc_reward
    for l in Discount.lp_rates:
        if level >= l:
            discount = Discount.lp_rates[l]
            break

    return level, discount


def init_stake_score(agents, total_reward, factor_map):
    stake_score = {
        'coin': 0,
        'power': 0,
        'btc': 0
    }

    for agent in agents:
        agent['totalReward'] = total_reward

        total_power = sum([item['value'] for item in agent['power']])
        agent['total_power'] = total_power

        total_coin = sum([item['value'] for item in agent['coin']])
        agent['total_coin'] = total_coin

        total_btc = sum([item['value'] for item in agent['btc']])
        agent['total_btc'] = total_btc

        agent['validator_score'] = total_coin + total_power * factor_map['power'] + total_btc * factor_map['btc']

        stake_score['power'] += total_power * factor_map['power']
        stake_score['coin'] += total_coin
        stake_score['btc'] += total_btc * factor_map['btc']

    return stake_score


def init_reward_discount_for_hardcap(stake_score_map, reward_cap_map):
    reward_discount = {
        'coin': 10000,
        'power': 10000,
        'btc': 10000
    }

    total_asset_points = stake_score_map['coin'] + stake_score_map['power'] + stake_score_map['btc']
    for asset in stake_score_map:
        if stake_score_map.get(asset) * HardCap.SUM_HARD_CAP > reward_cap_map[asset] * total_asset_points:
            discount = reward_cap_map[asset] * total_asset_points * Utils.DENOMINATOR // (
                    HardCap.SUM_HARD_CAP * stake_score_map[asset])
            reward_discount[asset] = discount

    return reward_discount


def calc_agent_asset_reward(agent, asset, asset_factor, reward_discount, unit_amount, compensation_reward=None):
    key_asset_amount = 'total_' + asset  # e.g. total_coin, total_power, total_btc
    key_asset_reward = asset + '_reward'  # e.g. coin_reward, power_reward, btc_reward
    key_asset_unit_reward = 'single_' + key_asset_reward  # e.g. single_coin_reward, ...
    key_total_score = 'validator_score'
    key_total_reward = 'totalReward'

    if agent[key_asset_amount] == 0:
        return 0, 0

    asset_amount = agent[key_asset_amount]
    total_score = agent[key_total_score]
    total_reward = agent[key_total_reward]
    agent[key_asset_reward] = total_reward * (
            asset_amount * asset_factor) // total_score * reward_discount // Utils.DENOMINATOR

    if asset != 'power' and compensation_reward:
        agent[key_asset_reward] += compensation_reward[asset].get(agent['address'], 0)

    agent[key_asset_unit_reward] = agent[key_asset_reward] * unit_amount // agent[key_asset_amount]

    return agent[key_asset_unit_reward], agent[key_asset_reward]


def calc_coin_delegator_reward(agent, stake_list, delegator_reward_map):
    for item in stake_list:
        actual_account_coin_reward = agent['single_coin_reward'] * (
                item['value'] - item['undelegate_amount']) // Utils.CORE_STAKE_DECIMAL

        if delegator_reward_map.get(item['address']) is None:
            delegator_reward_map[item['address']] = actual_account_coin_reward
        else:
            delegator_reward_map[item['address']] += actual_account_coin_reward

        print(f"coin reward: {agent['address']} on {item['address']} => {actual_account_coin_reward}")


def calc_power_delegator_reward(agent, stake_list, delegator_reward_map):
    for item in stake_list:
        actual_account_reward = agent['single_power_reward'] * item['value']

        if delegator_reward_map.get(item['address']) is None:
            delegator_reward_map[item['address']] = actual_account_reward
        else:
            delegator_reward_map[item['address']] += actual_account_reward

        print(f"power reward: {agent['address']} on {item['address']} => {actual_account_reward}")


def calc_btc_delegator_reward(agent, stake_list, delegator_reward_map, unclaimed_reward_map, unclaimed_info_map,
                              rates_core_map, core_lp):
    for item in stake_list:
        actual_account_btc_reward = agent['single_btc_reward'] * item['value'] // Utils.BTC_DECIMAL
        b_btc_reward = actual_account_btc_reward

        if item['stake_duration']:
            months, duration_discount = get_tlp_rate(item['stake_duration'])
            actual_account_btc_reward = actual_account_btc_reward * duration_discount // Utils.DENOMINATOR

            if unclaimed_reward_map.get(item['address']) is None:
                unclaimed_reward_map[item['address']] = 0

            unclaimed_reward_map[item['address']] += b_btc_reward - actual_account_btc_reward

            unclaimed_info_map['duration'] += b_btc_reward - actual_account_btc_reward

            rates_key = str(item['address']) + str(agent['address'])
            rates_core_map[rates_key] = {
                'duration': [item['stake_duration'], months, duration_discount,
                             b_btc_reward - actual_account_btc_reward]
            }

        if core_lp:
            if unclaimed_reward_map.get(item['address']) is None:
                unclaimed_reward_map[item['address']] = 0

        if delegator_reward_map.get(item['address']) is None:
            delegator_reward_map[item['address']] = actual_account_btc_reward
        else:
            delegator_reward_map[item['address']] += actual_account_btc_reward
        print(f"btc reward: {agent['address']} on {item['address']} => {actual_account_btc_reward}")


def calc_delegator_actual_reward(delegator, coin_reward_map, btc_reward_map, unclaimed_reward_map, unclaimed_info_map,
                                 rates_core_map):
    coin_reward = coin_reward_map.get(delegator, 0)
    btc_reward = btc_reward_map.get(delegator)

    level, reward_discount = get_lp_rate(coin_reward, btc_reward)

    actual_account_btc_reward = btc_reward * reward_discount // Utils.DENOMINATOR
    btc_reward_map[delegator] = actual_account_btc_reward

    unclaimed_reward_map[delegator] += btc_reward - actual_account_btc_reward

    unclaimed_info_map['core'] += btc_reward - actual_account_btc_reward
    rates_core_map[delegator] = {'core_rate': [level, reward_discount]}


def update_delegator_total_reward(asset_reward_map, account_rewards_map):
    for delegator in asset_reward_map:
        if account_rewards_map.get(delegator) is None:
            account_rewards_map[delegator] = 0

        account_rewards_map[delegator] += asset_reward_map.get(delegator)


def parse_delegation(agents, block_reward, power_factor=500, btc_factor=10, core_lp=False, compensation_reward=None):
    """
    :param block_reward:
    :param agents:
        example:
        [{
            "address": 0x1,
            "active": True,
            "coin": [{"address": 0xa,"value: 3}],
            "power": [{"address": 0xb,"value: 99 }]
        }]
    :return: agent score dict and delegate reward dict
        example:
        {"0xa": 33, "0xb": 23}
    """
    total_reward = block_reward

    reward_cap = {
        'coin': HardCap.CORE_HARD_CAP,
        'power': HardCap.POWER_HARD_CAP,
        'btc': HardCap.BTC_HARD_CAP
    }

    factor_map = {
        'coin': 1,
        'power': power_factor,
        'btc': btc_factor
    }

    reward_unit_amount_map = {
        'coin': Utils.CORE_STAKE_DECIMAL,
        'power': 1,
        'btc': Utils.BTC_DECIMAL
    }

    # init asset score for 3 assets: coin, power, btc
    stake_score = init_stake_score(agents, total_reward, factor_map)

    # discounts on hard cap bonuses
    collateral_state = init_reward_discount_for_hardcap(stake_score, reward_cap)

    # calc the reward distribution of each asset for each agent
    asset_reward_map = {}
    asset_unit_reward_map = {}
    for asset in stake_score:
        for agent in agents:
            if asset_reward_map.get(asset) is None:
                asset_reward_map[asset] = {}

            factor = factor_map[asset]
            discount = collateral_state[asset]
            unit_amount = reward_unit_amount_map[asset]

            asset_unit_reward, asset_reward = calc_agent_asset_reward(
                agent,
                asset,
                factor,
                discount,
                unit_amount,
                compensation_reward
            )

            asset_unit_reward_map[asset] = asset_unit_reward
            asset_reward_map[asset][agent['address']] = asset_reward

    delegator_coin_reward = {}
    delegator_power_reward = {}
    delegator_btc_reward = {}

    unclaimed_reward = {}
    unclaimed_info = {
        'core': 0,
        'duration': 0
    }

    # rates_core is for debugging purposes
    rates_core = {}
    for agent in agents:
        calc_coin_delegator_reward(agent, agent['coin'], delegator_coin_reward)
        calc_power_delegator_reward(agent, agent['power'], delegator_power_reward)
        calc_btc_delegator_reward(agent, agent['btc'], delegator_btc_reward, unclaimed_reward, unclaimed_info,
                                  rates_core, core_lp)

    for delegator in unclaimed_reward:
        calc_delegator_actual_reward(
            delegator,
            delegator_coin_reward,
            delegator_btc_reward,
            unclaimed_reward,
            unclaimed_info,
            rates_core
        )

    account_rewards = {}
    update_delegator_total_reward(delegator_coin_reward, account_rewards)
    update_delegator_total_reward(delegator_power_reward, account_rewards)
    update_delegator_total_reward(delegator_btc_reward, account_rewards)
    print(f'delegator rewards : {account_rewards}')
    rewards = [delegator_coin_reward, delegator_power_reward, delegator_btc_reward]
    unclaimed = [unclaimed_reward, unclaimed_info]
    round_reward = [asset_unit_reward_map, asset_reward_map]
    return rewards, unclaimed, account_rewards, round_reward, collateral_state


def set_coin_delegator(coin_delegator, validator, delegator, remain_coin, transfer_out_deposit, total_coin):
    coin_delegator[validator] = {delegator: {'remain_coin': remain_coin, 'transferOutDeposit': transfer_out_deposit,
                                             'total_pledged_amount': total_coin}}


def calculate_rewards(agent_list: list, coin_delegator: dict, actual_debt_deposit, account, block_reward):
    result = []
    total_reward = block_reward
    for agent in agent_list:
        d = coin_delegator.get(agent, {}).get(account, 0)
        expect_reward = 0
        if d == 0:
            result.append(expect_reward)
        else:
            if d['transferOutDeposit'] > actual_debt_deposit:
                d['transferOutDeposit'] -= actual_debt_deposit
                actual_debt_deposit = 0
            else:
                actual_debt_deposit -= d['transferOutDeposit']
                d['transferOutDeposit'] = 0
            expect_reward = total_reward * (d['transferOutDeposit'] + d['remain_coin']) // d['total_pledged_amount']
            result.append(expect_reward)
    return result


def calculate_coin_rewards(score, sum_score, coin_reward):
    return coin_reward * score // sum_score


def calculate_power_rewards(score, sum_score, coin_reward):
    return coin_reward * score // sum_score


if __name__ == '__main__':
    delegate_info = [
        {
            "address": "n2",
            "active": True,
            "coin": [],
            "power": [set_delegate("a2", 200)],
            "btc": []
        }, {
            "address": "n1",
            "active": True,
            "coin": [set_delegate("a0", 80000)],
            "power": [],
            "btc": []
        },
        {
            "address": "n0",
            "active": True,
            "coin": [],
            "power": [],
            "btc": [set_delegate("a0", 2000)],
        }
    ]
    parse_delegation(delegate_info, 13545, core_lp=True)
