import pytest
import brownie
from web3 import Web3, constants

from .common import *
from .delegate import *
from .utils import *
from eth_abi import encode

init_validators = [
    '0x01Bca3615D24d3c638836691517b2B9b49b054B1',
    '0xa458499604A85E90225a14946f36368Ae24df16D',
    '0x5E00C0D5C4C10d4c805aba878D51129A89d513e0',
    '0x1Cd652bC64Af3f09B490dAae27f46e53726ce230',
    '0xDA37ccECBB2D7C83aE27eE2BeBFE8EBCe162c600'
]
init_validator_incomes = [0, 0, 0, 0, 0]
random_address = "0x51BafF77eFF55ac97d170E7449b59b73E95e262e"
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"

account_tracker: AccountTracker = None
system_reward_tracker: AccountTracker = None
validator_set_tracker: AccountTracker = None
stake_hub_tracker: AccountTracker = None
validator_set_instance = None
BLOCK_REWARD = 0
felony_round = 1
felony_deposit = int(1e5)


@pytest.fixture(scope="module", autouse=True)
def setup(system_reward, validator_set, pledge_agent, core_agent, stake_hub, candidate_hub):
    global account_tracker, system_reward_tracker, validator_set_tracker, stake_hub_tracker
    global validator_set_instance
    global BLOCK_REWARD, block_reward, validator_count
    validator_set_instance = validator_set
    BLOCK_REWARD = validator_set.BLOCK_REWARD()
    account_tracker = get_tracker(accounts[0])
    system_reward_tracker = get_tracker(system_reward)
    validator_set_tracker = get_tracker(validator_set)
    stake_hub_tracker = get_tracker(stake_hub)
    block_reward = validator_set.blockReward()
    validator_count = validator_set.validatorCount()
    candidate_hub.setMaxAlternateCount(1)
    candidate_hub.setValidatorCount(3)
    validator_set.setMaintainSlashPercent(30)


@pytest.fixture()
def deposit_for_reward(validator_set):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture()
def set_candidate_maintenance(candidate_hub):
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for operator in operators[:3]:
        delegate_coin_success(operator, accounts[0], 1e18)
        delegate_coin_success(operator, accounts[1], 1e18)
    return operators, consensuses


@pytest.fixture(autouse=True)
def clear_tracker():
    account_tracker.balance()
    system_reward_tracker.balance()
    validator_set_tracker.balance()
    stake_hub_tracker.balance()


def __balance_check(account_delta=0, validator_set_delta=0, system_reward_delta=0, stake_hub=0):
    assert account_tracker.delta() == account_delta
    assert system_reward_tracker.delta() == system_reward_delta
    assert validator_set_tracker.delta() == validator_set_delta
    assert stake_hub_tracker.delta() == stake_hub


def __contract_check(total_income, validator_incomes):
    validators = validator_set_instance.getValidators()
    current_total_income = validator_set_instance.totalInCome()
    current_validate_incomes = []

    assert current_total_income == total_income
    assert len(validator_incomes) == len(validators)

    for validator in validators:
        current_validate_incomes.append(validator_set_instance.getIncoming(validator))

    for i in range(len(current_validate_incomes)):
        assert current_validate_incomes[i] == validator_incomes[i]


def __fake_validator_set():
    update_system_contract_address(validator_set_instance, candidate_hub=accounts[0])


def __update_gov_address():
    update_system_contract_address(validator_set_instance, gov_hub=accounts[0])


def __update_slash_address():
    update_system_contract_address(validator_set_instance, slash_indicator=accounts[0])


def test_check_validator_address_failed_with_zero_address(validator_set):
    assert validator_set.isValidator.call(constants.ADDRESS_ZERO) is False


def test_check_validator_address_failed_with_random_address(validator_set):
    assert validator_set.isValidator.call(random_address) is False


def test_check_validator_address_success(validator_set):
    assert validator_set.isValidator.call(init_validators[0]) is True


def test_get_validators_success():
    assert validator_set_instance.getValidators() == init_validators


def test_get_income_failed_with_zero_address():
    assert validator_set_instance.getIncoming(ZERO_ADDRESS) == 0


def test_get_income_failed_with_deprecated_validator():
    assert validator_set_instance.getIncoming(random_address) == 0


def get_income_success_with_0_amount():
    assert validator_set_instance.getIncoming(init_validators[0]) == 0


def test_get_income_success_with_certain_amount():
    deposit_value = 9999
    validator_set_instance.deposit(init_validators[0], {'value': deposit_value})
    assert validator_set_instance.getIncoming(init_validators[0]) == deposit_value


def test_deposit_to_zero_address():
    deposit_value = 9999999
    tx = validator_set_instance.deposit(ZERO_ADDRESS, {'value': deposit_value})
    expect_event(tx, "deprecatedDeposit", {
        "validator": ZERO_ADDRESS,
        "amount": deposit_value
    })
    __contract_check(0, init_validator_incomes)
    __balance_check(0 - deposit_value, deposit_value, 0)


def test_deposit_to_deprecated_validator():
    deposit_value = 9999999
    tx = validator_set_instance.deposit(random_address, {'value': deposit_value})
    expect_event(tx, "deprecatedDeposit", {
        "validator": random_address,
        "amount": deposit_value
    })
    __contract_check(0, init_validator_incomes)
    __balance_check(0 - deposit_value, deposit_value, 0)


def test_deposit_to_deprecated_validator_with_amount_0():
    deposit_value = 0
    tx = validator_set_instance.deposit(random_address, {'value': deposit_value})
    expect_event(tx, "deprecatedDeposit", {
        "validator": random_address,
        "amount": deposit_value
    })
    __contract_check(0, init_validator_incomes)
    __balance_check(0 - deposit_value, deposit_value, 0)


def test_deposit_to_validator_with_amount_0():
    deposit_value = 0
    address = init_validators[0]
    tx = validator_set_instance.deposit(address, {'value': deposit_value})
    expect_event(tx, "validatorDeposit", {
        "validator": address,
        "amount": deposit_value
    })
    __contract_check(deposit_value, [deposit_value, 0, 0, 0, 0])
    __balance_check(0 - deposit_value, deposit_value, 0)


def test_deposit_to_validator():
    deposit_value = 999
    address = init_validators[0]
    tx = validator_set_instance.deposit(address, {'value': deposit_value})
    expect_event(tx, "validatorDeposit", {
        "validator": address,
        "amount": deposit_value
    })
    __contract_check(deposit_value, [deposit_value, 0, 0, 0, 0])
    __balance_check(0 - deposit_value, deposit_value, 0)


@pytest.mark.parametrize("validator_address", [ZERO_ADDRESS, random_address])
def test_deposit_to_deprecated_validator_with_positive_balance(validator_address):
    accounts[1].transfer(validator_set_instance.address, Web3.to_wei(10, 'ether'))
    validator_set_tracker.balance()

    deposit_value = 999
    tx = validator_set_instance.deposit(validator_address, {'value': deposit_value})
    amount = validator_set_instance.blockReward() + deposit_value
    expect_event(tx, "deprecatedDeposit", {
        'validator': validator_address,
        'amount': amount
    })
    __contract_check(0, init_validator_incomes)
    __balance_check(0 - deposit_value, deposit_value, 0)


@pytest.mark.parametrize("validator_address,deposit_value", [
    (random_address, 0),
    (init_validators[0], 0),
    (init_validators[0], 9999999)
])
def test_deposit_to_validator_with_positive_balance(validator_address, deposit_value):
    accounts[1].transfer(validator_set_instance.address, Web3.to_wei(10, 'ether'))
    validator_set_tracker.balance()

    tx = validator_set_instance.deposit(validator_address, {'value': deposit_value})
    amount = validator_set_instance.blockReward() + deposit_value
    event_name = "validatorDeposit" if validator_address in init_validators else 'deprecatedDeposit'
    expect_event(tx, event_name, {
        'validator': validator_address,
        'amount': amount
    })
    if validator_address in init_validators:
        __contract_check(amount, [amount, 0, 0, 0, 0])
    else:
        __contract_check(0, init_validator_incomes)
    __balance_check(0 - deposit_value, deposit_value, 0)


def test_vote_addr_and_weights_mismatch_failed(set_candidate):
    operators, consensuses = set_candidate
    accounts[1].transfer(validator_set_instance.address, Web3.to_wei(10, 'ether'))
    validator_set_tracker.balance()
    weights = [10, 10]
    with brownie.reverts("length not equal"):
        validator_set_instance.vote(consensuses, weights)

    validator_set_instance.vote([], [])


def test_val_addrs_contains_non_validator(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    consensuses.append(accounts[2])
    weights = [10, 20, 30, 40]
    validator_set.vote(consensuses, weights)
    assert validator_set.getValidatorByConsensus(consensuses[0])['voteWeight'] == weights[0]
    assert validator_set.getValidatorByConsensus(consensuses[1])['voteWeight'] == weights[1]
    assert validator_set.getValidatorByConsensus(consensuses[2])['voteWeight'] == weights[2]
    with brownie.reverts("no match validator"):
        validator_set.getValidatorByConsensus(consensuses[3])


@pytest.mark.xfail
def test_invalid_input_format_failed(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    consensuses.append(accounts[2])
    weights = accounts[0]
    with brownie.reverts():
        validator_set.vote(consensuses, weights)


def test_vote_success(validator_set):
    operators = []
    consensuses = []
    vote_address_list = []
    for operator in accounts[5:8]:
        operators.append(operator)
        vote_address = random_vote_address()
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address))
        vote_address_list.append(vote_address)
    turn_round()
    weights = [10, 20, 30]
    validator_set.vote(consensuses, weights)
    for i in range(len(consensuses)):
        validator = [operators[i], consensuses[i], operators[i], 1000, 0, vote_address_list[i], weights[i], 0]
        assert validator_set.getValidatorByConsensus(consensuses[i]) == validator


