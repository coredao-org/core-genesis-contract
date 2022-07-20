from collections import defaultdict


def set_delegate(address, value):
    return {"address": address, "value": value}


def parse_delegation(agents, block_reward):
    """
    :param block_reward:
    :param agents:
        example:
        [{
            "address": 0xdasdas213123,
            "active": True,
            "coin": [{
                "address": 0x21312321389123890,
                "value: 3
            }, {
                "address": 0x21312321389123890,
                "value: 4
            }],
            "power": [{
                "address": 0x128381290830912,
                "value: 99
            }]
        }]
    :return: agent integral dict and delegate reward dict
        example:
        {"0xdasdas213123": 33, "0x12321312312": 23}
        {"0x21312321389123890": 13, "0x21312321389123890": 3}
    """
    btc_count = 1
    coin_count = 1

    agent_integral = {}
    delegator_reward = defaultdict(int)

    for agent in agents:
        total_power = sum([item['value'] for item in agent['power']])
        agent['total_power'] = total_power
        btc_count += total_power
        total_coin = sum([item['value'] for item in agent['coin']])
        agent['total_coin'] = total_coin
        coin_count += total_coin

    for agent in agents:
        agent_integral[agent['address']] = 2 * agent['total_power'] * coin_count + agent['total_coin'] * btc_count

    for agent in agents:
        if not agent['active']:
            continue
        for item in agent['coin']:
            reward = block_reward * item['value'] * btc_count // agent_integral[agent['address']]
            delegator_reward[item['address']] += reward
            print(f"coin reward: {agent['address']} on {item['address']} => {reward}")
        for item in agent['power']:
            reward = block_reward * item['value'] * coin_count // 10000
            reward = reward * 20000 // agent_integral[agent['address']]
            delegator_reward[item['address']] += reward
            print(f"power reward: {agent['address']} on {item['address']} => {reward}")

    return agent_integral, delegator_reward


if __name__ == '__main__':
    # delegate_info = [{
    #     "address": "n1",
    #     "coin": [set_delegate("x", 4), set_delegate("y", 2)],
    #     "power": [set_delegate("x", 2), set_delegate("y", 1)]
    # }, {
    #     "address": "n2",
    #     "coin": [{"address": "z", "value": 9}],
    #     "power": [{"address": "z", "value": 2}]
    # }]

    delegate_info = [{
        "address": "n0",
        "active": True,
        "coin": [set_delegate("x", 2e18)],
        "power": [set_delegate("x", 6e18)]
    }]

    _agent_integral, _delegator_reward = parse_delegation(delegate_info, 324000000)
    print(_agent_integral)
    print(_delegator_reward)
