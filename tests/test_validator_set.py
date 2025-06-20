import pytest
import brownie
from web3 import Web3, constants

from .common import turn_round, register_candidate, get_current_round, execute_proposal
from .delegate import delegate_coin_success
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

account_tracker: AccountTracker = None
system_reward_tracker: AccountTracker = None
validator_set_tracker: AccountTracker = None
stake_hub_tracker: AccountTracker = None
validator_set_instance = None
BLOCK_REWARD = 0
felony_round = 1
felony_deposit = int(1e5)


@pytest.fixture(scope="module", autouse=True)
def setup(system_reward, validator_set, pledge_agent, core_agent, stake_hub):
    global account_tracker, system_reward_tracker, validator_set_tracker, stake_hub_tracker
    global validator_set_instance
    global BLOCK_REWARD, block_reward
    validator_set_instance = validator_set
    BLOCK_REWARD = validator_set.BLOCK_REWARD()
    account_tracker = get_tracker(accounts[0])
    system_reward_tracker = get_tracker(system_reward)
    validator_set_tracker = get_tracker(validator_set)
    stake_hub_tracker = get_tracker(stake_hub)
    block_reward = validator_set.blockReward()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


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
        validator = [operators[i], consensuses[i], operators[i], 1000, 0, vote_address_list[i], weights[i]]
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


def test_update_failed_by_address_which_is_not_candidate():
    with brownie.reverts("the msg sender must be candidate contract"):
        validator_set_instance.updateValidatorSet([random_address], [random_address], [random_address], [100], [])


def test_update_failed_with_empty_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [])
    assert validator_set_instance.getValidators() == init_validators


def test_update_failed_with_addresses_of_different_length():
    __fake_validator_set()
    with brownie.reverts("the numbers of consensusAddresses and commissionThousandthss should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address], [accounts[2].address],
                                                  [accounts[3].address, accounts[4].address], [random_vote_address()])
    with brownie.reverts("the numbers of consensusAddresses and feeAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address],
                                                  [accounts[2].address, accounts[4].address], [accounts[3].address],
                                                  [random_vote_address()])
    with brownie.reverts("the numbers of consensusAddresses and operateAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address], [accounts[1].address, accounts[4].address],
                                                  [accounts[2].address], [accounts[3].address], [random_vote_address()])
    with brownie.reverts("the numbers of consensusAddresses and operateAddresses should be equal"):
        validator_set_instance.updateValidatorSet([accounts[0].address, accounts[4].address], [accounts[1].address],
                                                  [accounts[2].address], [accounts[3].address], [random_vote_address()])


def test_update_failed_with_duplicate_consensus_address():
    __fake_validator_set()
    with brownie.reverts("duplicate consensus address"):
        validator_set_instance.updateValidatorSet([accounts[0], accounts[0]], [accounts[1], accounts[1]],
                                                  [accounts[2], accounts[2]], [100, 100],
                                                  [random_vote_address(), random_vote_address()])


def test_update_failed_with_commissionThousandths_out_of_range():
    __fake_validator_set()
    with brownie.reverts("commissionThousandths out of bound"):
        validator_set_instance.updateValidatorSet([accounts[0], accounts[0]], [accounts[1], accounts[3]],
                                                  [accounts[2], accounts[2]], [1000, 10000],
                                                  [random_vote_address(), random_vote_address()])


def test_update_success():
    __fake_validator_set()
    tx = validator_set_instance.updateValidatorSet([accounts[0]], [accounts[1]], [accounts[2]], [1000],
                                                   [Web3.to_hex(random_vote_address())])
    expect_event(tx, "validatorSetUpdated")
    assert validator_set_instance.getValidators() == [accounts[1]]