def test_repeated_vote_counts_accumulate_success(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    weights = [10, 20, 30]
    validator_set.vote(consensuses, weights)
    validator_set.vote(consensuses, weights)
    validator_set.vote(consensuses, weights)
    for i in range(len(consensuses)):
        assert validator_set.getValidatorByConsensus(consensuses[i])['voteWeight'] == weights[i] * 3

    validator_set.vote(consensuses[:-1], weights[:-1])
    assert validator_set.getValidatorByConsensus(consensuses[0])['voteWeight'] == weights[0] * 4
    assert validator_set.getValidatorByConsensus(consensuses[1])['voteWeight'] == weights[1] * 4


def test_vote_for_unelected_validator_failed(validator_set, set_candidate):
    operators, consensuses = set_candidate
    weights = [10, 20, 30]
    validator_set.vote(consensuses, weights)
    for i in range(len(consensuses)):
        validator_set.vote([consensuses[i]], [weights[i]])
    for i in range(len(consensuses)):
        with brownie.reverts("no match validator"):
            validator_set.getValidatorByConsensus(consensuses[i])


@pytest.mark.parametrize("validator_state", ['minor', 'major'])
def test_vote_address_contains_felony_failed(validator_set, set_candidate, slash_indicator, validator_state):
    operators, consensuses = set_candidate
    turn_round()
    turn_round(consensuses)
    tx0 = None
    vote_state = False
    if validator_state == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
        vote_state = True
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    validator_set.vote([consensuses[0]], [10])
    if vote_state:
        assert validator_set.getValidatorByConsensus(consensuses[0])['voteWeight'] == 10
    else:
        with brownie.reverts("no match validator"):
            validator_set.getValidatorByConsensus(consensuses[0])


def test_vote_address_contains_unregistered_failed(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    weights = [10, 20, 30]
    with brownie.reverts("no match validator"):
        validator_set.getValidatorByConsensus(consensuses[0])
    validator_set.vote(consensuses, weights)
    with brownie.reverts("no match validator"):
        validator_set.getValidatorByConsensus(consensuses[0])


def test_vote_array_length_change_success(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    weights0 = [10, 20, 30]
    weights1 = [60, 90, 120]
    validator_set.vote(consensuses, weights0)
    validator_set.vote(consensuses[:1], weights0[:1])
    validator_set.vote(consensuses, weights1)
    validator_set.vote(consensuses[:2], weights1[:2])
    actual_validator_fee = [140, 200, 150]
    for i in range(len(consensuses)):
        assert validator_set.getValidatorByConsensus(consensuses[i])['voteWeight'] == actual_validator_fee[i]


# updateValidatorSet
def test_update_failed_by_address_which_is_not_candidate():
    with brownie.reverts("the msg sender must be candidate contract"):
        validator_set_instance.updateValidatorSet([random_address], [random_address], [random_address], [100], [],
                                                  validator_count)


def test_update_failed_with_empty_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [], validator_count)
    assert validator_set_instance.getValidators() == init_validators


def test_update_failed_with_addresses_of_different_length():
    __fake_validator_set()
    with brownie.reverts("the numbers of consensusAddresses and commissionThousandthss should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address], [accounts[2].address],
                                                  [accounts[3].address, accounts[4].address], [random_vote_address()],
                                                  validator_count)
    with brownie.reverts("the numbers of consensusAddresses and feeAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address],
                                                  [accounts[2].address, accounts[4].address], [accounts[3].address],
                                                  [random_vote_address()], validator_count)
    with brownie.reverts("the numbers of consensusAddresses and operateAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address, accounts[4].address],
                                                  [accounts[2].address], [accounts[3].address], [random_vote_address()],
                                                  validator_count)
    with brownie.reverts("the numbers of consensusAddresses and operateAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address, accounts[4].address], [accounts[1].address],
                                                  [accounts[2].address], [accounts[3].address], [random_vote_address()],
                                                  validator_count)


def test_update_failed_with_duplicate_consensus_address():
    __fake_validator_set()
    with brownie.reverts("duplicate consensus address"):
        validator_set_instance.updateValidatorSet([accounts[0], accounts[0]], [accounts[1], accounts[1]],
                                                  [accounts[2], accounts[2]], [100, 100],
                                                  [random_vote_address(), random_vote_address()], validator_count)


def test_update_failed_with_commissionThousandths_out_of_range():
    __fake_validator_set()
    with brownie.reverts("commissionThousandths out of bound"):
        validator_set_instance.updateValidatorSet([accounts[0], accounts[0]], [accounts[1], accounts[3]],
                                                  [accounts[2], accounts[2]], [1000, 10000],
                                                  [random_vote_address(), random_vote_address()], validator_count)


def test_update_success():
    __fake_validator_set()
    vote_address = random_vote_address()
    tx = validator_set_instance.updateValidatorSet([accounts[0]], [accounts[1]], [accounts[2]], [1000],
                                                   [vote_address], validator_count)
    expect_event(tx, "validatorSetUpdated")
    assert validator_set_instance.getValidators() == [accounts[1]]
    assert validator_set_instance.getValidatorByConsensus(accounts[1]) == [accounts[0], accounts[1], accounts[2], 1000,
                                                                           0, vote_address, 0, 0]


def test_update_validator_set_default_vote_weight(set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    __fake_validator_set()
    vote_address = random_vote_address()
    validator_set_instance.updateValidatorSet([operators[0]], [accounts[1]], [accounts[2]], [1000],
                                              [vote_address], validator_count)
    assert validator_set_instance.getValidators() == [accounts[1]]
    validator = validator_set_instance.getValidatorByConsensus(accounts[1])
    assert validator['voteWeight'] == 0


def test_update_validator_set_add_new(validator_set, set_candidate):
    turn_round()
    __fake_validator_set()
    commission_thousandths = 400
    assert len(validator_set.getValidators()) == 3
    operate_addr_list = [account for account in accounts[:5]]
    consensus_addr_list = [account for account in accounts[5:10]]
    fee_addr_list = [account for account in accounts[10:15]]
    vote_addr_list = [random_vote_address() for _ in range(5)]
    commission_thousandths = [commission_thousandths for _ in range(5)]
    validator_set.updateValidatorSet(operate_addr_list, consensus_addr_list, fee_addr_list, commission_thousandths,
                                     vote_addr_list, validator_count)
    assert len(validator_set.getValidators()) == 5
    for index, address in enumerate(consensus_addr_list):
        assert validator_set.getValidatorByConsensus(address) == [operate_addr_list[index], address,
                                                                  fee_addr_list[index], commission_thousandths[index],
                                                                  0, vote_addr_list[index], 0, 0]


def test_update_validator_set_modify_existing(validator_set):
    __fake_validator_set()
    commission_thousandths = 400
    assert len(validator_set.getValidators()) == 5
    operate_addr_list = [account for account in accounts[:5]]
    consensus_addr_list = [account for account in accounts[5:10]]
    fee_addr_list = [account for account in accounts[10:15]]
    vote_addr_list = [random_vote_address() for _ in range(5)]
    commission_thousandths = [commission_thousandths for _ in range(5)]
    validator_set.updateValidatorSet(operate_addr_list, consensus_addr_list, fee_addr_list, commission_thousandths,
                                     vote_addr_list, validator_count)
    assert len(validator_set.getValidators()) == 5
    for index, address in enumerate(consensus_addr_list):
        validator = [operate_addr_list[index], address, fee_addr_list[index], commission_thousandths[index], 0,
                     vote_addr_list[index], 0, 0]
        assert validator_set.getValidatorByConsensus(address) == validator


@pytest.mark.parametrize("legnth", [4, 6, 7])
def test_vote_validator_count_mismatch(validator_set, legnth):
    __fake_validator_set()
    commission_thousandths = 400
    assert len(validator_set.getValidators()) == 5
    operate_addr_list = [account for account in accounts[:5]]
    consensus_addr_list = [account for account in accounts[5:10]]
    fee_addr_list = [account for account in accounts[10:15]]
    vote_addr_list = [random_vote_address() for _ in range(legnth)]
    commission_thousandths = [commission_thousandths for _ in range(5)]
    with brownie.reverts("the numbers of consensusAddresses and voteAddressed should be equal"):
        validator_set.updateValidatorSet(operate_addr_list, consensus_addr_list, fee_addr_list, commission_thousandths,
                                         vote_addr_list, validator_count)


def test_validator_count_change_update(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_coin_success(operators[0], accounts[0], amount=1002)
    delegate_coin_success(operators[1], accounts[0], amount=1001)
    delegate_coin_success(operators[2], accounts[0], amount=1000)
    turn_round()
    assert len(validator_set.getValidators()) == 3
    delegate_coin_success(operators[0], accounts[0], amount=999)
    vote_address = random_vote_address()
    consensuses.append(register_candidate(operator=accounts[20], vote_address=vote_address))
    operators.append(accounts[20])
    tx = turn_round(consensuses)
    expect_event(tx, "validatorSetUpdated")
    assert validator_set.getValidators() == consensuses
    # commission_thousandths is set to 1000 because there is no stake on the validator.
    commission_thousandths = 1000
    assert validator_set.getValidatorByConsensus(consensuses[-1]) == [accounts[20], consensuses[-1], accounts[20],
                                                                      commission_thousandths, 0, vote_address, 0, 0]
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round(consensuses)
    candidate_hub.unregister({'from': operators[0]})
    turn_round(consensuses)
    assert validator_set.getValidatorByConsensus(consensuses[-1]) == [accounts[20], consensuses[-1], accounts[20],
                                                                      commission_thousandths, 0, vote_address, 0, 0]
    with brownie.reverts("no match validator"):
        validator_set.getValidatorByConsensus(consensuses[0])


def test_update_validator_set_updates_ranked_validator_list(validator_set):
    operate_addr_list = [account for account in accounts[:5]]
    consensus_addr_list = [account for account in accounts[5:10]]
    fee_addr_list = [account for account in accounts[10:15]]
    vote_addr_list = [random_vote_address() for _ in range(5)]
    commission_thousandths = [400 for _ in range(5)]
    validator_count = 5
    update_system_contract_address(validator_set, candidate_hub=accounts[0])
    validator_set.updateValidatorSet(
        operate_addr_list,
        consensus_addr_list,
        fee_addr_list,
        commission_thousandths,
        vote_addr_list,
        validator_count
    )
    assert validator_set.getRankedValidatorList() == consensus_addr_list
    new_consensus_addr_list = [account for account in accounts[15:20]]
    new_operate_addr_list = [account for account in accounts[20:25]]
    new_fee_addr_list = [account for account in accounts[25:30]]
    new_vote_addr_list = [random_vote_address() for _ in range(5)]
    validator_set.updateValidatorSet(
        new_operate_addr_list,
        new_consensus_addr_list,
        new_fee_addr_list,
        commission_thousandths,
        new_vote_addr_list,
        validator_count
    )
    assert validator_set.getRankedValidatorList() == new_consensus_addr_list


# getValidatorsAndVoteAddresses
def test_get_validators_and_vote_address_success(validator_set):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(3)]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
    turn_round()
    assert validator_set.getValidatorsAndVoteAddresses() == [consensuses, vote_address_list]


def test_get_validators_and_vote_addresses_basic_functionality(validator_set, candidate_hub):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(10)]
    for index, operator in enumerate(accounts[5:15]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
        delegate_coin_success(operator, accounts[0], 1000 + index)
    candidate_hub.setMaxAlternateCount(2)
    candidate_hub.setValidatorCount(6)
    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 8
    assert validator_set.getCurrentValidatorSet()[6]['consensusAddress'] == consensuses[-7]
    assert validator_set.getCurrentValidatorSet()[7]['consensusAddress'] == consensuses[-8]
    result = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs, vote_addrs = result
    assert len(consensus_addrs) == len(vote_addrs) == 6
    assert set(consensuses[-6:]).issubset(set(consensus_addrs))


def test_get_validators_and_vote_addresses_with_maintenance_validators(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[3], accounts[0], 5000)
    delegate_coin_success(operators[4], accounts[0], 10000)
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    result = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs, vote_addrs = result

    working_validators = validator_set.getWorkingValidators()
    assert len(consensus_addrs) == len(working_validators) == 3
    for addr in consensus_addrs:
        assert addr != consensuses[0]
    assert consensuses[4] in consensus_addrs


def test_get_validators_and_vote_addresses_after_validator_exit_maintenance(validator_set, candidate_hub):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(15)]
    for index, operator in enumerate(accounts[5:20]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
        delegate_coin_success(operator, accounts[0], 10000 - index)
    candidate_hub.setMaxAlternateCount(3)
    candidate_hub.setValidatorCount(9)
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.enterMaintenance({'from': operators[3]})
    validator_set.enterMaintenance({'from': operators[6]})
    result_before = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs_before, _ = result_before

    assert consensus_addrs_before[-3:] == [consensuses[9], consensuses[10], consensuses[11]]
    for consensus in consensus_addrs_before[:-3]:
        assert consensus in [consensuses[1], consensuses[2], consensuses[4], consensuses[5], consensuses[7],
                             consensuses[8]]
    validator_set.exitMaintenance({'from': operators[0]})
    validator_set.exitMaintenance({'from': operators[6]})

    result_after = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs_after, vote_addrs_after = result_after
    for consensus in consensus_addrs_after:
        assert consensus in [consensuses[0], consensuses[1], consensuses[2], consensuses[4], consensuses[5],
                             consensuses[6], consensuses[7], consensuses[8], consensuses[9]]
    assert len(consensus_addrs_after) == 9


def test_get_validators_and_vote_addresses_with_slashed_validators(validator_set, slash_indicator,
                                                                   set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_indicator.slash(consensuses[0])
    slash_indicator.slash(consensuses[0])

    result_after = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs_after, _ = result_after

    assert consensuses[0] not in consensus_addrs_after
    turn_round(consensuses)
    slash_indicator.setFelonyThreshold(3)
    for i in range(3):
        slash_indicator.slash(consensuses[1])

    result_final = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs_final, _ = result_final
    assert consensuses[1] not in consensus_addrs_final


def test_get_validators_and_vote_addresses_validator_count_limit(validator_set):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(10)]

    for index, operator in enumerate(accounts[5:15]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))

    turn_round()

    result = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs, vote_addrs = result

    validator_count = validator_set.validatorCount()
    assert len(consensus_addrs) <= validator_count == 3

    working_validators = validator_set.getWorkingValidators()
    assert len(consensus_addrs) <= len(working_validators) == 4


def test_get_validators_and_vote_addresses_empty_validator_set(validator_set):
    turn_round()
    validator_set.clearCurrentValidatorSet()
    result = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs, vote_addrs = result
    assert len(consensus_addrs) == 0
    assert len(vote_addrs) == 0


def test_get_validators_and_vote_addresses_vote_address_correctness(validator_set):
    operators = []
    consensuses = []
    specific_vote_addresses = [
        random_vote_address(),
        random_vote_address(),
        random_vote_address()
    ]

    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=specific_vote_addresses[index]))

    turn_round()

    result = validator_set.getValidatorsAndVoteAddresses()
    consensus_addrs, vote_addrs = result

    for i, consensus_addr in enumerate(consensus_addrs):
        consensus_index = consensuses.index(consensus_addr)
        expected_vote_addr = specific_vote_addresses[consensus_index]
        assert vote_addrs[i] == expected_vote_addr


