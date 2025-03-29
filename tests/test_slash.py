import brownie
import pytest
import random
from brownie import accounts, chain
from brownie.test import given, strategy
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from .utils import expect_event, padding_left, update_system_contract_address
from .common import register_candidate, turn_round

misdemeanorThreshold = 0
felonyThreshold = 0


@pytest.fixture(scope="module", autouse=True)
def set_threshold(slash_indicator):
    global misdemeanorThreshold
    global felonyThreshold
    misdemeanorThreshold = slash_indicator.misdemeanorThreshold()
    felonyThreshold = slash_indicator.felonyThreshold()


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_slash_validator(slash_indicator):
    account: LocalAccount = Account.create(str(random.random()))
    tx = slash_indicator.slash(account.address)
    assert len(tx.events.keys()) == 0


def test_misdemeanor_normal_address(slash_indicator):
    account: LocalAccount = Account.create(str(random.random()))
    for _ in range(misdemeanorThreshold):
        slash_indicator.slash(account.address)


def test_misdemeanor_validator(slash_indicator, validator_set):
    operator = accounts[0]
    consensus = register_candidate(operator=operator)
    turn_round()

    assert validator_set.getValidators() == [consensus]
    for _ in range(misdemeanorThreshold):
        tx = slash_indicator.slash(consensus)

    expect_event(tx, "validatorMisdemeanor", {'validator': operator})


def test_calc_income_after_misdemeanor(slash_indicator, validator_set):
    operator1 = accounts[1]
    operator2 = accounts[2]

    consensus1 = register_candidate(operator=operator1)
    consensus2 = register_candidate(operator=operator2)
    turn_round()

    validator_set.deposit(consensus1, {'value': 1000})
    validator_set.deposit(consensus2, {'value': 1000})
    for _ in range(misdemeanorThreshold):
        slash_indicator.slash(consensus2)

    assert validator_set.getIncoming(consensus2) == 0


def test_felony(slash_indicator, validator_set, candidate_hub):
    operator1 = accounts[1]
    operator2 = accounts[2]
    consensus1 = register_candidate(operator=operator1)
    register_candidate(operator=operator2)
    turn_round()

    for _ in range(felonyThreshold):
        tx = slash_indicator.slash(consensus1)
    expect_event(tx, 'validatorFelony', {'validator': operator1})
    assert consensus1 not in validator_set.getValidators()
    assert candidate_hub.jailMap(operator1) > 0


def test_felony_when_only_one_validator(slash_indicator):
    operator = accounts[1]
    consensus = register_candidate(operator=operator)
    turn_round()

    for _ in range(felonyThreshold):
        tx = slash_indicator.slash(consensus)
    assert 'validatorFelony' not in tx.events


def test_jailed_candidate(slash_indicator, validator_set):
    operator1 = accounts[1]
    operator2 = accounts[2]
    consensus1 = register_candidate(operator=operator1)
    consensus2 = register_candidate(operator=operator2)
    turn_round()

    for _ in range(felonyThreshold):
        slash_indicator.slash(consensus1)

    turn_round()
    assert validator_set.getValidators() == [consensus2]


def test_deduct_margin(slash_indicator, candidate_hub):
    operator1 = accounts[1]
    operator2 = accounts[2]
    consensus1 = register_candidate(operator=operator1)
    register_candidate(operator=operator2)
    turn_round()

    for _ in range(felonyThreshold):
        slash_indicator.slash(consensus1)
    candidate = candidate_hub.candidateSet(candidate_hub.operateMap(operator1) - 1).dict()
    assert candidate['margin'] == candidate_hub.requiredMargin() - slash_indicator.felonyDeposit()


def test_clean(slash_indicator, validator_set):
    decrease_value = felonyThreshold // slash_indicator.DECREASE_RATE()
    st = strategy("uint8", max_value=felonyThreshold - 1)

    for _ in range(10):
        slash_accounts = [Account.create(str(random.random())) for _ in range(random.randint(1, 10))]
        counts = [st.example() for _ in slash_accounts]
        for account, count in zip(slash_accounts, counts):
            validator_set.setValidatorSetMap(account.address)
            for _ in range(count):
                slash_indicator.slash(account.address)
        turn_round()
        for account, count in zip(slash_accounts, counts):
            assert slash_indicator.getSlashIndicator(account.address)[1] == max([count - decrease_value, 0])


def test_only_gov_can_call(slash_indicator):
    value = padding_left(Web3.to_hex(1000), 64)
    with brownie.reverts(f"the msg sender must be governance contract"):
        slash_indicator.updateParam('misdemeanorThreshold', value)


