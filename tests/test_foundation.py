import pytest
import brownie
from web3 import Web3
from brownie import accounts, reverts, Foundation, FoundationMock

def deploy_foundation():
    gov_account = accounts[0]
    foundation = FoundationMock.deploy({'from': gov_account})
    foundation.setGov(gov_account, {'from': gov_account})
    return foundation, gov_account

def test_successful_fund():
    foundation, gov_account = deploy_foundation()

    payee = accounts[1]
    fund_amount = 1000000000000000000  # 1 Ether

    gov_account.transfer(foundation.address, fund_amount * 2) # Transfer twice the amount of eth to ensure the balance is sufficient
    initial_balance = payee.balance()
    foundation.fund(payee, fund_amount, {'from': gov_account})

    assert payee.balance() == initial_balance + fund_amount

def test_fund_reverts_with_zero_address():
    foundation, gov_account = deploy_foundation()

    fund_amount = 1000000000000000000  # 1 Ether
    gov_account.transfer(foundation.address, fund_amount * 2)  # Transfer twice the amount of eth to ensure the balance is sufficient

    with pytest.raises(Exception):
        foundation.fund("0x0000000000000000000000000000000000000000", fund_amount, {'from': gov_account})

def test_fund_reverts_if_not_enough_balance():
    foundation, gov_account = deploy_foundation()

    fund_amount = 1000000000000000000  # 1 Ether
    gov_account.transfer(foundation.address, fund_amount)  # Transfer twice the amount of eth to ensure the balance is sufficient

    with pytest.raises(Exception):
        foundation.fund(payee, fund_amount*2, {'from': gov_account})

def test_fund_reverts_for_non_gov_caller():
    foundation, gov_account = deploy_foundation()

    non_gov_account = accounts[2]
    payee = accounts[1]
    fund_amount = 1000000000000000000  # 1 Ether
    gov_account.transfer(foundation.address, fund_amount * 2)

    with pytest.raises(Exception):
        foundation.fund(payee, fund_amount, {'from': non_gov_account})