def test_get_validators_and_vote_addresses_validator_count_zero(validator_set, candidate_hub,
                                                                set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[3], accounts[0], 10000)
    turn_round()
    validator_set.setValidatorCount(0)
    assert validator_set.validatorCount() == 0
    consensus_addrs, vote_addrs = validator_set.getValidatorsAndVoteAddresses()
    working_validators = validator_set.getWorkingValidators()
    assert len(consensus_addrs) == len(working_validators)
    for addr in consensus_addrs:
        assert addr in working_validators
    assert len(consensus_addrs) == len(vote_addrs)
    for consensus in consensuses[:4]:
        assert consensus in consensus_addrs


def test_only_gov_can_govern(validator_set):
    with brownie.reverts("the msg sender must be governance contract"):
        validator_set.updateParam('voteRewardPercent',
                                  '0x0000000000000000000000000000000000000000000000000000000000000014')


def test_governance_var_not_exist_failed(validator_set):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(100), 64)
    with brownie.reverts("UnsupportedGovParam: test1"):
        validator_set.updateParam('test1', hex_value)


def test_value_length_invalid_failed(validator_set):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(20), 62)
    with brownie.reverts("MismatchParamLength: voteRewardPercent"):
        validator_set.updateParam('voteRewardPercent', hex_value)
    with brownie.reverts("MismatchParamLength: blockRewardIncentivePercent"):
        validator_set.updateParam('blockRewardIncentivePercent', hex_value)


@pytest.mark.parametrize("value", [101, 102])
def test_percent_exceeds_max_failed(validator_set, value):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(value), 64)
    with brownie.reverts(f"OutOfBounds: voteRewardPercent, {value}, 0, 100"):
        validator_set.updateParam('voteRewardPercent', hex_value)
    with brownie.reverts(f"OutOfBounds: blockRewardIncentivePercent, {value}, 0, 100"):
        validator_set.updateParam('blockRewardIncentivePercent', hex_value)


@pytest.mark.parametrize("value", [0, 1, 10, 50, 98, 99])
def test_update_vote_reward_percent_success(validator_set, value):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(value), 64)
    validator_set.updateParam('voteRewardPercent', hex_value)
    assert validator_set.voteRewardPercent() == value


@pytest.mark.parametrize("value", [0, 1, 10, 50, 98, 99])
def test_update_block_reward_incentive_percent_success(validator_set, value):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(value), 64)
    validator_set.updateParam('blockRewardIncentivePercent', hex_value)
    assert validator_set.blockRewardIncentivePercent() == value


def test_update_param_success_with_key_blockRewardIncentivePercent():
    __update_gov_address()
    validator_set_instance.updateParam('blockRewardIncentivePercent',
                                       '0x0000000000000000000000000000000000000000000000000000000000000014')
    assert validator_set_instance.blockRewardIncentivePercent() == 20


def test_distribute_reward_failed_by_address_which_is_not_candidate():
    with brownie.reverts("the msg sender must be candidate contract"):
        validator_set_instance.distributeReward(0)
    __contract_check(0, init_validator_incomes)
    __balance_check()


def test_distribute_reward_success_with_empty_validators():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [], validator_count)
    validator_set_instance.distributeReward(7)
    __contract_check(0, init_validator_incomes)
    __balance_check()


def test_distribute_reward_success_with_validators_which_have_no_incomes(candidate_hub):
    __fake_validator_set()
    round_tag = candidate_hub.getRoundTag()
    validator_set_instance.distributeReward(round_tag)
    __contract_check(0, init_validator_incomes)
    __balance_check()


def test_distribute_reward_success_with_commissionThousandths_1000():
    __fake_validator_set()
    validator = validator_set_instance.currentValidatorSet(0).dict()
    blockRewardIncentivePercent = validator_set_instance.blockRewardIncentivePercent()
    value = 1000000000000000000
    validator_set_instance.deposit(init_validators[0], {'value': value})

    tx = validator_set_instance.distributeReward(0)
    expect_incentive = blockRewardIncentivePercent * value // 100
    expect_reward = value - expect_incentive

    expect_event(tx, "directTransfer", {
        'operateAddress': validator['operateAddress'],
        'validator': validator['feeAddress'],
        'amount': expect_reward,
        'totalReward': expect_reward
    })
    __contract_check(0, init_validator_incomes)
    __balance_check(0 - value, 0, expect_incentive, 0)
    assert brownie.web3.eth.get_balance(validator['feeAddress']) == expect_reward


def test_distribute_reward_success_with_commissionThousandths_500():
    __fake_validator_set()
    commission = 500
    value = 1000000000000000000
    blockRewardIncentivePercent = validator_set_instance.blockRewardIncentivePercent()
    expect_incentive = blockRewardIncentivePercent * value // 100
    expect_income = value - expect_incentive
    expect_reward = expect_income * commission // 1000

    validator = validator_set_instance.currentValidatorSet(0).dict()
    validator_set_instance.updateValidatorSet(
        [validator['operateAddress']],
        [validator['consensusAddress']],
        [validator['feeAddress']],
        [commission],
        [validator['voteAddr']],
        validator_count
    )

    validator_set_instance.deposit(init_validators[0], {'value': value})

    tx = validator_set_instance.distributeReward(1)

    expect_event(tx, "directTransfer", {
        'operateAddress': validator['operateAddress'],
        'validator': validator['feeAddress'],
        'amount': expect_reward,
        'totalReward': expect_income
    })
    __contract_check(0, [0])
    # in the event that there is a reward on the validator, but there is no staking, this part of the reward will be burned
    __balance_check(0 - value, 0, expect_incentive + expect_reward, 0)
    assert brownie.web3.eth.get_balance(validator['feeAddress']) == expect_reward


