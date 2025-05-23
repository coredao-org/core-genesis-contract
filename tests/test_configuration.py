import pytest
import brownie
import rlp
from eth_utils import to_bytes

from .delegate import StakeManager
from .utils import *
from .common import register_candidate, execute_proposal
from web3 import Web3

stake_manager = StakeManager()


@pytest.fixture(scope="module", autouse=True)
def set_up(configuration):
    update_system_contract_address(configuration, gov_hub=accounts[0])


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def set_event(rewards, event_name, gas, is_bytes=True):
    signature = Web3.keccak(text=event_name)
    rewards_value = []
    for reward in rewards:
        if is_bytes:
            address = to_bytes(hexstr=reward[0].address)
        else:
            address = reward[0].address
        rewards_value.append([address, reward[1]])
    event = [rewards_value, signature, gas]
    return event


def test_only_gov_can_call(configuration, core_agent):
    update_system_contract_address(configuration, gov_hub=accounts[1])
    grades = [ZERO_ADDRESS, [[ZERO_ADDRESS, 0], random_btc_tx_id(), 1000], 1000]
    grades_encode = rlp.encode(grades)
    with brownie.reverts("the msg sender must be governance contract"):
        configuration.updateParam('addConfig', grades_encode)


def test_add_config_success(configuration, core_agent):
    event_prototype = "Transfer(address,address,uint256)"
    signature = Web3.keccak(text=event_prototype)
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [
                [
                    [to_bytes(hexstr=accounts[1].address), 2000],
                    [to_bytes(hexstr=accounts[2].address), 8000]
                ],
                signature,
                20000],
            [
                [
                    [to_bytes(hexstr=accounts[3].address), 7000],
                    [to_bytes(hexstr=accounts[4].address), 3000]
                ],
                'btcExpired',
                100000
            ]
        ],
        []
    ]
    value_encode = rlp.encode(value)
    configuration.updateParam('addConfig', value_encode)
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['configAddress'] == accounts[0]
    assert config_fee['isActive']
    hex_32bytes = '0x' + 'btcExpired'.encode('utf-8').ljust(32, b'\x00').hex()
    assert config_fee['events'] == [
        [signature.hex(), 20000,
         (('0x96C42C56fdb78294F96B0cFa33c92bed7D75F96a', 2000), ('0x97e9fA3b2AeA5aa56376a5FB5Cbf153ae91b0660', 8000))],
        [hex_32bytes, 100000,
         (('0xA904540818AC9c47f2321F97F1069B9d8746c6DB', 7000), ('0x316b2Fa7C8a2ab7E21110a4B3f58771C01A71344', 3000))]
    ]
    assert configuration.configAddresses(0) == accounts[0]


def test_add_config_success_normal(configuration, core_agent):
    gas = [14001, 14002, 24003, 24004, 24005]
    rewards = [
        [[accounts[1], 2000], [accounts[6], 2000], [accounts[1], 2000], [accounts[2], 2000], [accounts[1], 2000]],
        [[accounts[2], 1000], [accounts[7], 1000], [accounts[1], 1000], [accounts[2], 6000], [accounts[3], 1000]],
        [[accounts[3], 3000], [accounts[8], 3000], [accounts[1], 3000], [accounts[1], 500], [accounts[2], 500]],
        [[accounts[4], 3000], [accounts[9], 1000], [accounts[1], 5000], [accounts[2], 500], [accounts[3], 500]],
        [[accounts[5], 3000], [accounts[10], 2000], [accounts[1], 3000], [accounts[1], 1500], [accounts[4], 500]]
    ]
    event_prototype = ["Transfer(address,address,uint256)", "Transfer1(address,address,uint256)",
                       "Transfer2(address,address,uint256)", "Transfer3(address,address,uint256)",
                       "Transfer4(address,address,uint256)"]

    events = []
    events_result = []
    for index, i in enumerate(gas):
        events.append(set_event(rewards[index], event_prototype[index], i))
        is_bytes = False
        event_name = Web3.keccak(text=event_prototype[index])
        events_result.append([event_name.hex(), i, set_event(rewards[index], event_prototype[index], i, is_bytes)[0]])
    functions = []
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        functions
    ]
    value_encode = rlp.encode(value)
    configuration.updateParam('addConfig', value_encode)
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['configAddress'] == accounts[0]
    assert config_fee['isActive']
    assert config_fee['events'] == events_result


@pytest.mark.parametrize("length", [0, 1, 2, 4, 5, 6])
def test_add_config_invalid_length(configuration, length):
    value = [i for i in range(length)]
    value_encode = rlp.encode(value)
    with brownie.reverts("MismatchParamLength: addConfig"):
        configuration.updateParam('addConfig', value_encode)


def test_invalid_parameter_format(configuration):
    value = to_bytes(hexstr=accounts[0].address).hex()
    with brownie.reverts():
        configuration.updateParam('addConfig', value)


@pytest.mark.parametrize("events", [
    1, [1], [[1]], [[[ZERO_ADDRESS]]], [[[[ZERO_ADDRESS]]]]
])
def test_events_invalid_format(configuration, events):
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode)


def test_invalid_contract_address_format(configuration):
    value = [
        'test1',
        [],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode)


