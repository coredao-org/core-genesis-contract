import pytest
import random
from brownie import accounts
from brownie.test import given, strategy
from eth_account import Account
from eth_account.signers.local import LocalAccount
from .utils import expect_event
from .common import register_candidate, turn_round

misdemeanorThreshold = 0
felonyThreshold = 0


@pytest.fixture(scope="module", autouse=True)
def set_threshold(slash_indicator):
    global misdemeanorThreshold
    global felonyThreshold
    misdemeanorThreshold = slash_indicator.misdemeanorThreshold()
    felonyThreshold = slash_indicator.felonyThreshold()


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
    candidate = candidate_hub.candidateSet(candidate_hub.operateMap(operator1)-1).dict()
    assert candidate['margin'] == candidate_hub.requiredMargin() - slash_indicator.felonyDeposit()


def test_clean(slash_indicator, validator_set):
    decrease_value = felonyThreshold // slash_indicator.DECREASE_RATE()
    st = strategy("uint8", max_value=felonyThreshold-1)

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