def test_distribute_vote_reward_success(validator_set, system_reward, deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators = []
    consensuses = []
    fee_address = accounts[6:9]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, fee_address=fee_address[index]))
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [10, 20, 30]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
        validator_set.vote(consensuses, weights, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(fee_address)
    block_reward = 30000
    tx = validator_set.distributeReward(8)
    receive_reward = block_reward * validator_set.blockRewardIncentivePercent() // 100
    expect_event(tx, "receiveDeposit", {
        'from': validator_set.address,
        'amount': receive_reward * len(operators)
    })
    assert system_reward_tracker.delta() == receive_reward * len(operators)
    validator_reward = (block_reward - receive_reward) // 2

    fee_amount = []
    for i in range(len(operators)):
        expect_event(tx, "directTransfer", {
            'operateAddress': operators[i],
            'validator': fee_address[i],
            'amount': validator_reward - (validator_reward * 10 // 100),
            'totalReward': block_reward - receive_reward
        }, idx=i)
        fee_amount.append(validator_reward - (validator_reward * 10 // 100))
    vote_reward = validator_reward * validator_set.voteRewardPercent() // 100 * 3
    vote_amount = [675, 1350, 2025]
    for i in range(len(operators)):
        expect_event(tx, "voteRewardTransfer", {
            'operateAddress': operators[i],
            'validator': fee_address[i],
            'amount': vote_reward * weights[i] // sum(weights)
        }, idx=i)
        assert vote_reward * weights[i] // sum(weights) == vote_amount[i]
        fee_amount[i] += vote_amount[i]
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == fee_amount[index]


def test_zero_vote_weight_sum_zero_reward_success(validator_set, system_reward, set_candidate, deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [0, 0, 0]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
        validator_set.vote(consensuses, weights, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(operators)
    income = 30000
    temp_income = income - (block_reward * validator_set.blockRewardIncentivePercent() // 100)
    tx = validator_set.distributeReward(get_current_round())
    assert 'voteRewardTransfer' not in tx.events
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == temp_income // 2


def test_distribute_reward_by_weight_proportion_success(validator_set, system_reward, set_candidate,
                                                        deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights0 = [10, 20, 90]
    weights1 = [25, 30, 40]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
    validator_set.vote(consensuses, weights0, {"from": accounts[99]})
    validator_set.vote(consensuses[:-1], weights1[:-1], {"from": accounts[99]})
    validator_set.vote(consensuses[:1], weights1[:1], {"from": accounts[99]})
    validator_set.vote(consensuses, weights1, {"from": accounts[99]})
    vote_weight = [85, 80, 130]
    for index, consensus in enumerate(consensuses):
        assert validator_set.getValidatorByConsensus(consensus).dict()['voteWeight'] == vote_weight[index]
    __fake_validator_set()
    trackers = get_trackers(operators)
    income = 30000
    temp_income = income - (block_reward * validator_set.blockRewardIncentivePercent() // 100)
    validator_reward = temp_income // 2
    vote_reward = validator_reward * validator_set.voteRewardPercent() // 100
    tx = validator_set.distributeReward(get_current_round())
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * vote_weight[index] // sum(vote_weight)
        assert tracker.delta() == validator_fee + vote_fee


def test_vote_reward_as_validator_portion_success(validator_set, system_reward, deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, commission=800))
        delegate_coin_success(operator, accounts[99], coin_value)
    weights0 = [10, 20, 50]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
    validator_set.vote(consensuses, weights0, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(operators)
    temp_income = block_reward - (block_reward * validator_set.blockRewardIncentivePercent() // 100)
    validator_reward = temp_income * 800 // 1000
    vote_reward = validator_reward * validator_set.voteRewardPercent() // 100
    validator_set.distributeReward(get_current_round())
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * weights0[index] // sum(weights0)
        assert tracker.delta() == validator_fee + vote_fee


@pytest.mark.parametrize("vote_reward_percent", [0, 10, 20, 50, 80, 99, 100])
def test_vote_reward_after_update_success(validator_set, set_candidate, vote_reward_percent, deposit_for_reward):
    hex_value = padding_left(Web3.to_hex(vote_reward_percent), 64)
    execute_proposal(
        validator_set.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['voteRewardPercent', Web3.to_bytes(hexstr=hex_value)]),
        "update felonyThreshold"
    )
    assert validator_set.getVoteRewardPercent() == vote_reward_percent
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [10, 20, 30]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
        validator_set.vote(consensuses, weights, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(operators)
    temp_income = block_reward - (block_reward * validator_set.blockRewardIncentivePercent() // 100)
    validator_reward = temp_income // 2
    vote_reward = validator_reward * vote_reward_percent // 100
    tx = validator_set.distributeReward(get_current_round())
    if vote_reward_percent == 0:
        assert 'voteRewardTransfer' not in tx.events
    else:
        assert 'voteRewardTransfer' in tx.events
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * weights[index] // sum(weights)
        assert tracker.delta() == validator_fee + vote_fee


def test_zero_weight_validator_gets_no_reward_success(validator_set, set_candidate, deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [0, 20, 30]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
        validator_set.vote(consensuses, weights, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(operators)
    validator_set.distributeReward(get_current_round())
    actual_validator_fee = [12150, 13770, 14580]
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == actual_validator_fee[index]


def test_vote_non_current_validator(validator_set, set_candidate, deposit_for_reward):
    coin_value = 10000
    validator_set.updateBlockReward(20000)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [0, 20, 30]
    turn_round()
    for consensus in consensuses:
        validator_set.deposit(consensus, {"value": 10000, "from": accounts[99]})
    consensus = register_candidate(operator=accounts[10])
    for i in range(10, 12):
        operators.append(accounts[i])
    consensuses.append(consensus)
    consensuses.append(accounts[11])
    weights.append(30)
    weights.append(50)
    validator_set.vote(consensuses, weights, {"from": accounts[99]})
    __fake_validator_set()
    trackers = get_trackers(operators)
    validator_set.distributeReward(get_current_round())
    actual_validator_fee = [12150, 13770, 14580, 0, 0]
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == actual_validator_fee[index]


def test_vote_weight_clears_next_round(validator_set, candidate_hub, set_candidate, deposit_for_reward):
    coin_value = 10000
    new_block_reward = 20000
    validator_set.updateBlockReward(new_block_reward)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [10, 20, 30]
    turn_round()
    trackers = get_trackers(operators)
    tx = turn_round(consensuses, weights=weights)
    total_reward = (new_block_reward + 100) * 90 // 100
    assert tx.events['directTransfer']['totalReward'] == total_reward
    validator_fee = total_reward // 2
    total_reward -= validator_fee
    assert tx.events['directTransfer']['amount'] == total_reward - total_reward * 10 // 100
    actual_validator_fee = [452, 904, 1356]
    for index, tracker in enumerate(trackers):
        assert tracker.delta() == (total_reward - total_reward * 10 // 100) + actual_validator_fee[index]
    tx = candidate_hub.turnRound()
    assert 'voteRewardTransfer' not in tx.events
    for consensus in consensuses:
        validator = validator_set.getValidatorByConsensus(consensus)
        assert validator['voteWeight'] == 0


def test_update_validator_fee_vote_reward(validator_set, candidate_hub, deposit_for_reward):
    coin_value = 10000
    new_block_reward = 20000
    validator_set.updateBlockReward(new_block_reward)
    operators = []
    consensuses = []
    commission_fee = [200, 500, 600]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, commission=commission_fee[index]))
        delegate_coin_success(operator, accounts[99], coin_value)
    weights = [10, 20, 30]
    turn_round()
    total_reward = 30000 * 90 // 100
    vote_fee = []
    for i in range(len(operators)):
        vote_fee.append(total_reward * commission_fee[i] // 1000)
    total_vote_reward = 0
    tx = turn_round(consensuses, weights=weights, tx_fee=10000)
    for i in range(len(operators)):
        amount = vote_fee[i] * 90 // 100
        expect_event(tx, 'directTransfer', {
            'amount': amount
        }, idx=i)
        total_vote_reward += vote_fee[i] - amount
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': total_vote_reward * weights[i] // sum(weights)
        }, idx=i)


def test_vote_no_stake_calculation(validator_set, set_candidate, candidate_hub, deposit_for_reward):
    new_block_reward = 20000
    validator_set.updateBlockReward(new_block_reward)
    operators, consensuses = set_candidate
    weights = [10, 20, 30]
    turn_round()
    tx = turn_round(consensuses, weights=weights)
    total_reward = (new_block_reward + 100) * 90 // 100 * 10 // 100 * 3
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': total_reward * weights[i] // sum(weights)
        }, idx=i)


def test_single_vote_distribution(validator_set, candidate_hub, set_candidate, deposit_for_reward):
    new_block_reward = 20000
    delegate_amount = 10000
    validator_set.updateBlockReward(new_block_reward)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], delegate_amount)
    weights = [10, 20, 30]
    turn_round()
    for miner in consensuses:
        validator_set.deposit(miner, {"value": 10000, "from": accounts[99]})
    validator_set.vote(consensuses, weights, {"from": accounts[99]})
    tx = candidate_hub.turnRound()
    vote_amount = [675, 1350, 2025]
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': vote_amount[i]
        }, idx=i)
    turn_round(consensuses)


def test_vote_new_validator_added(validator_set, candidate_hub, set_candidate, deposit_for_reward):
    new_block_reward = 20000
    delegate_amount = 10000
    validator_set.updateBlockReward(new_block_reward)
    weights = [10, 20, 30]
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], delegate_amount)
    turn_round()
    consensuses.append(register_candidate(operator=accounts[10]))
    operators.append(accounts[10])
    delegate_coin_success(accounts[10], accounts[99], delegate_amount - 1)
    weights.append(30)
    tx = turn_round(consensuses, weights=weights, round_count=2, tx_fee=10000)
    total_vote_fee = 5400
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': total_vote_fee * weights[i] // sum(weights)
        }, idx=i)


def test_vote_large_weight_gap(validator_set, set_candidate, deposit_for_reward):
    new_block_reward = 20000
    delegate_amount = 10000
    validator_set.updateBlockReward(new_block_reward)
    weights = [1, 1000000, 1000000]
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], delegate_amount)
    turn_round()
    tx = turn_round(consensuses, weights=weights, tx_fee=10000)
    total_vote_fee = 4050
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': total_vote_fee * weights[i] // sum(weights)
        }, idx=i)
    turn_round(consensuses)


def test_zero_vote_and_percent(validator_set, candidate_hub, set_candidate):
    hex_value = padding_left(Web3.to_hex(0), 64)
    execute_proposal(
        validator_set.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['voteRewardPercent', Web3.to_bytes(hexstr=hex_value)]),
        "update felonyThreshold"
    )
    assert validator_set.getVoteRewardPercent() == 0
    new_block_reward = 20000
    delegate_amount = 10000
    validator_set.updateBlockReward(new_block_reward)
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], delegate_amount)
    turn_round()
    for miner in consensuses:
        validator_set.deposit(miner, {"value": 10000, "from": accounts[99]})
    tx = candidate_hub.turnRound()
    assert 'voteRewardTransfer' not in tx.events
    turn_round(consensuses)


def test_vote_reward_percent_max(validator_set, set_candidate, deposit_for_reward):
    hex_value = padding_left(Web3.to_hex(100), 64)
    execute_proposal(
        validator_set.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['voteRewardPercent', Web3.to_bytes(hexstr=hex_value)]),
        "update felonyThreshold"
    )
    new_block_reward = 20000
    delegate_amount = 10000
    validator_set.updateBlockReward(new_block_reward)
    weights = [30, 50, 70]
    operators, consensuses = set_candidate
    for operator in operators:
        delegate_coin_success(operator, accounts[99], delegate_amount)
    turn_round()
    validator_set.vote(consensuses, weights, {"from": accounts[99]})
    tx = turn_round(consensuses, weights=weights, tx_fee=10000)
    total_vote_fee = 13500 * 3
    for i in range(len(operators)):
        expect_event(tx, 'voteRewardTransfer', {
            'amount': total_vote_fee * weights[i] // sum(weights)
        }, idx=i)
    turn_round(consensuses)


def test_misdemeanor_failed_with_address_which_is_not_slash():
    with brownie.reverts("the msg sender must be slash contract"):
        validator_set_instance.misdemeanor(init_validators[0])


def test_misdemeanor_failed_with_after_set_empty_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [], validator_count)
    __update_slash_address()
    validator = validator_set_instance.getValidatorByConsensus(init_validators[0]).dict()
    tx = validator_set_instance.misdemeanor(init_validators[0])
    expect_event(tx, "validatorMisdemeanor", {
        "validator": validator['operateAddress'],
        "amount": 0
    })


def test_misdemeanor_return_empty_with_empty_validator_set_and_ZERO_ADDRESS():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [], validator_count)
    __update_slash_address()
    assert validator_set_instance.misdemeanor.call(ZERO_ADDRESS) == ()


def test_misdemeanor_return_empty_with_only_one_validator_set_and_0_income():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()], validator_count)
    __update_slash_address()
    assert validator_set_instance.misdemeanor.call(init_validators[0]) == ()
    __contract_check(0, [0])


def test_misdemeanor_return_empty_with_only_one_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()], validator_count)

    deposit_value = 1000000000
    expect_event(validator_set_instance.deposit(init_validators[0], {'value': deposit_value}), "validatorDeposit", {
        "amount": deposit_value,
        "validator": init_validators[0]
    })
    __update_slash_address()
    assert validator_set_instance.misdemeanor.call(init_validators[0]) == ()
    __contract_check(deposit_value, [deposit_value])


def test_misdemeanor_success_0_income():
    __update_slash_address()
    validator_set_instance.misdemeanor.call(init_validators[0])
    __contract_check(0, init_validator_incomes)


def test_misdemeanor_success():
    __fake_validator_set()
    deposit_value = 1000000000
    average_value = deposit_value // (len(init_validators) - 1)
    expect_event(validator_set_instance.deposit(init_validators[2], {'value': deposit_value}), "validatorDeposit", {
        "amount": deposit_value,
        "validator": init_validators[2]
    })
    __update_slash_address()
    validator_set_instance.misdemeanor(init_validators[2])
    __contract_check(deposit_value, [average_value, average_value, 0, average_value, average_value])
    __balance_check(0 - deposit_value, deposit_value, 0, 0)


def test_felony_failed_with_address_which_is_not_slash():
    with brownie.reverts("the msg sender must be slash contract"):
        validator_set_instance.felony(init_validators[0], felony_round, felony_deposit)


def test_misdemeanor_return_empty_with_ZERO_ADDRESS_validator():
    __update_slash_address()
    assert validator_set_instance.felony.call(ZERO_ADDRESS, felony_round, felony_deposit) == ()


def test_felony_failed_with_one_validator_which_has_0_income():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()], validator_count)
    __update_slash_address()
    assert validator_set_instance.felony.call(init_validators[0], felony_round, felony_deposit) == ()
    __contract_check(0, [0])


def test_felony_failed_with_one_validator_which_has_income():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()], validator_count)
    deposit_value = 1000000000
    validator_set_instance.deposit(init_validators[0], {'value': deposit_value})
    __update_slash_address()
    assert validator_set_instance.felony.call(init_validators[0], felony_round, felony_deposit) == ()
    validator_set_instance.felony(init_validators[0], felony_round, felony_deposit)
    __contract_check(deposit_value, [0])
    __balance_check(0 - deposit_value, deposit_value, 0, 0)