@pytest.mark.parametrize("new_misdemeanorThreshold", [1, 2, 3])
def test_update_misdemeanor_threshold_success(slash_indicator, new_misdemeanorThreshold):
    value = padding_left(Web3.to_hex(new_misdemeanorThreshold), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('misdemeanorThreshold', value)
    assert slash_indicator.misdemeanorThreshold() == value


@pytest.mark.parametrize("new_misdemeanorThreshold", [0, 4, 5, 100])
def test_update_misdemeanor_threshold_failure(slash_indicator, new_misdemeanorThreshold):
    value = padding_left(Web3.to_hex(new_misdemeanorThreshold), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: misdemeanorThreshold, {new_misdemeanorThreshold}, 1, 3"):
        slash_indicator.updateParam('misdemeanorThreshold', value)


@pytest.mark.parametrize("new_felonyThreshold", [3, 4, 5, 6, 100])
def test_update_felony_threshold_success(slash_indicator, new_felonyThreshold):
    value = padding_left(Web3.to_hex(new_felonyThreshold), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('felonyThreshold', value)
    assert slash_indicator.felonyThreshold() == value


@pytest.mark.parametrize("new_felonyThreshold", [0, 1, 2])
def test_update_felony_threshold_failure(slash_indicator, new_felonyThreshold):
    value = padding_left(Web3.to_hex(new_felonyThreshold), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(f"OutOfBounds: felonyThreshold, {new_felonyThreshold}, 3, {uint256_max}"):
        slash_indicator.updateParam('felonyThreshold', value)


@pytest.mark.parametrize("new_rewardForReportDoubleSign", [1, 2, 3, 1e19, 1e20, 1e21])
def test_update_reward_for_report_double_sign_success(slash_indicator, new_rewardForReportDoubleSign):
    value = padding_left(Web3.to_hex(int(new_rewardForReportDoubleSign)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('rewardForReportDoubleSign', value)
    assert slash_indicator.rewardForReportDoubleSign() == value


@pytest.mark.parametrize("new_rewardForReportDoubleSign", [0, 1e22, 1e23])
def test_update_reward_for_report_double_sign_failure(slash_indicator, new_rewardForReportDoubleSign):
    value = padding_left(Web3.to_hex(int(new_rewardForReportDoubleSign)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    max_value = 1000000000000000000000
    with brownie.reverts(
            f"OutOfBounds: rewardForReportDoubleSign, {int(new_rewardForReportDoubleSign)}, 1, {max_value}"):
        slash_indicator.updateParam('rewardForReportDoubleSign', value)


@pytest.mark.parametrize("new_felonyDeposit", [1e18, 1e19, 1e20])
def test_update_felony_deposit_success(slash_indicator, new_felonyDeposit):
    value = padding_left(Web3.to_hex(int(new_felonyDeposit)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('felonyDeposit', value)
    assert slash_indicator.felonyDeposit() == value


@pytest.mark.parametrize("new_felonyDeposit", [0, 1e16, 1e17])
def test_update_felony_deposit_failure(slash_indicator, new_felonyDeposit):
    value = padding_left(Web3.to_hex(int(new_felonyDeposit)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    min_value = 1000000000000000000
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(
            f"OutOfBounds: felonyDeposit, {int(new_felonyDeposit)}, {min_value}, {uint256_max}"):
        slash_indicator.updateParam('felonyDeposit', value)


@pytest.mark.parametrize("new_felonyRound", [1, 2, 3, 1000, 5000])
def test_update_felony_round_success(slash_indicator, new_felonyRound):
    value = padding_left(Web3.to_hex(new_felonyRound), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('felonyRound', value)
    assert slash_indicator.felonyRound() == value


@pytest.mark.parametrize("new_felonyRound", [0])
def test_update_felony_round_failure(slash_indicator, new_felonyRound):
    value = padding_left(Web3.to_hex(new_felonyRound), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(
            f"OutOfBounds: felonyRound, 0, {1}, {uint256_max}"):
        slash_indicator.updateParam('felonyRound', value)


def test_invalid_key(slash_indicator):
    value = padding_left(Web3.to_hex(1000), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    with brownie.reverts("UnsupportedGovParam: key_error"):
        slash_indicator.updateParam('key_error', value)


def test_invalid_value_length(slash_indicator):
    value = padding_left(Web3.to_hex(1000), 66)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    with brownie.reverts("MismatchParamLength: felonyRound"):
        slash_indicator.updateParam('felonyRound', value)


def test_get_slash_indicator_success(slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    slash_indicator.slash(consensuses[0])
    value = slash_indicator.getSlashIndicator(consensuses[0])
    assert value == (chain.height, 1)
    turn_round(consensuses)