def test_contract_address_already_exists(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [
                [
                    [to_bytes(hexstr=accounts[3].address), 7000],
                    [to_bytes(hexstr=accounts[4].address), 3000]
                ],
                'btcExpired',
                100000
            ]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    tx = configuration.updateParam('addConfig', value_encode)
    assert 'ConfigUpdated' in tx.events
    with brownie.reverts(f"AddressAlreadyExists: 0x9fb29aac15b9a4b7f17c3385939b007540f4d791"):
        configuration.updateParam('addConfig', value_encode)


def test_events_length_zero(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts(f"ZeroEvents: "):
        configuration.updateParam('addConfig', value_encode)


@pytest.mark.parametrize("events_length", [3, 4, 5])
def test_events_length_exceeds_max(configuration, events_length):
    bytes_length = 64
    event = [
        [[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 100000
    ]
    events = []
    for i in range(events_length):
        events.append(event)
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    max_events = 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(max_events), bytes_length))
    configuration.updateParam('updateMaxEvents', padding_value)
    with brownie.reverts(f"TooManyEvents: "):
        configuration.updateParam('addConfig', value_encode)


def test_ratio_exceeds_maximum(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [[[to_bytes(hexstr=accounts[3].address), 4000], [to_bytes(hexstr=accounts[3].address), 2000],
              [to_bytes(hexstr=accounts[3].address), 2000], [to_bytes(hexstr=accounts[3].address), 1000],
              [to_bytes(hexstr=accounts[3].address), 500], [to_bytes(hexstr=accounts[3].address), 500]],
             'transfer', 100000]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts(f"TooManyRewardAddresses: "):
        configuration.updateParam('addConfig', value_encode)


@pytest.mark.parametrize("percentages", [2000, 9998, 9999, 10001, 10002])
def test_ratio_must_equal_10000(configuration, percentages):
    avg = percentages // 3
    percentage1 = avg
    percentage2 = avg
    percentage3 = percentages - percentage1 - percentage2
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [[[to_bytes(hexstr=accounts[3].address), percentage1], [to_bytes(hexstr=accounts[3].address), percentage2],
              [to_bytes(hexstr=accounts[3].address), percentage3]],
             'transfer', 100000]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    bytes_length = 64
    max_events = 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(max_events), bytes_length))
    configuration.updateParam('updateMaxEvents', padding_value)
    with brownie.reverts(f"InvalidRewardPercentage: {percentages}"):
        configuration.updateParam('addConfig', value_encode)


@pytest.mark.parametrize("gas", [[0, 1000001], [1, 1000002], [2, 1000003], [3, 1000003]])
def test_gas_exceeds_maximum(configuration, gas):
    events = [
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 6000], [to_bytes(hexstr=accounts[3].address), 4000]], 'transfer',
         1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
    ]
    events[gas[0]][-1] = gas[1]
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts(f"InvalidGasValue: {gas[1]}"):
        configuration.updateParam('addConfig', value_encode)


def test_rewards_invalid_format(configuration):
    event1 = [[['test1', 10000]], 'transfer', 100000]
    event2 = [[[to_bytes(hexstr=accounts[3].address), 'transfertransfertransfertransfertransfer']], 'transfer', 100000]
    value1 = [
        to_bytes(hexstr=accounts[0].address),
        [event1],
        1000
    ]
    value_encode1 = rlp.encode(value1)
    value2 = [
        to_bytes(hexstr=accounts[0].address),
        [event2],
        1000
    ]
    value_encode2 = rlp.encode(value2)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode1)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode2)


@pytest.mark.parametrize("is_multiple_data", [True, False])
@pytest.mark.parametrize("event", [
    [[[]], 'transfer', 100000],
    [[[to_bytes(hexstr=ZERO_ADDRESS)]]],
    [[[10000]]],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]]],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]], 100000],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]], 'transfer']])
def test_add_config_governance_invalid_parameter(configuration, event, is_multiple_data):
    events = [[[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000]]
    if is_multiple_data:
        events.append(event)
    else:
        events = [event]
    value1 = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode1 = rlp.encode(value1)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode1)


