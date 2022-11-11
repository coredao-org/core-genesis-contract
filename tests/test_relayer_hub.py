import pytest
import brownie
from web3 import Web3
from brownie import *
from .utils import expect_event, get_tracker, padding_left


@pytest.fixture(scope="module", autouse=True)
def set_up(validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub,
           gov_hub, pledge_agent, burn, foundation):
    relay_hub.updateContractAddr(
        validator_set.address,
        slash_indicator.address,
        system_reward.address,
        btc_light_client.address,
        relay_hub.address,
        candidate_hub.address,
        accounts[0],
        pledge_agent.address,
        burn.address,
        foundation.address
    )


def test_update_param_failed_with_unknown_key(relay_hub):
    with brownie.reverts("unknown param"):
        relay_hub.updateParam("unknown", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_require_deposit_with_unmatched_length(relay_hub):
    with brownie.reverts("length of requiredDeposit mismatch"):
        relay_hub.updateParam("requiredDeposit", "0x0000000000123")


def test_update_param_dues_with_unmatched_length(relay_hub):
    with brownie.reverts("length of dues mismatch"):
        relay_hub.updateParam("dues", "0x0000000000123")


def test_update_param_require_deposit_failed_with_value_out_of_range(relay_hub):
    with brownie.reverts("the requiredDeposit out of range"):
        relay_hub.updateParam("requiredDeposit", padding_left(Web3.toHex(relay_hub.dues()), 64))


def test_update_param_dues_failed_with_value_out_of_range(relay_hub):
    with brownie.reverts("the dues out of range"):
        relay_hub.updateParam("dues", padding_left(Web3.toHex(0), 64))
    with brownie.reverts("the dues out of range"):
        relay_hub.updateParam("dues", padding_left(Web3.toHex(relay_hub.requiredDeposit() + 10), 64))


def test_update_param_required_deposit_success(relay_hub):
    value = padding_left(Web3.toHex(relay_hub.dues() + 10), 64)
    tx = relay_hub.updateParam("requiredDeposit", value)
    expect_event(tx, "paramChange", {
        "key": "requiredDeposit",
        "value": value
    })


def test_update_param_dues_success(relay_hub):
    value = padding_left(Web3.toHex(relay_hub.requiredDeposit() - 10), 64)
    tx = relay_hub.updateParam("dues", value)
    expect_event(tx, "paramChange", {
        "key": "dues",
        "value": value
    })


def test_register_and_unregister_success(relay_hub, system_reward):
    required_deposit = relay_hub.requiredDeposit()
    tx = relay_hub.register({'value': required_deposit})
    expect_event(tx, "relayerRegister", {"relayer": accounts[0]})
    assert relay_hub.isRelayer(accounts[0]) is True

    tracker = get_tracker(accounts[0])
    system_reward_tracker = get_tracker(system_reward)

    tx = relay_hub.unregister()
    expect_event(tx, "relayerUnRegister", {"relayer": accounts[0]})
    assert relay_hub.isRelayer(accounts[0]) is False

    assert system_reward_tracker.delta() == relay_hub.dues()
    assert tracker.delta() == required_deposit - relay_hub.dues()


def test_register_failed(relay_hub):
    required_deposit = relay_hub.requiredDeposit()
    relay_hub.register({'value': required_deposit})

    with brownie.reverts("relayer already exists"):
        relay_hub.register({'value': required_deposit})

    with brownie.reverts("relayer does not exist"):
        relay_hub.unregister({'from': accounts[1]})

    with brownie.reverts("deposit value does not match requirement"):
        relay_hub.register({'from': accounts[1], 'value': 1})

    with brownie.reverts("deposit value does not match requirement"):
        relay_hub.register({'from': accounts[1], 'value': 1e10})
