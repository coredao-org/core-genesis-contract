import pytest
import brownie
from web3 import Web3, constants
from eth_abi import encode_abi
from brownie import accounts, SelfDestroy
from .utils import expect_event, get_tracker, padding_left, encode_args_with_signature
from .common import execute_proposal


VALIDATOR_CONTRACT_ADDR = None
SLASH_CONTRACT_ADDR = None
SYSTEM_REWARD_ADDR = None
LIGHT_CLIENT_ADDR = None
RELAYER_HUB_ADDR = None
CANDIDATE_HUB_ADDR = None
GOV_HUB_ADDR = None
PLEDGE_AGENT_ADDR = None
BURN_ADDR = None
FOUNDATION_ADDR = None


@pytest.fixture(scope="module", autouse=True)
def set_up(validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub,
           gov_hub, pledge_agent, burn, foundation):
    global VALIDATOR_CONTRACT_ADDR
    global SLASH_CONTRACT_ADDR
    global SYSTEM_REWARD_ADDR
    global LIGHT_CLIENT_ADDR
    global RELAYER_HUB_ADDR
    global CANDIDATE_HUB_ADDR
    global GOV_HUB_ADDR
    global PLEDGE_AGENT_ADDR
    global BURN_ADDR
    global FOUNDATION_ADDR
    VALIDATOR_CONTRACT_ADDR = validator_set.address
    SLASH_CONTRACT_ADDR = slash_indicator.address
    SYSTEM_REWARD_ADDR = system_reward.address
    LIGHT_CLIENT_ADDR = btc_light_client.address
    RELAYER_HUB_ADDR = relay_hub.address
    CANDIDATE_HUB_ADDR = candidate_hub.address
    GOV_HUB_ADDR = gov_hub.address
    PLEDGE_AGENT_ADDR = pledge_agent.address
    BURN_ADDR = burn.address
    FOUNDATION_ADDR = foundation.address


def __update_gov_address(burn_instance):
    burn_instance.updateContractAddr(
        VALIDATOR_CONTRACT_ADDR,
        SLASH_CONTRACT_ADDR,
        SYSTEM_REWARD_ADDR,
        LIGHT_CLIENT_ADDR,
        RELAYER_HUB_ADDR,
        CANDIDATE_HUB_ADDR,
        accounts[0],
        PLEDGE_AGENT_ADDR,
        BURN_ADDR,
        FOUNDATION_ADDR,
    )


def __add_balance(address, value):
    c = SelfDestroy.deploy({'from': accounts[1]})
    accounts[1].transfer(c.address, value)
    c.destruct(address)


def test_update_param_failed_with_unknown_key(burn):
    __update_gov_address(burn)
    with brownie.reverts("unknown param"):
        burn.updateParam("unknown", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_burn_cap_with_unmatched_length(burn):
    __update_gov_address(burn)
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['burnCap'])
    with brownie.reverts(f"typed error: {error_msg}"):
        burn.updateParam("burnCap", "0x0000000000123")


def test_update_param_burn_cap_with_0(burn):
    __update_gov_address(burn)
    tx = burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000000000000000000")
    expect_event(tx, 'paramChange', {
        "key": "burnCap",
        "value": "0x0000000000000000000000000000000000000000000000000000000000000000"
    })


def test_update_param_burn_cap_with_value_which_is_less_than_burn_contract_balance(burn):
    __update_gov_address(burn)
    __add_balance(burn.address, Web3.toWei(1, 'ether'))

    new_burn_cap = "0x0000000000000000000000000000000000000000000000000de0b6b3a763fff"
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["burnCap", Web3.toInt(hexstr=new_burn_cap), burn.balance(), Web3.toInt(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"typed error: {error_msg}"):
        burn.updateParam("burnCap", new_burn_cap)


def test_update_param_burn_cap_success(burn):
    __update_gov_address(burn)
    __add_balance(burn.address, Web3.toWei(1, 'ether'))
    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640001")
    expect_event(tx, "paramChange", {
        "key": "burnCap",
        "value": "0x0000000000000000000000000000000000000000000000000de0b6b3a7640001"
    })

    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_value_0_and_balance_is_0(burn):
    tracker = get_tracker(accounts[0])
    tx = burn.burn()
    assert "burned" not in tx.events
    assert tracker.delta() == 0


def test_burn_success_with_value_0_and_balance_is_equal_to_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    __add_balance(burn.address, Web3.toWei(1, 'ether'))

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn()
    assert "burned" not in tx.events

    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_value_0_and_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    __add_balance(burn.address, Web3.toWei(2, 'ether'))

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn()
    assert "burned" not in tx.events
    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_1_ether_and_balance_is_0(burn):
    burn_value = Web3.toWei(1, 'ether')
    tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({'value': burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": burn_value})

    assert tracker.delta() == (0 - burn_value)
    assert burn_tracker.delta() == burn_value


def test_burn_success_with_value_1_and_balance_is_equal_to_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    burn_value = Web3.toWei(1, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({"value": burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": burn_value})

    assert account0_tracker.delta() == (0 - burn_value)
    assert burn_tracker.delta() == burn_value


def test_burn_failed_with_1_ether_due_to_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    __add_balance(burn.address, Web3.toWei(2, 'ether'))

    burn_value = Web3.toWei(1, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({'value': burn_value})
    assert "burned" not in tx.events

    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_half_of_2_ether_and_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")

    burn_value = Web3.toWei(2, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({"value": burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": Web3.toWei(1, 'ether')})

    assert account0_tracker.delta() == (0 - Web3.toWei(1, 'ether'))
    assert burn_tracker.delta() == Web3.toWei(1, 'ether')


def test_receive_ether(burn):
    with brownie.reverts():
        accounts[0].transfer(burn.address, Web3.toWei(1, 'ether'))


def test_receive_ether_through_destruct_command(burn):
    __add_balance(burn.address, 1)
    assert brownie.web3.eth.get_balance(burn.address) == 1


def test_modify_burn_cap(burn):
    new_cap = 200
    hex_value = padding_left(Web3.toHex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['burnCap', Web3.toBytes(hexstr=hex_value)]),
        "update burn cap"
    )
    assert burn.burnCap() == new_cap


def test_burn_less_than_cap(burn):
    new_cap = 100
    hex_value = padding_left(Web3.toHex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['burnCap', Web3.toBytes(hexstr=hex_value)]),
        "update burn cap"
    )

    burn.burn({'value': 90})
    tx = burn.burn({'value': 8})
    expect_event(tx, "burned", {
        "to": accounts[0],
        "amount": 8
    })
    assert brownie.web3.eth.get_balance(burn.address) == 98


def test_burn_greater_than_cap(burn):
    new_cap = 100
    hex_value = padding_left(Web3.toHex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['burnCap', Web3.toBytes(hexstr=hex_value)]),
        "update burn cap"
    )

    __add_balance(burn.address, 101)

    account0_tracker = get_tracker(accounts[0])
    tx = burn.burn({'value': 8})
    assert "burned" not in tx.events
    assert account0_tracker.delta() == 0