def test_add_config_multiple_times(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [
                [[to_bytes(hexstr=accounts[2].address), 5000], [to_bytes(hexstr=accounts[3].address), 5000]],
                'transfer', 100000
            ]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    configuration.updateParam('addConfig', value_encode)
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['configAddress'] == accounts[0]
    value[0] = to_bytes(hexstr=accounts[1].address)
    value_encode = rlp.encode(value)
    configuration.updateParam('addConfig', value_encode)
    config_fee = configuration.getConfig(accounts[1])
    assert config_fee['configAddress'] == accounts[1]


def test_add_config_rewards_empty(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [
                [],
                'transfer', 100000
            ]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts("InvalidRewardPercentage: 0"):
        configuration.updateParam('addConfig', value_encode)


def test_add_config_address_data_empty(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [
                [[], []],
                'transfer', 100000
            ]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts():
        configuration.updateParam('addConfig', value_encode)


def address2_bytes(account):
    bytes_value = to_bytes(hexstr=account.address)
    return bytes_value


def list2_elp_encode(array):
    return rlp.encode(array)


def uint2_bytes(value, bytes_length=64):
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    return padding_value


def test_add_config_after_deletion(configuration):
    value = [
        to_bytes(hexstr=accounts[2].address),
        [
            set_event([[accounts[1], 2000], [accounts[6], 8000]], 'transfer', 100000)
        ],
        []
    ]
    configuration.updateParam('addConfig', list2_elp_encode(value))
    configuration.updateParam('removeConfig', to_bytes(hexstr=accounts[2].address))
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['configAddress'] == ZERO_ADDRESS
    configuration.updateParam('addConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['configAddress'] == accounts[2]


def test_execute_add_config_success(configuration, system_reward, gov_hub):
    events = [
        [
            [
                [Web3.to_bytes(hexstr="0x1ef01E76f1aad50144A32680f16Aa97a10f8aF95"), 4000],
                [Web3.to_bytes(hexstr="0x8883fadb3538111e9522b34C36838d40FE42dEc7"), 6000]
            ],
            Web3.keccak(text="Transfer(address,address,uint256)"),
            1000000
        ],
        [
            [[Web3.to_bytes(hexstr="0x4e8cc1720Be51D15ac6e63fdEb656EA8993c25Fc"), 10000]],
            Web3.keccak(text="Approval(address,address,uint256)"),
            50000
        ]

    ]
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        []
    ]
    update_system_contract_address(configuration, gov_hub=gov_hub)
    execute_proposal(
        configuration.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['addConfig', list2_elp_encode(value)]),
        "add config success"
    )

    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['events'][0] == [Web3.keccak(text="Transfer(address,address,uint256)").hex(), 1000000,
                                       [['0x1ef01E76f1aad50144A32680f16Aa97a10f8aF95', 4000],
                                        ['0x8883fadb3538111e9522b34C36838d40FE42dEc7', 6000]]]
    assert len(config_fee['functions']) == 0
    function = [
        [[[to_bytes(hexstr=accounts[2].address), 6000], [to_bytes(hexstr=accounts[3].address), 4000]],
         Web3.keccak(text="transfer"),
         100000]]
    value[-2] = function
    update_system_contract_address(configuration, gov_hub=gov_hub)
    execute_proposal(
        configuration.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['updateConfig', list2_elp_encode(value)]),
        "update addWhiteList1"
    )
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['events'][0] == [Web3.keccak(text="transfer").hex(), 100000,
                                       [[accounts[2].address, 6000], [accounts[3].address, 4000]
                                        ]
                                       ]


def test_governance_after_limit_with_excess_events(configuration):
    _add_config(accounts[2])
    maximum_reward = 10
    bytes_length = 64
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(maximum_reward), bytes_length))
    configuration.updateParam('updateMaxEvents', padding_value)
    events = [
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 6000], [to_bytes(hexstr=accounts[3].address), 4000]], 'transfer',
         1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000]
    ]
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        []
    ]
    tx = configuration.updateParam('addConfig', list2_elp_encode(value))
    assert tx.events['ConfigUpdated']['eventCount'] == len(events)


def test_total_configurations_no_limit(configuration):
    bytes_length = 64
    maximum_reward = 10
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(maximum_reward), bytes_length))
    configuration.updateParam('updateMaxEvents', padding_value)
    events = [
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000]
    ]
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        []
    ]
    for account in accounts[:20]:
        value[0] = to_bytes(hexstr=account.address)
        tx = configuration.updateParam('addConfig', list2_elp_encode(value))
        assert 'ConfigUpdated' in tx.events


def test_remove_success(configuration):
    _add_config(accounts[4])
    assert len(configuration.getAllConfigAddresses()) == 1
    assert configuration.getAllConfigAddresses() == [accounts[4]]
    tx = configuration.updateParam('removeConfig', address2_bytes(accounts[4]))
    assert 'ConfigRemoved' in tx.events
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['configAddress'] == ZERO_ADDRESS
    assert config_fee['isActive'] is False
    assert len(config_fee['events']) == 0
    assert len(config_fee['functions']) == 0
    assert len(configuration.getAllConfigAddresses()) == 0


def test_remove_multiple_addresses_success(configuration):
    _add_config(accounts[4])
    _add_config(accounts[5])
    _add_config(accounts[6])
    configuration.updateParam('removeConfig', address2_bytes(accounts[4]))
    config_fee = configuration.getConfig(accounts[4])
    assert config_fee['configAddress'] == ZERO_ADDRESS
    assert configuration.getAllConfigAddresses() == [accounts[6], accounts[5]]
    _add_config(accounts[7])
    _add_config(accounts[8])
    configuration.updateParam('removeConfig', address2_bytes(accounts[8]))
    assert configuration.getAllConfigAddresses() == [accounts[6], accounts[5], accounts[7]]
    _add_config(accounts[8])
    configuration.updateParam('removeConfig', address2_bytes(accounts[7]))
    assert configuration.getAllConfigAddresses() == [accounts[6], accounts[5], accounts[8]]
    _add_config(accounts[9])
    assert configuration.getAllConfigAddresses() == [accounts[6], accounts[5], accounts[8], accounts[9]]
    configuration.updateParam('removeConfig', address2_bytes(accounts[6]))
    config_array = [accounts[9], accounts[5], accounts[8]]
    assert configuration.getAllConfigAddresses() == config_array
    for ca in config_array:
        assert configuration.getConfig(ca)['configAddress'] == ca
    assert configuration.getConfig(accounts[7])['configAddress'] == ZERO_ADDRESS
    assert configuration.getConfig(accounts[6])['configAddress'] == ZERO_ADDRESS


def test_remove_invalid_parameter_format(configuration):
    _add_config(accounts[4])
    with brownie.reverts():
        configuration.updateParam('removeConfig', 1000)


def test_remove_nonexistent_contract_address(configuration):
    _add_config(accounts[4])
    with brownie.reverts(f'AddressNotFound: 0xc40e52501d9969b6788c173c1ca6b23de6f3392d'):
        configuration.updateParam('removeConfig', address2_bytes(accounts[6]))


def test_remove_invalid_length_format(configuration):
    _add_config(accounts[4])
    with brownie.reverts(f'MismatchParamLength: removeConfig'):
        configuration.updateParam('removeConfig', '0x123456')


def test_remove_invalid_address_format(configuration):
    _add_config(accounts[4])
    remove_address = [accounts[4].address]
    with brownie.reverts():
        configuration.updateParam('removeConfig', list2_elp_encode(remove_address))