def test_felony_success_with_validator_set_which_has_0_income(candidate_hub):
    candidate_hub.register(accounts[0], accounts[0], 100, random_vote_address(),
                           {'from': accounts[0], 'value': Web3.to_wei(20000, 'ether')})
    candidate_hub.register(accounts[1], accounts[1], 100, random_vote_address(),
                           {'from': accounts[1], 'value': Web3.to_wei(20000, 'ether')})
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([accounts[0], accounts[1]], [accounts[0], accounts[1]],
                                              [accounts[0], accounts[1]], [100, 100],
                                              [random_vote_address(), random_vote_address()], validator_count)

    __update_slash_address()
    candidate = candidate_hub.candidateSet(0).dict()
    tx = validator_set_instance.felony(accounts[0], felony_round, felony_deposit)
    expect_event(tx, 'validatorFelony', {'validator': accounts[0], 'amount': 0})
    total_margin = Web3.to_wei(20000, 'ether') - felony_deposit

    set_jail = candidate_hub.SET_JAIL()
    set_margin = candidate_hub.SET_MARGIN()
    status = candidate['status'] | set_jail

    expect_event(tx, "deductedMargin", {
        "operateAddr": accounts[0],
        "margin": felony_deposit,
        "totalMargin": total_margin
    })
    expect_event(tx, "statusChanged", {
        "operateAddr": accounts[0],
        "oldStatus": candidate['status'],
        "newStatus": status | set_margin if total_margin < candidate_hub.requiredMargin() else status
    })
    __contract_check(0, [0])


def test_felony_success_with_validator_set_which_has_income(candidate_hub):
    candidate_hub.register(accounts[0], accounts[0], 100, random_vote_address(),
                           {'from': accounts[0], 'value': Web3.to_wei(20000, 'ether')})
    candidate_hub.register(accounts[1], accounts[1], 100, random_vote_address(),
                           {'from': accounts[1], 'value': Web3.to_wei(20000, 'ether')})
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([accounts[0], accounts[1]], [accounts[0], accounts[1]],
                                              [accounts[0], accounts[1]], [100, 100],
                                              [random_vote_address(), random_vote_address()], validator_count)

    __update_slash_address()
    deposit_value = 1000000000
    average_value = deposit_value / 1
    validator_set_instance.deposit(accounts[0], {'value': deposit_value})

    candidate = candidate_hub.candidateSet(0).dict()
    tx = validator_set_instance.felony(accounts[0], felony_round, felony_deposit)
    expect_event(tx, "validatorFelony", {'validator': accounts[0], "amount": deposit_value})

    total_margin = Web3.to_wei(20000, 'ether') - felony_deposit

    set_jail = candidate_hub.SET_JAIL()
    set_margin = candidate_hub.SET_MARGIN()
    status = candidate['status'] | set_jail

    expect_event(tx, "deductedMargin", {
        "operateAddr": accounts[0],
        "margin": felony_deposit,
        "totalMargin": total_margin
    })
    expect_event(tx, "statusChanged", {
        "operateAddr": accounts[0],
        "oldStatus": candidate['status'],
        "newStatus": status | set_margin if total_margin < candidate_hub.requiredMargin() else status
    })
    __contract_check(deposit_value, [average_value])
    __balance_check((deposit_value + Web3.to_wei(20000, 'ether')) * -1, deposit_value, felony_deposit, 0)


def test_subsidy_reduce():
    validator_set_instance.updateBlockReward(BLOCK_REWARD)
    validator_set_instance.updateSubsidyReduceInterval(3)
    reduce_interval = validator_set_instance.SUBSIDY_REDUCE_INTERVAL()
    chain.mine(reduce_interval - chain.height % reduce_interval - 1)
    validator_set_instance.deposit(ZERO_ADDRESS, {'value': 1})
    assert validator_set_instance.blockReward() == validator_set_instance.BLOCK_REWARD() * validator_set_instance.REDUCE_FACTOR() // 10000


def test_subsidy_reduce_for_81_times():
    block_reward = validator_set_instance.BLOCK_REWARD()
    for _ in range(81):
        block_reward = block_reward * validator_set_instance.REDUCE_FACTOR() // 10000

    validator_set_instance.updateBlockReward(BLOCK_REWARD)
    validator_set_instance.updateSubsidyReduceInterval(3)
    reduce_interval = validator_set_instance.SUBSIDY_REDUCE_INTERVAL()
    chain.mine(reduce_interval - chain.height % reduce_interval - 1)
    validator_set_instance.deposit(ZERO_ADDRESS, {'value': 1})
    for _ in range(80):
        chain.mine(reduce_interval - 1)
        validator_set_instance.deposit(ZERO_ADDRESS, {'value': 1})
    assert validator_set_instance.blockReward() == block_reward


def test_validator_contract_receive_ether(validator_set):
    transfer_amount = 1000000
    tracker0 = get_tracker(accounts[0])
    tx = accounts[0].transfer(validator_set.address, transfer_amount)
    assert "received" in tx.events
    event = tx.events['received'][-1]
    assert event['from'] == accounts[0].address
    assert event['amount'] == transfer_amount
    assert tracker0.delta() == 0 - transfer_amount
    tx1 = accounts[0].transfer(validator_set.address, 0)
    assert "received" not in tx1.events
    assert tracker0.delta() == 0


# exitMaintenanceTurnRound
def test_revert_when_not_candidate_exit_maintenance_turn_round(validator_set):
    with brownie.reverts("the msg sender must be candidate contract"):
        validator_set.exitMaintenanceTurnRound()


def test_exit_maintenance_turn_round_no_maintenance_success(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()

    for i in range(len(operators)):
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] == 0

    turn_round()

    for i in range(len(operators)):
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] == 0


def test_exit_maintenance_turn_round_with_maintenance_success(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.enterMaintenance({'from': operators[1]})
    validator0 = validator_set.getValidatorByConsensus(consensuses[0])
    validator1 = validator_set.getValidatorByConsensus(consensuses[1])
    assert validator0['enterMaintenanceHeight'] != 0
    assert validator1['enterMaintenanceHeight'] != 0
    turn_round(chain_get_validator_consensus())
    for i in range(len(operators)):
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] == 0


@pytest.mark.parametrize("block_count", [20, 100])
def test_exit_maintenance_turn_round_with_maintenance_slash(validator_set, candidate_hub, block_count,
                                                            set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.enterMaintenance({'from': operators[1]})
    chain.mine(block_count)
    tx = turn_round(chain_get_validator_consensus())
    if block_count == 20:
        assert 'validatorMisdemeanor' in tx.events
    else:
        assert 'validatorFelony' in tx.events
    for i in range(len(operators[:2])):
        if block_count == 20:
            validator = validator_set.getValidatorByConsensus(consensuses[i])
            assert validator['enterMaintenanceHeight'] == 0
        else:
            with brownie.reverts("no match validator"):
                validator_set.getValidatorByConsensus(consensuses[i])


def test_exit_maintenance_turn_round_slash_then_exit(validator_set, slash_indicator, candidate_hub,
                                                     set_candidate_maintenance):
    accounts[99].transfer(candidate_hub.address, Web3.to_wei(1, 'ether'))
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_indicator.slash(consensuses[0], {'from': accounts[0]})
    slash_indicator.slash(consensuses[0], {'from': accounts[0]})
    assert slash_indicator.indicators(consensuses[0])['count'] == 2
    slash_indicator.setFelonyThreshold(8)
    chain.mine(24)
    tx = turn_round(chain_get_validator_consensus())
    expect_event(tx, "validatorSlashed", {
        "validator": consensuses[0],
        'blockCount': 3
    })
    assert 'validatorMisdemeanor' in tx.events

    slash_indicator.slash(consensuses[1], {'from': accounts[1]})
    slash_indicator.slash(consensuses[1], {'from': accounts[1]})
    chain.mine(60)
    tx = validator_set.exitMaintenanceTurnRound(
        {'from': candidate_hub.address})
    expect_event(tx, "validatorSlashed", {
        "validator": consensuses[1],
        'blockCount': 6
    })
    assert 'validatorFelony' in tx.events


def test_slash_during_maintenance(validator_set, slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    for i in range(2):
        slash_indicator.slash(consensuses[0], {'from': accounts[0]})
    for i in range(2):
        slash_indicator.slash(consensuses[0], {'from': accounts[0]})
    for i in range(2):
        slash_indicator.slash(consensuses[1], {'from': accounts[0]})
    tx = turn_round(consensuses)
    assert 'validatorMisdemeanor' not in tx.events
    assert 'validatorFelony' not in tx.events
    with brownie.reverts("no match validator"):
        validator = validator_set.getValidatorByConsensus(consensuses[0])
    validator = validator_set.getValidatorByConsensus(consensuses[1])
    assert validator['enterMaintenanceHeight'] == 0
    turn_round(consensuses)


@pytest.mark.parametrize("operator_index", [-1, -2])
def test_validator_apply_maintenance_success(validator_set, set_candidate_maintenance, operator_index, candidate_hub):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    tx1 = validator_set.enterMaintenance({'from': operators[operator_index]})
    validator_last = validator_set.getValidatorByConsensus(consensuses[operator_index])
    assert validator_last['enterMaintenanceHeight'] != 0
    assert 'validatorEnterMaintenance' in tx1.events
    tx2 = validator_set.enterMaintenance({'from': operators[0]})
    validator_first = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator_first['enterMaintenanceHeight'] != 0
    assert 'validatorEnterMaintenance' in tx2.events
    chain.mine(300)
    tx = turn_round(consensuses)
    with brownie.reverts("no match validator"):
        validator_set.getValidatorByConsensus(consensuses[operator_index])


@pytest.mark.parametrize("maintain_index", [
    [0],
    [0, 1, 2],
    [0, 1, -1, 2, -3],
    [0, 1, 2, 3, 4, 5, 6],
    [0, 8, 9, 10],
    [0, 10, 11],
    [1, -2, -1, -3],
    [-1, 1, 0, -3],
    [0, -1, 1, -2, 3, -3, 4, -4],
]
                         )
def test_multiple_validators_multiple_candidates_exit_maintenance(validator_set, candidate_hub, maintain_index):
    candidate_hub.setMaxAlternateCount(9)
    candidate_hub.setValidatorCount(11)
    operators = []
    consensuses = []
    for operator in accounts[5:25]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for operator in operators[:10]:
        delegate_coin_success(operator, accounts[0], 1e18)
        delegate_coin_success(operator, accounts[1], 1e18)
    turn_round()
    for i in maintain_index:
        tx = validator_set.enterMaintenance({'from': operators[i]})
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] != 0
        assert 'validatorEnterMaintenance' in tx.events
    chain.mine(300)
    tx = turn_round(consensuses)
    maintain_address = []
    for i in maintain_index:
        maintain_address.append(consensuses[i])
        with brownie.reverts("no match validator"):
            validator_set.getValidatorByConsensus(consensuses[i])
    for consensus in consensuses:
        if consensus not in maintain_address:
            validator = validator_set.getValidatorByConsensus(consensus)
            assert validator['enterMaintenanceHeight'] == 0
            assert validator['consensusAddress'] == consensus
    turn_round(consensuses)


def test_exit_maintenance_with_rejected_and_queued_delegations(validator_set, slash_indicator, candidate_hub,
                                                               set_candidate_maintenance):
    slash_indicator.setFelonyThreshold(100)
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[3], accounts[1], 10000)
    delegate_coin_success(operators[4], accounts[2], 9999)
    candidate_hub.setValidatorCount(3)
    candidate_hub.setMaxAlternateCount(2)
    turn_round()
    enter_maintenance(operators[0])
    slash_validator(consensuses[2])
    slash_validator(consensuses[1], 'minor')
    refuse_delegate(operators[3])
    refuse_delegate(operators[0])
    working_validators = chain_get_validator_consensus()
    assert len(working_validators) == 3
    for consensus in working_validators:
        assert consensus in [consensuses[1], consensuses[3], consensuses[4]]
    tx = turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[0])
    working_validators = chain_get_validator_consensus()
    assert len(working_validators) == 2
    for consensus in working_validators:
        assert consensus in [consensuses[1], consensuses[4]]