@pytest.mark.parametrize("fake,key,value,err", [
    (False, "blockReward", "0x0000000000000000000000000000000000000000000000000000000000000001",
     "the msg sender must be governance contract"),
    (True, "totalInCome", "0x0000000000000000000000000000000000000000000000000000000000000001", "unknown param"),
    (True, "blockReward", '0x' + str('2000000000000000000'), "length of blockReward mismatch"),
    (True, "blockReward", "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "the blockReward out of range"),
    (True, "blockReward", "0x000000000000000000000000000000000000000000000001a055690d9db80001",
     "the blockReward out of range"),
    (True, "blockRewardIncentivePercent", "0x" + str(10), "length of blockRewardIncentivePercent mismatch"),
    (True, "blockRewardIncentivePercent", "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "the blockRewardIncentivePercent out of range"),
    (True, "blockRewardIncentivePercent", "0x0000000000000000000000000000000000000000000000000000000000000000",
     "the blockRewardIncentivePercent out of range"),
    (True, "blockRewardIncentivePercent", "0x0000000000000000000000000000000000000000000000000000000000000064",
     "the blockRewardIncentivePercent out of range"),
])
def update_param_failed(fake, key, value, err):
    if fake:
        __fake_validator_set()
    with brownie.reverts(err):
        validator_set_instance.updateParam(key, value)


@pytest.mark.parametrize("value,expected", [
    ("0x0000000000000000000000000000000000000000000000000000000000000000", 0),
    ("0x000000000000000000000000000000000000000000000001a055690d9db80000", 30000000000000000000),
    ("0x0000000000000000000000000000000000000000000000001bc16d674ec80000", 2000000000000000000),
])
def update_param_success_with_block_reward(value, expected):
    __fake_validator_set()
    validator_set_instance.updateParam("blockReward", value)
    assert validator_set_instance.blockReward() == expected


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
    validator_set_instance.updateValidatorSet([], [], [], [], [])
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
        [validator['voteAddr']]
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


def test_distribute_vote_reward_success(validator_set, system_reward):
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
    vote_reward = validator_reward * validator_set.INIT_VOTE_REWARD_PERCENT() // 100 * 3
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


def test_zero_vote_weight_sum_zero_reward_success(validator_set, system_reward, set_candidate):
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


def test_distribute_reward_by_weight_proportion_success(validator_set, system_reward, set_candidate):
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
    vote_reward = validator_reward * validator_set.INIT_VOTE_REWARD_PERCENT() // 100
    tx = validator_set.distributeReward(get_current_round())
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * vote_weight[index] // sum(vote_weight)
        assert tracker.delta() == validator_fee + vote_fee


def test_vote_reward_as_validator_portion_success(validator_set, system_reward):
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
    vote_reward = validator_reward * validator_set.INIT_VOTE_REWARD_PERCENT() // 100
    validator_set.distributeReward(get_current_round())
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * weights0[index] // sum(weights0)
        assert tracker.delta() == validator_fee + vote_fee


@pytest.mark.parametrize("vote_reward_percent", [0, 20, 99, 100])
def test_vote_reward_after_update_success(validator_set, set_candidate, vote_reward_percent):
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
    validator_set.distributeReward(get_current_round())
    for index, tracker in enumerate(trackers):
        validator_fee = validator_reward - vote_reward
        vote_fee = vote_reward * len(operators) * weights[index] // sum(weights)
        assert tracker.delta() == validator_fee + vote_fee


def test_misdemeanor_failed_with_address_which_is_not_slash():
    with brownie.reverts("the msg sender must be slash contract"):
        validator_set_instance.misdemeanor(init_validators[0])


def test_misdemeanor_failed_with_after_set_empty_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [])
    __update_slash_address()
    validator = validator_set_instance.getValidatorByConsensus(init_validators[0]).dict()
    tx = validator_set_instance.misdemeanor(init_validators[0])
    expect_event(tx, "validatorMisdemeanor", {
        "validator": validator['operateAddress'],
        "amount": 0
    })


def test_misdemeanor_return_empty_with_empty_validator_set_and_ZERO_ADDRESS():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([], [], [], [], [])
    __update_slash_address()
    assert validator_set_instance.misdemeanor.call(ZERO_ADDRESS) == ()


def test_misdemeanor_return_empty_with_only_one_validator_set_and_0_income():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()])
    __update_slash_address()
    assert validator_set_instance.misdemeanor.call(init_validators[0]) == ()
    __contract_check(0, [0])


def test_misdemeanor_return_empty_with_only_one_validator_set():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()])

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
                                              [random_vote_address()])
    __update_slash_address()
    assert validator_set_instance.felony.call(init_validators[0], felony_round, felony_deposit) == ()
    __contract_check(0, [0])


def test_felony_failed_with_one_validator_which_has_income():
    __fake_validator_set()
    validator_set_instance.updateValidatorSet([init_validators[0]], [init_validators[0]], [init_validators[0]], [100],
                                              [random_vote_address()])
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
                                              [random_vote_address(), random_vote_address()])

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
                                              [random_vote_address(), random_vote_address()])

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