def test_remove_after_repeated_additions(configuration):
    _add_config(accounts[4])
    remove_address: bytes = address2_bytes(accounts[4])
    configuration.updateParam('removeConfig', remove_address)
    _add_config(accounts[4])
    tx = configuration.updateParam('removeConfig', remove_address)
    assert 'ConfigRemoved' in tx.events
    with brownie.reverts():
        configuration.updateParam('removeConfig', remove_address)


def test_update_config_success(configuration):
    _add_config(accounts[2])
    gas = [50000]
    rewards = [
        [[accounts[1], 1000], [accounts[2], 2000], [accounts[3], 3000], [accounts[4], 4000]]
    ]
    event_prototype = ["Transfer11(address,address,uint256)"]
    events_result = []
    events = []
    for index, i in enumerate(gas):
        events.append(set_event(rewards[index], event_prototype[index], i))
        is_bytes = False
        event_name = Web3.keccak(text=event_prototype[index])
        events_result.append([event_name.hex(), i, set_event(rewards[index], event_prototype[index], i, is_bytes)[0]])
    value = [
        to_bytes(hexstr=accounts[2].address),
        events,
        []
    ]
    config_fee = configuration.getConfig(accounts[2])
    assert len(config_fee['events']) == 2
    tx = configuration.updateParam('updateConfig', list2_elp_encode(value))
    assert 'ConfigUpdated' in tx.events
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['configAddress'] == accounts[2]
    assert config_fee['isActive']
    assert config_fee['events'][0] == [Web3.keccak(text=event_prototype[0]).hex(), gas[0],
                                       [[accounts[1].address, 1000], [accounts[2].address, 2000],
                                        [accounts[3].address, 3000],
                                        [accounts[4].address, 4000]]]

    assert len(config_fee['events']) == 1


def test_update_five_configs_success(configuration):
    gas = [14001, 14002, 24003, 24004, 24005]
    rewards = [
        [[accounts[1], 2000], [accounts[6], 2000], [accounts[1], 2000], [accounts[2], 2000], [accounts[1], 2000]],
        [[accounts[2], 1000], [accounts[7], 1000], [accounts[1], 1000], [accounts[2], 6000], [accounts[3], 1000]],
        [[accounts[3], 3000], [accounts[8], 3000], [accounts[1], 3000], [accounts[1], 500], [accounts[2], 500]],
        [[accounts[4], 3000], [accounts[9], 1000], [accounts[1], 5000], [accounts[2], 500], [accounts[3], 500]],
        [[accounts[5], 3000], [accounts[10], 2000], [accounts[1], 3000], [accounts[1], 1500], [accounts[4], 500]]
    ]
    event_prototype = ["Transfer(address,address,uint256)", "Transfer1(address,address,uint256)",
                       "Transfer2(address,address,uint256)", "Transfer3(address,address,uint256)",
                       "Transfer4(address,address,uint256)"]
    events = []
    events_result = []
    for index, i in enumerate(gas):
        events.append(set_event(rewards[index], event_prototype[index], i))
        is_bytes = False
        event_name = Web3.keccak(text=event_prototype[index])
        events_result.append(
            [event_name.hex(), i, set_event(rewards[index], event_prototype[index], i, is_bytes)[0]])
    functions = []
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        functions
    ]
    value_encode = rlp.encode(value)
    configuration.updateParam('addConfig', value_encode)
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['events'] == events_result
    assert len(config_fee['events']) == 5

    gas1 = [20001, 20002, 20003, 20004, 20005]
    rewards1 = [
        [[accounts[2], 1000], [accounts[1], 3000], [accounts[2], 1000], [accounts[1], 3000], [accounts[1], 2000]],
        [[accounts[3], 1000], [accounts[2], 0], [accounts[2], 1000], [accounts[1], 7000], [accounts[3], 1000]],
        [[accounts[4], 3000], [accounts[3], 5000], [accounts[2], 1000], [accounts[2], 500], [accounts[2], 500]],
        [[accounts[5], 5000], [accounts[4], 1000], [accounts[2], 3000], [accounts[3], 500], [accounts[5], 500]],
        [[accounts[6], 4000], [accounts[5], 2000], [accounts[2], 2000], [accounts[4], 500], [accounts[6], 1500]]
    ]
    event_prototype1 = ["update_Transfer(address,address,uint256)", "update_Transfer1(address,address,uint256)",
                        "update_Transfer2(address,address,uint256)", "update_Transfer3(address,address,uint256)",
                        "update_Transfer4(address,address,uint256)"]
    events = []
    events_result = []
    for index, i in enumerate(gas1):
        events.append(set_event(rewards1[index], event_prototype1[index], i))
        is_bytes = False
        event_name = Web3.keccak(text=event_prototype1[index])
        events_result.append(
            [event_name.hex(), i, set_event(rewards1[index], event_prototype1[index], i, is_bytes)[0]])
    functions = []
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        functions
    ]
    configuration.updateParam('updateConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['events'] == events_result
    assert len(config_fee['events']) == 5
    value = [
        to_bytes(hexstr=accounts[0].address),
        events[:4],
        functions
    ]
    configuration.updateParam('updateConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['events'] == events_result[:4]
    assert len(config_fee['events']) == 4


@pytest.mark.parametrize("length", [0, 1, 2, 4, 5, 6])
def test_update_config_invalid_length(configuration, length):
    value = [i for i in range(length)]
    value_encode = rlp.encode(value)
    with brownie.reverts("MismatchParamLength: updateConfig"):
        configuration.updateParam('updateConfig', value_encode)


def test_update_invalid_parameter_format(configuration):
    value = to_bytes(hexstr=accounts[0].address).hex()
    with brownie.reverts():
        configuration.updateParam('updateConfig', value)


@pytest.mark.parametrize("events", [
    1, [1], [[1]], [[[ZERO_ADDRESS]]], [[[[ZERO_ADDRESS]]]]
])
def test_update_events_invalid_format(configuration, events):
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts():
        configuration.updateParam('updateConfig', value_encode)


def test_update_invalid_contract_address_format(configuration):
    value = [
        'test1',
        [],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts():
        configuration.updateParam('updateConfig', value_encode)


def test_update_nonexistent_contract_address(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [[[
            [to_bytes(hexstr=accounts[3].address), 7000],
            [to_bytes(hexstr=accounts[4].address), 3000]],
            'btcExpired',
            100000]], 1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts("AddressNotFound: 0x9fb29aac15b9a4b7f17c3385939b007540f4d791"):
        configuration.updateParam('updateConfig', value_encode)


def test_update_events_zero_length_success(configuration):
    _add_config(accounts[0])
    value = [
        to_bytes(hexstr=accounts[0].address),
        [],
        1000
    ]
    value_encode = rlp.encode(value)
    with brownie.reverts('ZeroEvents: '):
        configuration.updateParam('updateConfig', value_encode)


@pytest.mark.parametrize("events_length", [3, 4, 5])
def test_update_events_exceed_max_length(configuration, events_length):
    event = [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 100000]
    events = []
    for i in range(events_length):
        events.append(event)
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    bytes_length = 64
    max_events = 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(max_events), bytes_length))
    _add_config(accounts[0])
    configuration.updateParam('updateMaxEvents', padding_value)
    with brownie.reverts(f"TooManyEvents: "):
        configuration.updateParam('updateConfig', value_encode)


@pytest.mark.xfail
def test_update_reward_exceeds_maximum(configuration):
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [[[to_bytes(hexstr=accounts[3].address), 8000], [to_bytes(hexstr=accounts[3].address), 2000]],
             'transfer1', 10000],
            [[[to_bytes(hexstr=accounts[3].address), 8000], [to_bytes(hexstr=accounts[3].address), 2000],
              ],
             'transfer2', 10000],
            [[[to_bytes(hexstr=accounts[3].address), 4000], [to_bytes(hexstr=accounts[3].address), 1000],
              [to_bytes(hexstr=accounts[3].address), 2000], [to_bytes(hexstr=accounts[3].address), 1000]],
             'transfer3', 10000]
        ],
        []
    ]
    value_encode = list2_elp_encode(value)
    _add_config(accounts[0])
    configuration.updateParam('updatedMaximumRewardAddress', list2_elp_encode([2]))
    configuration.updateParam('updateConfig', value_encode)