def test_exit_and_reenter_maintenance_then_exit_again(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    enter_maintenance(operators[0])
    chain.mine(20)
    turn_round(chain_get_validator_consensus())
    enter_maintenance(operators[0])
    chain.mine(10)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[0])
    turn_round(chain_get_validator_consensus())


def test_turn_round_with_validator_count_zero_and_various_operations(validator_set, candidate_hub, slash_indicator):
    delegate_amount = 10000
    start_count = 10
    operators = []
    consensuses = []
    for i, operator in enumerate(accounts[start_count:start_count + 12]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
        delegate_coin_success(operator, accounts[0], delegate_amount - i)
    candidate_hub.setValidatorCount(6)
    candidate_hub.setMaxAlternateCount(0)
    turn_round()
    validator_set.setValidatorCount(0)
    expect_validator_consensus(consensuses[:6])
    tx = slash_validator(consensuses[0], slash_type='minor')
    assert 'validatorMisdemeanor' in tx.events
    assert 'validatorEnterMaintenance' not in tx.events
    tx = slash_validator(consensuses[1], slash_type='felony')
    assert 'validatorFelony' in tx.events
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[2])
    candidate_hub.unregister({'from': operators[-1]})
    refuse_delegate(operators[4])
    expect_validator_consensus([consensuses[0], consensuses[2], consensuses[3], consensuses[4], consensuses[5]])
    turn_round(chain_get_validator_consensus())
    expect_validator_consensus(
        [consensuses[0], consensuses[2], consensuses[3], consensuses[5], consensuses[6], consensuses[7]])
    stake_hub_claim_reward(accounts[0])
    turn_round(chain_get_validator_consensus())


# enterMaintenance
def test_enter_maintenance_non_validator():
    with brownie.reverts("not a validator"):
        validator_set_instance.enterMaintenance({'from': accounts[99]})


def test_enter_maintenance_success(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    candidate_hub.setValidatorCount(2)
    for operator in operators[:2]:
        delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 3
    tx = validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    expect_event(tx, "validatorEnterMaintenance", {
        'validator': consensuses[0]
    })


def test_enter_maintenance_already_in_maintenance(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    for operator in operators[:3]:
        delegate_coin_success(operator, accounts[0], 1e18)
    candidate_hub.setValidatorCount(3)
    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 5
    validator_set.enterMaintenance({'from': operators[0]})
    assert validator_set.currentValidatorSet(0)['enterMaintenanceHeight'] != 0
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[0]})


def test_enter_maintenance_multiple_validators(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    for i in range(len(operators[:2])):
        tx = validator_set.enterMaintenance({'from': operators[i]})
        expect_event(tx, "validatorEnterMaintenance", {
            'validator': consensuses[i]
        })
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] != 0


def test_enter_maintenance_after_exit(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    candidate_hub.setValidatorCount(2)
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})

    __fake_validator_set()
    validator_set.exitMaintenanceTurnRound()

    tx = validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    expect_event(tx, "validatorEnterMaintenance", {
        'validator': consensuses[0]
    })


def test_revert_when_single_validator_enter_maintenance(validator_set, candidate_hub):
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)

    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 1

    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operator})


def test_revert_when_notenoughalternates_entermaintenance(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(3)
    operators, consensuses = set_candidate_maintenance
    for operator in operators[:3]:
        delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 5
    for i in range(len(operators[:2])):
        validator_set.enterMaintenance({'from': operators[i]})
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] != 0
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[2]})
    turn_round(consensuses)


def test_revert_when_already_misdemeanor_enter_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_threshold = slash_indicator.misdemeanorThreshold()
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx1.events
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[0]})


def test_revert_when_already_felony_enter_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_threshold = slash_indicator.felonyThreshold()
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx1.events
    with brownie.reverts("not a validator"):
        validator_set.enterMaintenance({'from': operators[0]})


def test_misdemeanor_apply_maintenance(validator_set, candidate_hub, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    candidate_hub.setValidatorCount(5)
    turn_round()
    slash_threshold = slash_indicator.misdemeanorThreshold()
    for count in range(slash_threshold):
        tx1 = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx1.events
    assert 'validatorEnterMaintenance' not in tx1.events
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] == 0
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[0]})

    turn_round(consensuses)


def test_alternate_validator_apply_maintenance_success(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[4]})
    tx = validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    assert 'validatorEnterMaintenance' in tx.events
    chain.mine(300)
    turn_round(consensuses)


def test_revert_when_candidate_apply_maintenance_rejected(validator_set, set_candidate_maintenance, candidate_hub):
    operators, consensuses = set_candidate_maintenance
    candidate_hub.setMaxAlternateCount(0)
    turn_round()
    with brownie.reverts("not a validator"):
        validator_set.enterMaintenance({'from': operators[-1]})


def test_enter_maintenance_when_get_working_count_zero(validator_set, candidate_hub, set_candidate_maintenance,
                                                       slash_indicator):
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[0], accounts[0], 1000)
    candidate_hub.setValidatorCount(1)
    candidate_hub.setMaxAlternateCount(0)
    # If only one validator, felony does not remove it.
    slash_threshold = slash_indicator.felonyThreshold()
    for _ in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' not in tx.events

    turn_round()
    assert validator_set.getWorkingCount() == 1
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[0]})
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[0])


def test_slash_accumulates_during_and_after_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[0], accounts[0], 1e18)
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0

    tx = slash_indicator.slash(consensuses[0])
    tx = slash_indicator.slash(consensuses[0])
    chain.mine(21)
    indicators = slash_indicator.getIndicators()
    tx2 = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorFelony' in tx2.events
    assert tx2.events['validatorSlashed']['blockCount'] == 2


def test_working_count_excludes_felony_validators(validator_set, candidate_hub, set_candidate_maintenance,
                                                  slash_indicator):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round(consensuses)
    initial_working_count = validator_set.getWorkingCount()
    assert initial_working_count == 5
    enter_maintenance(operators[0])
    enter_maintenance(operators[1])
    slash_threshold = slash_indicator.felonyThreshold()
    for _ in range(slash_threshold):
        slash_indicator.slash(consensuses[2])
        slash_indicator.slash(consensuses[1])
        slash_indicator.slash(consensuses[4])
    tx = exit_maintenance(operators[0])
    assert tx.events['validatorSlashed']['blockCount'] == 2


def test_upgrade_validator_cannot_enter_maintenance(validator_set, slash_indicator, candidate_hub,
                                                    set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.setValidatorCount(0)
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operators[0]})
    slash_threshold = slash_indicator.misdemeanorThreshold()
    for i in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    assert 'validatorEnterMaintenance' not in tx.events
    turn_round(consensuses)


def test_maintenance_with_less_alternate(validator_set, candidate_hub):
    candidate_hub.setValidatorCount(4)
    candidate_hub.setMaxAlternateCount(5)
    operators = []
    consensuses = []
    for i in range(5):
        operators.append(accounts[i])
        consensuses.append(register_candidate(operator=accounts[i]))
    turn_round()
    enter_maintenance(operators[0])
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[1])
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[2])
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[3])
    turn_round(chain_get_validator_consensus())
    enter_maintenance(operators[1])
    turn_round(chain_get_validator_consensus())
    enter_maintenance(operators[2])
    turn_round(chain_get_validator_consensus())
    enter_maintenance(operators[3])


def test_delegate_and_transfer_during_maintenance(validator_set, candidate_hub, set_candidate_maintenance):
    stake_manager = StakeManager()
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    operators, consensuses = set_candidate_maintenance
    turn_round()
    operator = operators[0]
    delegator = accounts[20]
    btc_delegator = accounts[21]
    delegate_amount = 100000
    btc_amount = 1000
    tx = validator_set.enterMaintenance({'from': operator})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    delegate_coin_success(operator, delegator, delegate_amount)
    txid = delegate_btc_success(operator, btc_delegator, btc_amount, LOCK_SCRIPT, relay=btc_delegator)
    transfer_coin_success(operator, operators[1], delegator, delegate_amount // 2)
    transfer_btc_success(txid, operators[2], btc_delegator)
    undelegate_coin_success(operator, delegator, delegate_amount // 4)
    delegate_coin_success(operator, delegator, delegate_amount // 10)
    txid2 = delegate_btc_success(operator, btc_delegator, btc_amount // 10, LOCK_SCRIPT, relay=btc_delegator)
    transfer_coin_success(operator, operators[1], delegator, delegate_amount // 20)
    transfer_btc_success(txid2, operators[2], btc_delegator)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(delegator)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(delegator)
    turn_round(chain_get_validator_consensus())


def test_validator_with_no_delegation_cannot_enter_maintenance(validator_set, candidate_hub, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    candidate_hub.refuseDelegate({'from': operators[0]})

    validator_set.enterMaintenance({'from': operators[0]})

    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0


def test_new_validator_apply_maintenance_success(validator_set, set_candidate_maintenance, candidate_hub):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    operator = accounts[12]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)
    with brownie.reverts("not a validator"):
        validator_set.enterMaintenance({'from': operator})


# exitMaintenance
def test_maintenance_state_check_success(validator_set, set_candidate_maintenance):
    validator_set.setMaintainSlashPercent(30)
    operators, consensuses = set_candidate_maintenance
    for operator in operators[:3]:
        delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] == 0

    validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    maintenance_height = validator['enterMaintenanceHeight']
    assert maintenance_height != 0
    chain.mine(105)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    with brownie.reverts('no match validator'):
        validator_set.getValidatorByConsensus(consensuses[0])
    expect_event(tx, "validatorExitMaintenance", {
        'validator': consensuses[0]
    })
    assert 'validatorFelony' in tx.events
    expect_event(tx, "validatorSlashed", {
        'validator': consensuses[0],
        'blockCount': 10
    })


def test_exitmaintenance_success(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.deposit(consensuses[0], {"value": 100, "from": accounts[99]})
    validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    chain.mine(40)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] == 0
    expect_event(tx, "validatorExitMaintenance", {
        'validator': consensuses[0]
    })
    expect_event(tx, "validatorSlashed", {
        'validator': consensuses[0],
        'blockCount': 3
    })
    expect_event(tx, "validatorMisdemeanor", {
        'amount': 100
    })
    turn_round(consensuses)


def test_revert_when_notvalidator_exitmaintenance(validator_set):
    with brownie.reverts("not a validator"):
        validator_set.exitMaintenance({'from': accounts[99]})


def test_revert_when_notinmaintenance_exitmaintenance(validator_set, set_candidate):
    operators, consensuses = set_candidate
    turn_round()

    with brownie.reverts("not in Temporary Maintenance"):
        validator_set.exitMaintenance({'from': operators[0]})


def test_revert_when_alreadyexited_exitmaintenance(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})

    validator_set.exitMaintenance({'from': operators[0]})

    with brownie.reverts("not in Temporary Maintenance"):
        validator_set.exitMaintenance({'from': operators[0]})


def test_success_multiple_validators_exitmaintenance(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    for i in range(2):
        validator_set.enterMaintenance({'from': operators[i]})

    for i in range(2):
        tx = validator_set.exitMaintenance({'from': operators[i]})
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] == 0
        expect_event(tx, "validatorExitMaintenance", {
            'validator': consensuses[i]
        })


def test_revert_when_removedvalidator_exitmaintenance(validator_set, candidate_hub, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})

    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})

    with brownie.reverts("not a validator"):
        validator_set.exitMaintenance({'from': operators[0]})


def test_revert_when_previous_felony_exit_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    slash_threshold = slash_indicator.felonyThreshold()
    for _ in range(slash_threshold):
        slash_indicator.slash(consensuses[0])
    with brownie.reverts("not a validator"):
        validator_set.exitMaintenance({'from': operators[0]})


