import pytest
import brownie
from web3 import Web3, constants
from eth_abi import encode
from brownie import *
from .utils import expect_event, get_tracker, padding_left, encode_args_with_signature, update_system_contract_address
from .common import execute_proposal


@pytest.fixture(scope="module", autouse=True)
def set_up():
    pass


def __update_gov_address(burn):
    update_system_contract_address(burn, gov_hub=accounts[0])


def __add_balance(address, value):
    c = SelfDestroy.deploy({'from': accounts[1]})
    accounts[1].transfer(c.address, value)
    c.destruct(address)


def test_update_param_failed_with_unknown_key(burn):
    __update_gov_address(burn)
    with brownie.reverts("UnsupportedGovParam: unknown"):
        burn.updateParam("unknown", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_burn_cap_with_unmatched_length(burn):
    __update_gov_address(burn)
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['burnCap'])
    with brownie.reverts(f"{error_msg}"):
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
    __add_balance(burn.address, Web3.to_wei(1, 'ether'))

    new_burn_cap = "0x0000000000000000000000000000000000000000000000000de0b6b3a763fff"
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["burnCap", Web3.to_int(hexstr=new_burn_cap), burn.balance(), Web3.to_int(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"{error_msg}"):
        burn.updateParam("burnCap", new_burn_cap)


def test_update_param_burn_cap_success(burn):
    __update_gov_address(burn)
    __add_balance(burn.address, Web3.to_wei(1, 'ether'))
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
    __add_balance(burn.address, Web3.to_wei(1, 'ether'))

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn()
    assert "burned" not in tx.events

    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_value_0_and_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    __add_balance(burn.address, Web3.to_wei(2, 'ether'))

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn()
    assert "burned" not in tx.events
    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_1_ether_and_balance_is_0(burn):
    burn_value = Web3.to_wei(1, 'ether')
    tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({'value': burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": burn_value})

    assert tracker.delta() == (0 - burn_value)
    assert burn_tracker.delta() == burn_value


def test_burn_success_with_value_1_and_balance_is_equal_to_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    burn_value = Web3.to_wei(1, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({"value": burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": burn_value})

    assert account0_tracker.delta() == (0 - burn_value)
    assert burn_tracker.delta() == burn_value


def test_burn_failed_with_1_ether_due_to_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")
    __add_balance(burn.address, Web3.to_wei(2, 'ether'))

    burn_value = Web3.to_wei(1, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({'value': burn_value})
    assert "burned" not in tx.events

    assert account0_tracker.delta() == 0
    assert burn_tracker.delta() == 0


def test_burn_success_with_half_of_2_ether_and_balance_is_greater_than_burn_cap(burn):
    __update_gov_address(burn)
    burn.updateParam("burnCap", "0x0000000000000000000000000000000000000000000000000de0b6b3a7640000")

    burn_value = Web3.to_wei(2, 'ether')

    account0_tracker = get_tracker(accounts[0])
    burn_tracker = get_tracker(burn)

    tx = burn.burn({"value": burn_value})
    expect_event(tx, "burned", {"to": accounts[0], "amount": Web3.to_wei(1, 'ether')})

    assert account0_tracker.delta() == (0 - Web3.to_wei(1, 'ether'))
    assert burn_tracker.delta() == Web3.to_wei(1, 'ether')


def test_receive_ether(burn):
    with brownie.reverts():
        accounts[0].transfer(burn.address, Web3.to_wei(1, 'ether'))


def test_receive_ether_through_destruct_command(burn):
    __add_balance(burn.address, 1)
    assert brownie.web3.eth.get_balance(burn.address) == 1


def test_modify_burn_cap(burn):
    new_cap = 200
    hex_value = padding_left(Web3.to_hex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['burnCap', Web3.to_bytes(hexstr=hex_value)]),
        "update burn cap"
    )
    assert burn.burnCap() == new_cap


def test_burn_less_than_cap(burn):
    new_cap = 100
    hex_value = padding_left(Web3.to_hex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['burnCap', Web3.to_bytes(hexstr=hex_value)]),
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
    hex_value = padding_left(Web3.to_hex(new_cap), 64)

    execute_proposal(
        burn.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['burnCap', Web3.to_bytes(hexstr=hex_value)]),
        "update burn cap"
    )

    __add_balance(burn.address, 101)

    account0_tracker = get_tracker(accounts[0])
    tx = burn.burn({'value': 8})
    assert "burned" not in tx.events
    assert account0_tracker.delta() == 0