@pytest.mark.parametrize("percentages", [2000, 9998, 9999, 10001, 10002])
def test_update_ratio_must_equal_10000(configuration, percentages):
    avg = percentages // 3
    percentage1 = avg
    percentage2 = avg
    percentage3 = percentages - percentage1 - percentage2
    value = [
        to_bytes(hexstr=accounts[0].address),
        [
            [[[to_bytes(hexstr=accounts[3].address), percentage1], [to_bytes(hexstr=accounts[3].address), percentage2],
              [to_bytes(hexstr=accounts[3].address), percentage3]],
             'transfer', 100000]
        ],
        1000
    ]
    value_encode = rlp.encode(value)
    max_events = 2
    _add_config(accounts[0])
    configuration.updateParam('updateMaxEvents', uint2_bytes(max_events))
    with brownie.reverts(f"InvalidRewardPercentage: {percentages}"):
        configuration.updateParam('updateConfig', value_encode)


@pytest.mark.parametrize("gas", [[0, 1000001], [1, 1000002], [2, 1000003], [3, 1000003]])
def test_update_gas_exceeds_maximum(configuration, gas):
    events = [
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 6000], [to_bytes(hexstr=accounts[3].address), 4000]], 'transfer',
         1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
        [[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000],
    ]
    events[gas[0]][-1] = gas[1]
    value = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode = rlp.encode(value)
    _add_config(accounts[0])
    with brownie.reverts(f"InvalidGasValue: {gas[1]}"):
        configuration.updateParam('updateConfig', value_encode)


def test_update_events_reward_invalid_format(configuration):
    event1 = [[['test1', 10000]], 'transfer', 100000]
    event2 = [[[to_bytes(hexstr=accounts[3].address), 'transfertransfertransfertransfertransfer']], 'transfer', 100000]
    value1 = [
        to_bytes(hexstr=accounts[0].address),
        [event1],
        1000
    ]
    value_encode1 = rlp.encode(value1)
    value2 = [
        to_bytes(hexstr=accounts[0].address),
        [event2],
        1000
    ]
    value_encode2 = rlp.encode(value2)
    _add_config(accounts[0])
    with brownie.reverts():
        configuration.updateParam('updateConfig', value_encode1)
    with brownie.reverts():
        configuration.updateParam('updateConfig', value_encode2)


@pytest.mark.parametrize("is_multiple_data", [True, False])
@pytest.mark.parametrize("event", [
    [[[]], 'transfer', 100000],
    [[[to_bytes(hexstr=ZERO_ADDRESS)]]],
    [[[10000]]],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]]],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]], 100000],
    [[[to_bytes(hexstr=ZERO_ADDRESS), 10000]], 'transfer']])