def test_second_misdemeanor_after_exit(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.deposit(consensuses[0], {"value": 100, "from": accounts[99]})
    slash_threshold = slash_indicator.misdemeanorThreshold()
    for _ in range(slash_threshold):
        tx = slash_indicator.slash(consensuses[0])
    slash_indicator.setMisdemeanorThreshold(1)
    assert tx.events['validatorMisdemeanor']['amount'] == 100
    assert 'validatorEnterMaintenance' in tx.events
    validator_set.deposit(consensuses[0], {"value": 1000, "from": accounts[99]})
    chain.mine(13)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorMisdemeanor' in tx.events
    assert tx.events['validatorMisdemeanor']['amount'] == 1000
    tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events
    turn_round(consensuses)


def test_revert_when_previous_slash_and_missed_blocks(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_indicator.slash(consensuses[0])
    tx = validator_set.enterMaintenance({'from': operators[0]})
    chain.mine(15)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorMisdemeanor' in tx.events
    slash_indicator.slash(consensuses[0])
    tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events
    turn_round(consensuses)


def test_slash_count_after_percent_change(validator_set, set_candidate_maintenance):
    operators, _ = set_candidate_maintenance
    turn_round()
    validator_set.setMaintainSlashPercent(50)
    validator_set.enterMaintenance({'from': operators[0]})
    chain.mine(100)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert tx.events['validatorSlashed']['blockCount'] == 16


def test_no_slash_when_maintain_slash_percent_zero(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.setMaintainSlashPercent(0)
    validator_set.enterMaintenance({'from': operators[0]})
    chain.mine(2000)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorSlashed' not in tx.events
    assert 'validatorMisdemeanor' not in tx.events
    assert 'validatorFelony' not in tx.events


def test_clear_unpunished_blocks_in_maintenance(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator_set.enterMaintenance({'from': operators[0]})
    chain.mine(1)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorSlashed' not in tx.events


def test_slash_count_exclude_maintenance_validators(validator_set, slash_indicator, candidate_hub,
                                                    set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_indicator.slash(consensuses[0])
    tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    assert 'validatorEnterMaintenance' in tx.events
    validator_set.setValidatorCount(21)
    chain.mine(100)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert tx.events['validatorSlashed']['blockCount'] == 100 // 5 * 30 / 100
    turn_round(consensuses)


def test_felony_after_misdemeanor_in_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    misdemeanor_threshold = slash_indicator.misdemeanorThreshold()
    for _ in range(misdemeanor_threshold):
        slash_indicator.slash(consensuses[0])
    for _ in range(misdemeanor_threshold):
        slash_indicator.slash(consensuses[0])
    with brownie.reverts("not a validator"):
        tx = validator_set.exitMaintenance({'from': operators[0]})


def test_misdemeanor_to_felony_then_exit_maintenance(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    misdemeanor_threshold = slash_indicator.misdemeanorThreshold()
    for _ in range(misdemeanor_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    assert 'validatorEnterMaintenance' in tx.events
    for _ in range(misdemeanor_threshold):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events
    with brownie.reverts("not a validator"):
        validator_set.exitMaintenance({'from': operators[0]})
    tx = turn_round(consensuses)
    assert len(tx.events['roundReward']) == 3


def test_misdemeanor_with_missed_blocks(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.deposit(consensuses[0], {"value": 1000, "from": accounts[99]})
    for _ in range(slash_indicator.misdemeanorThreshold()):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    assert 'validatorEnterMaintenance' in tx.events
    slash_indicator.setFelonyThreshold(5)
    slash_indicator.slash(consensuses[0])
    slash_indicator.slash(consensuses[0])
    chain.mine(10)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorFelony' in tx.events
    turn_round(consensuses)


def test_revert_when_maintenance_then_felony(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    for _ in range(slash_indicator.felonyThreshold()):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events

    with brownie.reverts("not a validator"):
        validator_set.exitMaintenance({'from': operators[0]})


def test_maintenance_then_misdemeanor_exit(validator_set, set_candidate_maintenance, slash_indicator):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.deposit(consensuses[0], {"value": 1000, "from": accounts[99]})
    for _ in range(slash_indicator.misdemeanorThreshold()):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorMisdemeanor' in tx.events
    tx = validator_set.exitMaintenance({'from': operators[0]})
    assert 'validatorExitMaintenance' in tx.events
    turn_round(consensuses)


@pytest.mark.parametrize("blcok", [50, 100])
def test_slash_then_maintenance_then_felony(validator_set, set_candidate_maintenance, slash_indicator, blcok):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    slash_indicator.setFelonyThreshold(10)
    slash_indicator.setMisdemeanorThreshold(5)

    validator_set.deposit(consensuses[0], {"value": 1000, "from": accounts[99]})
    slash_indicator.slash(consensuses[0])
    slash_indicator.slash(consensuses[0])
    validator_set.enterMaintenance({'from': operators[0]})
    chain.mine(blcok)
    tx = validator_set.exitMaintenance({'from': operators[0]})
    if blcok == 100:
        assert 'validatorFelony' in tx.events
    else:
        assert 'validatorMisdemeanor' in tx.events
    turn_round(consensuses)


# canEnterMaintenance
def test_can_enter_maintenance_normal_case(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    index = validator_set.getValidatorIndexFromOps(operators[0])
    assert validator_set.canEnterMaintenance(index)


def test_revert_when_already_in_maintenance(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    index = validator_set.getValidatorIndexFromOps(operators[0])
    assert not validator_set.canEnterMaintenance(index)


def test_revert_when_single_validator(validator_set, candidate_hub):
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()

    index = validator_set.getValidatorIndexFromOps(operator)
    assert not validator_set.canEnterMaintenance(index)


def test_revert_when_working_count_insufficient(validator_set, candidate_hub, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    candidate_hub.setValidatorCount(6)
    turn_round()
    index = validator_set.getValidatorIndexFromOps(operators[0])
    assert not validator_set.canEnterMaintenance(index)


def test_can_enter_maintenance_after_exit(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.exitMaintenance({'from': operators[0]})

    index = validator_set.getValidatorIndexFromOps(operators[0])
    assert validator_set.canEnterMaintenance(index)


def test_revert_when_validator_count_equals_working(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.enterMaintenance({'from': operators[1]})

    index = validator_set.getValidatorIndexFromOps(operators[2])
    assert not validator_set.canEnterMaintenance(index)


def test_can_enter_maintenance_with_sufficient_working(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})

    index = validator_set.getValidatorIndexFromOps(operators[1])
    assert validator_set.canEnterMaintenance(index)


def test_revert_when_invalid_index(validator_set):
    assert not validator_set.canEnterMaintenance(0)
    with brownie.reverts("Index out of range"):
        validator_set.canEnterMaintenance(999)


# enterMaintenance-slash
def test_revert_when_not_slash_contract(validator_set):
    with brownie.reverts("the msg sender must be slash contract"):
        validator_set.enterMaintenance(init_validators[0])


def test_validator_not_in_set_success(validator_set):
    __update_slash_address()
    non_validator_address = accounts[0]

    initial_validators = validator_set.getValidators()

    tx = validator_set.enterMaintenance(non_validator_address)

    assert validator_set.getValidators() == initial_validators
    assert 'validatorEnterMaintenance' not in tx.events


def test_validator_already_in_maintenance_success(validator_set, set_candidate_maintenance):
    __update_slash_address()
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0

    tx = validator_set.enterMaintenance(consensuses[0])

    validator_after = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator_after['enterMaintenanceHeight'] == validator['enterMaintenanceHeight']
    assert 'validatorEnterMaintenance' not in tx.events


def test_only_one_working_validator_success(validator_set):
    __update_slash_address()
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()

    assert len(validator_set.getCurrentValidatorSet()) == 1

    tx = validator_set.enterMaintenance(consensus)

    validator = validator_set.getValidatorByConsensus(consensus)
    assert validator['enterMaintenanceHeight'] == 0
    assert 'validatorEnterMaintenance' not in tx.events


def test_working_count_equals_validator_count_success(validator_set, candidate_hub, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    candidate_hub.setValidatorCount(len(operators))
    turn_round()
    __update_slash_address()
    assert validator_set.getWorkingCount() == len(operators)
    tx = validator_set.enterMaintenance(consensuses[0])
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] == 0
    assert 'validatorEnterMaintenance' not in tx.events


def test_validator_can_enter_maintenance_success(validator_set, set_candidate_maintenance):
    __update_slash_address()
    operators, consensuses = set_candidate_maintenance
    turn_round()
    assert len(validator_set.getCurrentValidatorSet()) == 4
    assert validator_set.getWorkingCount() == 4
    assert validator_set.validatorCount() == 3
    tx = validator_set.enterMaintenance(consensuses[0])
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    expect_event(tx, "validatorEnterMaintenance", {
        'validator': consensuses[0]
    })


def test_multiple_validators_enter_maintenance_success(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    __update_slash_address()
    operators, consensuses = set_candidate_maintenance
    turn_round()
    for i in range(2):
        tx = validator_set.enterMaintenance(consensuses[i])
        validator = validator_set.getValidatorByConsensus(consensuses[i])
        assert validator['enterMaintenanceHeight'] != 0
        expect_event(tx, "validatorEnterMaintenance", {
            'validator': consensuses[i]
        })


def test_validator_after_exit_maintenance_success(validator_set, set_candidate_maintenance):
    __update_slash_address()
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance(consensuses[0])
    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0

    validator_set.exitMaintenance({'from': operators[0]})
    validator_after_exit = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator_after_exit['enterMaintenanceHeight'] == 0

    tx = validator_set.enterMaintenance(consensuses[0])
    validator_after_enter = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator_after_enter['enterMaintenanceHeight'] != 0
    expect_event(tx, "validatorEnterMaintenance", {
        'validator': consensuses[0]
    })


def test_zero_address_success(validator_set):
    __update_slash_address()

    initial_validators = validator_set.getValidators()

    tx = validator_set.enterMaintenance(ZERO_ADDRESS)

    assert validator_set.getValidators() == initial_validators
    assert 'validatorEnterMaintenance' not in tx.events


def test_validator_has_income_success(validator_set, set_candidate_maintenance):
    __update_slash_address()
    operators, consensuses = set_candidate_maintenance
    turn_round()

    deposit_value = 1000000000
    validator_set.deposit(consensuses[0], {'value': deposit_value})
    assert validator_set.getIncoming(consensuses[0]) == deposit_value

    tx = validator_set.enterMaintenance(consensuses[0])

    validator = validator_set.getValidatorByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    assert validator_set.getIncoming(consensuses[0]) == deposit_value
    expect_event(tx, "validatorEnterMaintenance", {
        'validator': consensuses[0]
    })


# getValidatorIndexFromOps
def test_get_validator_index_success(validator_set):
    first_validator = validator_set.currentValidatorSet(0)
    operate_address = first_validator['operateAddress']

    index = validator_set.getValidatorIndexFromOps(operate_address)

    assert index == 1


def test_get_validator_index_multiple_success(validator_set):
    validator_count = len(validator_set.getCurrentValidatorSet())
    for i in range(validator_count):
        validator = validator_set.currentValidatorSet(i)
        operate_address = validator['operateAddress']
        index = validator_set.getValidatorIndexFromOps(operate_address)
        assert index == i + 1


def test_get_validator_index_not_found_success(validator_set):
    non_existent_address = accounts[99]

    index = validator_set.getValidatorIndexFromOps(non_existent_address)

    assert index == 0


def test_get_validator_index_consensus_address_success(validator_set):
    first_validator = validator_set.currentValidatorSet(0)
    consensus_address = first_validator['consensusAddress']

    index = validator_set.getValidatorIndexFromOps(consensus_address)

    assert index == 0


def test_get_validator_index_after_removal_success(validator_set, candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()

    first_operator = operators[0]
    index_before = validator_set.getValidatorIndexFromOps(first_operator)
    assert index_before > 0

    candidate_hub.refuseDelegate({'from': first_operator})
    turn_round()
    candidate_hub.unregister({'from': first_operator})

    index_after = validator_set.getValidatorIndexFromOps(first_operator)
    assert index_after == 0


# getLivingValidators
def test_get_living_validators_with_multiple_validators(validator_set):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(5)]

    for index, operator in enumerate(accounts[10:15]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
        delegate_coin_success(operator, accounts[0], 1000 + index * 100)

    turn_round()

    result = validator_set.getLivingValidators()
    consensus_addrs, vote_addrs = result

    assert len(consensus_addrs) == len(vote_addrs)

    current_validators = validator_set.getCurrentValidatorSet()
    assert len(consensus_addrs) == len(current_validators)

    for consensus_addr in consensus_addrs:
        found = False
        for validator in current_validators:
            if validator['consensusAddress'] == consensus_addr:
                found = True
                break
        assert found


def test_get_living_validators_excludes_maintenance_validators(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance

    for i, operator in enumerate(operators[:3]):
        delegate_coin_success(operator, accounts[0], 5000 + i * 100)

    turn_round()
    result_before = validator_set.getLivingValidators()
    consensus_addrs_before, _ = result_before
    tx = validator_set.enterMaintenance({'from': operators[0]})
    assert 'validatorEnterMaintenance' in tx.events
    result_after = validator_set.getLivingValidators()
    consensus_addrs_after, vote_addrs_after = result_after
    current_validators = validator_set.getCurrentValidatorSet()
    assert len(consensus_addrs_after) == len(current_validators)
    assert consensuses[0] in consensus_addrs_after


def test_get_living_validators_correctness_of_vote_addresses(validator_set):
    operators = []
    consensuses = []
    specific_vote_addresses = [random_vote_address() for _ in range(3)]
    for index, operator in enumerate(accounts[20:23]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=specific_vote_addresses[index]))
        delegate_coin_success(operator, accounts[0], 2000)
    turn_round()
    result = validator_set.getLivingValidators()
    consensus_addrs, vote_addrs = result
    for i, consensus_addr in enumerate(consensus_addrs):
        if consensus_addr in consensuses:
            consensus_index = consensuses.index(consensus_addr)
            expected_vote_addr = specific_vote_addresses[consensus_index]
            actual_vote_addr = vote_addrs[i]
            assert actual_vote_addr == expected_vote_addr


def test_canceled_and_felony_validators_not_returned(validator_set, candidate_hub, slash_indicator):
    operators = [accounts[30], accounts[31], accounts[32]]
    consensuses = []
    for index, operator in enumerate(operators):
        consensuses.append(register_candidate(operator=operator))
    delegate_coin_success(operators[0], accounts[0], 1e18)
    delegate_coin_success(operators[1], accounts[0], 1e18)
    turn_round()

    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        slash_indicator.slash(consensuses[1])
    turn_round()
    validators = validator_set.getValidators()
    assert consensuses[0] not in validators
    assert consensuses[1] not in validators
    consensus_addrs, _ = validator_set.getLivingValidators()
    assert consensuses[0] not in consensus_addrs
    assert consensuses[1] not in consensus_addrs
    assert consensus_addrs == [consensuses[2]]


# update maintainSlashPercent 
def test_revert_when_not_gov_update_maintain_slash_percent(validator_set):
    hex_value = padding_left(Web3.to_hex(50), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        validator_set.updateParam('maintainSlashPercent', hex_value)


def test_revert_when_invalid_param_length_maintain_slash_percent(validator_set):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(50), 62)
    with brownie.reverts("MismatchParamLength: maintainSlashPercent"):
        validator_set.updateParam('maintainSlashPercent', hex_value)


@pytest.mark.parametrize("value", [101, 102])
def test_revert_when_maintain_slash_percent_exceeds_max(validator_set, value):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(value), 64)
    with brownie.reverts(f"OutOfBounds: maintainSlashPercent, {value}, 0, 100"):
        validator_set.updateParam('maintainSlashPercent', hex_value)


@pytest.mark.parametrize("value", [0, 1, 10, 50, 98, 99, 100])
def test_update_maintain_slash_percent_success(validator_set, value):
    __update_gov_address()
    hex_value = padding_left(Web3.to_hex(value), 64)

    tx = validator_set.updateParam('maintainSlashPercent', hex_value)

    assert validator_set.maintainSlashPercent() == value


# updateRankedValidatorList
def test_update_ranked_validator_list_basic_success(validator_set, set_candidate_maintenance):
    turn_round()
    assert len(validator_set.getRankedValidatorList()) == 4
    new_consensus_list = [accounts[10], accounts[11], accounts[12]]
    validator_set.mockUpdateRankedValidatorList(new_consensus_list)

    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 3
    assert updated_list[0] == accounts[10]
    assert updated_list[1] == accounts[11]
    assert updated_list[2] == accounts[12]


def test_update_ranked_validator_list_length_changes_success(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    long_list = [accounts[10], accounts[11], accounts[12], accounts[13], accounts[14]]
    validator_set.mockUpdateRankedValidatorList(long_list)
    assert len(validator_set.getRankedValidatorList()) == 5

    short_list = [accounts[20], accounts[21]]
    tx = validator_set.mockUpdateRankedValidatorList(short_list)

    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 2
    assert updated_list[0] == accounts[20]
    assert updated_list[1] == accounts[21]

    longer_list = [accounts[30], accounts[31], accounts[32], accounts[33]]
    tx = validator_set.mockUpdateRankedValidatorList(longer_list)

    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 4
    assert updated_list[0] == accounts[30]
    assert updated_list[1] == accounts[31]
    assert updated_list[2] == accounts[32]
    assert updated_list[3] == accounts[33]


def test_update_ranked_validator_list_edge_cases_success(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    empty_list = []
    tx = validator_set.mockUpdateRankedValidatorList(empty_list)
    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 0
    single_element_list = [accounts[99]]
    tx = validator_set.mockUpdateRankedValidatorList(single_element_list)
    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 1
    assert updated_list[0] == accounts[99]

    large_list = [accounts[i] for i in range(10, 20)]
    tx = validator_set.mockUpdateRankedValidatorList(large_list)
    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 10
    for i in range(10):
        assert updated_list[i] == accounts[10 + i]


def test_update_ranked_validator_list_special_addresses_success(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    duplicate_list = [accounts[10], accounts[10], accounts[11], accounts[11], accounts[12]]
    tx = validator_set.mockUpdateRankedValidatorList(duplicate_list)
    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 5
    assert updated_list[0] == accounts[10]
    assert updated_list[1] == accounts[10]
    assert updated_list[2] == accounts[11]
    assert updated_list[3] == accounts[11]
    assert updated_list[4] == accounts[12]

    zero_address_list = [accounts[10], "0x0000000000000000000000000000000000000000", accounts[11]]
    tx = validator_set.mockUpdateRankedValidatorList(zero_address_list)
    updated_list = validator_set.getRankedValidatorList()
    assert len(updated_list) == 3
    assert updated_list[0] == accounts[10]
    assert updated_list[1] == "0x0000000000000000000000000000000000000000"
    assert updated_list[2] == accounts[11]


def test_update_ranked_validator_list_multiple_updates_success(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    list1 = [accounts[10], accounts[11]]
    tx1 = validator_set.mockUpdateRankedValidatorList(list1)
    assert len(validator_set.getRankedValidatorList()) == 2

    list2 = [accounts[20], accounts[21], accounts[22]]
    tx2 = validator_set.mockUpdateRankedValidatorList(list2)
    assert len(validator_set.getRankedValidatorList()) == 3

    list3 = [accounts[30]]
    tx3 = validator_set.mockUpdateRankedValidatorList(list3)

    final_list = validator_set.getRankedValidatorList()
    assert len(final_list) == 1
    assert final_list[0] == accounts[30]


# getWorkingCount
def test_get_working_count_basic(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    assert validator_set.getWorkingCount() == 5

    validator_set.enterMaintenance({'from': operators[0]})
    assert validator_set.getWorkingCount() == 4

    validator_set.enterMaintenance({'from': operators[1]})
    assert validator_set.getWorkingCount() == 3


def test_get_working_count_after_exit(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    assert validator_set.getWorkingCount() == 4

    validator_set.exitMaintenance({'from': operators[0]})
    assert validator_set.getWorkingCount() == 5


def test_get_working_count_edge_case(validator_set, candidate_hub):
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()

    assert validator_set.getWorkingCount() == 1

    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operator})

    assert validator_set.getWorkingCount() == 1


def test_get_working_count_after_misdemeanor_slash(validator_set, candidate_hub, slash_indicator,
                                                   set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()
    assert validator_set.getWorkingCount() == 5

    for _ in range(2):
        slash_indicator.slash(consensuses[0])
    assert validator_set.getWorkingCount() == 4
    for _ in range(2):
        slash_indicator.slash(consensuses[1])
    assert validator_set.getWorkingCount() == 3
    slash_indicator.setFelonyThreshold(3)
    for _ in range(3):
        slash_indicator.slash(consensuses[2])
    assert validator_set.getWorkingCount() == 2


# getWorkingValidators
def test_get_working_validators_basic(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    delegate_coin_success(operators[3], accounts[0], 1e17)
    delegate_coin_success(operators[4], accounts[0], 1e16)
    turn_round()

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 5
    assert working_validators == consensuses

    validator_set.enterMaintenance({'from': operators[0]})
    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 4
    assert consensuses[0] not in working_validators
    for i in range(1, 5):
        assert consensuses[i] in working_validators


def test_get_working_validators_after_exit(validator_set, candidate_hub, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    validator_set.enterMaintenance({'from': operators[0]})
    validator_set.enterMaintenance({'from': operators[-1]})
    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 3
    assert consensuses[0] not in working_validators
    assert consensuses[-1] not in working_validators

    validator_set.exitMaintenance({'from': operators[-1]})
    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 4
    assert consensuses[0] not in working_validators
    assert consensuses[-1] in working_validators


def test_get_working_validators_after_slash(validator_set, candidate_hub, slash_indicator, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(2)
    operators, consensuses = set_candidate_maintenance
    turn_round()

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 5

    for _ in range(2):
        slash_indicator.slash(consensuses[0])

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 4
    assert consensuses[0] not in working_validators

    slash_indicator.setFelonyThreshold(3)
    for _ in range(3):
        slash_indicator.slash(consensuses[1])

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 3
    assert consensuses[0] not in working_validators
    assert consensuses[1] not in working_validators


def test_get_working_validators_edge_case(validator_set, candidate_hub):
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    delegate_coin_success(operator, accounts[0], 1e18)
    turn_round()

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 1
    assert working_validators[0] == consensus
    with brownie.reverts("can not enter Temporary Maintenance"):
        validator_set.enterMaintenance({'from': operator})

    working_validators = validator_set.getWorkingValidators()
    assert len(working_validators) == 1
    assert working_validators[0] == consensus


def test_get_working_validators_consistency(validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    working_count = validator_set.getWorkingCount()
    working_validators = validator_set.getWorkingValidators()
    assert working_count == len(working_validators)

    validator_set.enterMaintenance({'from': operators[0]})
    working_count = validator_set.getWorkingCount()
    working_validators = validator_set.getWorkingValidators()
    assert working_count == len(working_validators)

    validator_set.exitMaintenance({'from': operators[0]})
    working_count = validator_set.getWorkingCount()
    working_validators = validator_set.getWorkingValidators()
    assert working_count == len(working_validators)