def test_update_config_governance_invalid_parameter(configuration, event, is_multiple_data):
    events = [[[[to_bytes(hexstr=accounts[3].address), 10000]], 'transfer', 1000000]]
    if is_multiple_data:
        events.append(event)
    else:
        events = [event]
    value1 = [
        to_bytes(hexstr=accounts[0].address),
        events,
        1000
    ]
    value_encode1 = rlp.encode(value1)
    with brownie.reverts():
        configuration.updateParam('updateConfig', value_encode1)


def test_update_config_multiple_times(configuration):
    _add_config(accounts[1])
    value = [
        to_bytes(hexstr=accounts[1].address),
        [[[[to_bytes(hexstr=accounts[2].address), 5000], [to_bytes(hexstr=accounts[3].address), 5000]], 'transfer',
          100000]
         ],
        []
    ]
    value_encode = rlp.encode(value)
    configuration.updateParam('updateConfig', value_encode)
    config_fee = configuration.getConfig(accounts[1])
    assert config_fee['events'][0]['gas'] == 100000
    configuration.updateParam('updateConfig', value_encode)
    assert config_fee['events'][0]['gas'] == 100000
    value[1][0][-1] = 5000
    configuration.updateParam('updateConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[1])
    assert config_fee['events'][0]['gas'] == 5000


def test_update_after_readding_deleted_config(configuration):
    value = [
        to_bytes(hexstr=accounts[4].address),
        [[[[to_bytes(hexstr=accounts[2].address), 5000], [to_bytes(hexstr=accounts[3].address), 5000]], 'transfer',
          100000]
         ],
        []
    ]
    _add_config(accounts[4])
    remove_address = address2_bytes(accounts[4])
    configuration.updateParam('removeConfig', remove_address)
    with brownie.reverts('AddressNotFound: 0x316b2fa7c8a2ab7e21110a4b3f58771c01a71344'):
        configuration.updateParam('updateConfig', list2_elp_encode(value))
    _add_config(accounts[4])
    configuration.updateParam('updateConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[4])
    assert len(config_fee['events']) == 1


def test_add_config_function(configuration):
    function = [
        [[[to_bytes(hexstr=accounts[2].address), 5000], [to_bytes(hexstr=accounts[3].address), 5000]], 'transfer',
         100000]]
    value = [
        to_bytes(hexstr=accounts[0].address),
        function,
        function
    ]
    configuration.updateParam('addConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[0])
    assert len(config_fee['functions']) == 0
    function = [
        [[[to_bytes(hexstr=accounts[2].address), 6000], [to_bytes(hexstr=accounts[3].address), 4000]], 'transfer',
         100000]]
    value[-1] = function
    configuration.updateParam('updateConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[0])
    assert len(config_fee['functions']) == 0


def test_update_function_and_events(configuration):
    function = [
        [[[to_bytes(hexstr=accounts[2].address), 5000], [to_bytes(hexstr=accounts[3].address), 5000]], 'transfer',
         100000]]
    value = [
        to_bytes(hexstr=accounts[0].address),
        function,
        function
    ]
    configuration.updateParam('addConfig', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[0])
    assert len(config_fee['functions']) == 0


def test_add_function_and_events_success(configuration):
    event2 = (
        Web3.keccak(text="EventName2(bool)").hex(),
        30000,
        [[accounts[1].address, 4000], [accounts[2].address, 6000]]
    )
    function1 = (
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [[accounts[0], 3000], [accounts[1], 3000], [accounts[2], 5000]]
    )
    configuration.addConfigMock(accounts[0].address, [event2], [function1], False)
    config_fee = configuration.getConfig(accounts[0])
    assert config_fee['isActive'] is False
    assert config_fee['events'] == [event2]
    assert config_fee['functions'] == [function1]


def test_update_function_and_events_success(configuration):
    _add_config(accounts[2])
    event2 = (
        Web3.keccak(text="EventName2(bool)").hex(),
        30000,
        [[accounts[1].address, 4000], [accounts[2].address, 6000]]
    )
    function1 = (
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [[accounts[0], 3000], [accounts[1], 3000], [accounts[2], 5000]]
    )

    configuration.updateConfigMock(accounts[2].address, [event2], [function1])
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['events'] == [event2]
    assert config_fee['functions'] == [function1]


def test_functions_length_exceeds_max(configuration):
    _add_config(accounts[2])
    event2 = (
        Web3.keccak(text="EventName2(bool)").hex(),
        30000,
        [[accounts[1].address, 4000], [accounts[2].address, 6000]]
    )
    function1 = (
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [
            [accounts[0], 3000], [accounts[1], 3000], [accounts[2], 5000]
        ]
    )
    functions = [function1, function1, function1, function1, function1, function1]
    with brownie.reverts('TooManyFunctionSigs: '):
        configuration.addConfigMock(accounts[0].address, [event2], functions, False)
    with brownie.reverts('TooManyFunctionSigs: '):
        configuration.updateConfigMock(accounts[2].address, [event2], functions)


def test_update_config_status_success(configuration):
    _add_config(accounts[2])
    tx = configuration.updateParam('setConfigStatus', list2_elp_encode([address2_bytes(accounts[2]), 0]))
    assert tx.events['ConfigUpdated']['configAddress'] == accounts[2]
    assert tx.events['ConfigUpdated']['eventCount'] == 0
    assert 'ConfigUpdated' in tx.events
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['isActive'] is False


@pytest.mark.parametrize("length", [0, 1, 3, 4, 5, 6])
def test_update_config_status_invalid_length(configuration, length):
    _add_config(accounts[2])
    value = [i for i in range(length)]
    with brownie.reverts(f"MismatchParamLength: setConfigStatus"):
        configuration.updateParam('setConfigStatus', list2_elp_encode(value))


def test_update_config_status_invalid_parameter(configuration):
    _add_config(accounts[2])
    with brownie.reverts():
        configuration.updateParam('setConfigStatus', '0x12345')


def test_update_config_status_invalid_address_format(configuration):
    _add_config(accounts[2])
    value = ['test', 0]
    with brownie.reverts():
        configuration.updateParam('setConfigStatus', list2_elp_encode(value))


def test_update_config_status_invalid_state_format(configuration):
    _add_config(accounts[2])
    value = [address2_bytes(accounts[2]), 'test']
    with brownie.reverts():
        configuration.updateParam('setConfigStatus', list2_elp_encode(value))


def test_update_config_status_nonexistent_address(configuration):
    _add_config(accounts[2])
    value = [address2_bytes(accounts[1]), 1]
    with brownie.reverts('AddressNotFound: 0x96c42c56fdb78294f96b0cfa33c92bed7d75f96a'):
        configuration.updateParam('setConfigStatus', list2_elp_encode(value))


def test_update_config_status_repeated(configuration):
    _add_config(accounts[2])
    value = [address2_bytes(accounts[2]), 0]
    configuration.updateParam('setConfigStatus', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['isActive'] is False
    configuration.updateParam('setConfigStatus', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['isActive'] is False
    value[-1] = 1
    configuration.updateParam('setConfigStatus', list2_elp_encode(value))
    config_fee = configuration.getConfig(accounts[2])
    assert config_fee['isActive']


@pytest.mark.parametrize("value", [1, 50, 99, 101, 255])
def test_updated_maximum_reward_address_success(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    configuration.updateParam('updatedMaximumRewardAddress', padding_value)
    assert configuration.MAX_REWARDS() == value


@pytest.mark.parametrize("value", [0, 256, 257, 1000, 20000])
def test_updated_maximum_reward_address_failed(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    with brownie.reverts(f"OutOfBounds: updatedMaximumRewardAddress, {value}, 1, 255"):
        configuration.updateParam('updatedMaximumRewardAddress', padding_value)


def test_updated_maximum_reward_address_invalid_length(configuration):
    bytes_length = 64
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(20), bytes_length - 2))
    with brownie.reverts('MismatchParamLength: updatedMaximumRewardAddress'):
        configuration.updateParam('updatedMaximumRewardAddress', padding_value)


def test_updated_maximum_reward_address_invalid_format(configuration):
    value = '0x1234'
    with brownie.reverts():
        configuration.updateParam('updatedMaximumRewardAddress', value)


@pytest.mark.parametrize("value", [1, 50, 99, 101, 255])
def test_update_max_events_success(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    configuration.updateParam('updateMaxEvents', padding_value)
    assert configuration.MAX_EVENTS() == value


@pytest.mark.parametrize("value", [0, 256, 257, 1000])
def test_update_max_events_failed(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    with brownie.reverts(f"OutOfBounds: updateMaxEvents, {value}, 1, 255"):
        configuration.updateParam('updateMaxEvents', padding_value)


def test_update_max_events_invalid_length(configuration):
    bytes_length = 64
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(1), bytes_length - 2))
    with brownie.reverts('MismatchParamLength: updateMaxEvents'):
        configuration.updateParam('updateMaxEvents', padding_value)


def test_update_max_events_invalid_format(configuration):
    value = '0x1234'
    with brownie.reverts():
        configuration.updateParam('updateMaxEvents', value)


@pytest.mark.parametrize("value", [1, 101, 256, 1000, 2 ** 32 - 1])
def test_update_max_gas_success(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    configuration.updateParam('updateMaxGas', padding_value)
    assert configuration.MAX_GAS() == value


@pytest.mark.parametrize("value", [0, 2 ** 32, 2 ** 32 + 1])
def test_update_max_gas_failed(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    with brownie.reverts(f"OutOfBounds: updateMaxGas, {value}, 1, {2 ** 32 - 1}"):
        configuration.updateParam('updateMaxGas', padding_value)


def test_update_max_gas_invalid_length(configuration):
    bytes_length = 64
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(1), bytes_length - 2))
    with brownie.reverts('MismatchParamLength: updateMaxGas'):
        configuration.updateParam('updateMaxGas', padding_value)


def test_update_max_gas_invalid_format(configuration):
    value = '0x1234'
    with brownie.reverts():
        configuration.updateParam('updateMaxGas', value)


@pytest.mark.parametrize("value", [1, 50, 99, 101, 2 ** 8 - 1])
def test_update_max_functions_success(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    configuration.updateParam('updateMaxFunctions', padding_value)
    assert configuration.MAX_FUNCTIONS() == value


@pytest.mark.parametrize("value", [0, 2 ** 8, 2 ** 8 + 1, 1000, 10001])
def test_update_max_functions_failed(configuration, value):
    bytes_length = 64
    _add_config(accounts[2])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(value), bytes_length))
    with brownie.reverts(f"OutOfBounds: updateMaxFunctions, {value}, 1, {2 ** 8 - 1}"):
        configuration.updateParam('updateMaxFunctions', padding_value)


def test_update_max_functions_invalid_length(configuration):
    bytes_length = 64
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(1), bytes_length - 2))
    with brownie.reverts('MismatchParamLength: updateMaxFunctions'):
        configuration.updateParam('updateMaxFunctions', padding_value)


def test_update_max_functions_invalid_format(configuration):
    value = '0x1234'
    with brownie.reverts():
        configuration.updateParam('updateMaxFunctions', value)


def test_config_exists(configuration):
    _add_config(accounts[2])
    assert configuration.configExists(accounts[2])


def test_config_not_exists(configuration):
    _add_config(accounts[2])
    assert configuration.configExists(accounts[1]) is False
    assert configuration.configExists(ZERO_ADDRESS) is False


def test_query_after_address_deletion(configuration):
    _add_config(accounts[2])
    assert configuration.configExists(accounts[2])
    configuration.updateParam('removeConfig', to_bytes(hexstr=accounts[2].address))
    assert configuration.configExists(accounts[2]) is False


def test_query_event_success(configuration):
    events_result = []
    gas = [14001, 14002]
    rewards = [
        [[accounts[1], 2000], [accounts[6], 2000], [accounts[1], 2000], [accounts[2], 2000], [accounts[1], 2000]],
        [[accounts[2], 1000], [accounts[7], 1000], [accounts[1], 1000], [accounts[2], 6000], [accounts[3], 1000]]
    ]
    event_prototype = ["Transfer(address,address,uint256)", "Transfer1(address,address,uint256)"]
    for index, i in enumerate(gas):
        is_bytes = False
        event_name = Web3.keccak(text=event_prototype[index])
        events_result.append([event_name.hex(), i, set_event(rewards[index], event_prototype[index], i, is_bytes)[0]])
    _add_config(accounts[2])
    event_details = configuration.getEventDetails(accounts[2], 0)
    assert event_details == events_result[0]
    event_details = configuration.getEventDetails(accounts[2], 1)
    assert event_details == events_result[1]
    with brownie.reverts(f"Function index out of bounds"):
        configuration.getFunctionDetails(accounts[2], 0)


def test_query_nonexistent_event(configuration):
    _add_config(accounts[2])
    with brownie.reverts(f"Event index out of bounds"):
        configuration.getEventDetails(accounts[2], 3)
    with brownie.reverts(f"Event index out of bounds"):
        configuration.getEventDetails(accounts[3], 0)


def test_query_event_after_deletion(configuration):
    gas = 14001
    _add_config(accounts[2])
    event_details = configuration.getEventDetails(accounts[2], 0)
    assert event_details[1] == gas
    configuration.updateParam('removeConfig', to_bytes(hexstr=accounts[2].address))
    with brownie.reverts(f"Event index out of bounds"):
        configuration.getEventDetails(accounts[2], 0)


def test_get_function_success(configuration):
    event = [
        Web3.keccak(text="EventName2(bool)").hex(),
        30000,
        [[accounts[1].address, 4000], [accounts[2].address, 6000]]
    ]
    events = [event]
    event[1] = 20000
    function = [
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [[accounts[0], 3000], [accounts[1], 3000], [accounts[2], 5000]]
    ]
    functions = [function, event]
    configuration.addConfigMock(accounts[0].address, events, functions, False)
    function_details0 = configuration.getFunctionDetails(accounts[0], 0)
    function_details1 = configuration.getFunctionDetails(accounts[0], 1)
    assert function_details0 == functions[0]
    assert function_details1 == functions[1]
    with brownie.reverts(f"Event index out of bounds"):
        configuration.getEventDetails(accounts[0], 1)


def test_get_nonexistent_function(configuration):
    _add_config(accounts[2])
    function = [
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [[accounts[0], 3000], [accounts[1], 4000], [accounts[2], 3000]]
    ]
    configuration.updateConfigMock(accounts[2].address, [function], [function, function])
    assert configuration.getFunctionDetails(accounts[2], 0)
    assert configuration.getFunctionDetails(accounts[2], 1)
    with brownie.reverts(f"Function index out of bounds"):
        configuration.getFunctionDetails(accounts[2], 2)
    with brownie.reverts(f"Function index out of bounds"):
        configuration.getFunctionDetails(accounts[3], 0)


def test_get_function_after_deletion(configuration):
    _add_config(accounts[2])
    function = [
        Web3.keccak(text="FunctionName2(bool)").hex(),
        10000,
        [[accounts[0], 3000], [accounts[1], 4000], [accounts[2], 3000]]
    ]
    configuration.updateConfigMock(accounts[2].address, [function], [function, function])
    assert configuration.getFunctionDetails(accounts[2], 0)
    assert configuration.getFunctionDetails(accounts[2], 1)
    configuration.updateParam('removeConfig', to_bytes(hexstr=accounts[2].address))
    with brownie.reverts(f"Function index out of bounds"):
        configuration.getFunctionDetails(accounts[2], 0)


def _add_config(config_address, events=None):
    if events is None:
        gas = [14001, 14002]
        rewards = [
            [[accounts[1], 2000], [accounts[6], 2000], [accounts[1], 2000], [accounts[2], 2000], [accounts[1], 2000]],
            [[accounts[2], 1000], [accounts[7], 1000], [accounts[1], 1000], [accounts[2], 6000], [accounts[3], 1000]]
        ]
        event_prototype = ["Transfer(address,address,uint256)", "Transfer1(address,address,uint256)"]
        events = []
        for index, i in enumerate(gas):
            events.append(set_event(rewards[index], event_prototype[index], i))

    value = [
        to_bytes(hexstr=config_address.address),
        events,
        []
    ]
    update_system_contract_address(ConfigurationMock[0], gov_hub=accounts[0])
    tx = ConfigurationMock[0].updateParam('addConfig', list2_elp_encode(value))
    assert 'ConfigUpdated' in tx.events
    config_fee = ConfigurationMock[0].getConfig(config_address)
    assert config_fee['isActive']
