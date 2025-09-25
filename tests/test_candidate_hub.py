import random
import pytest
import brownie
from web3 import Web3
from eth_account import Account
from brownie import accounts, UnRegisterReentry
from brownie.test import given, strategy
from brownie.network.transaction import Status, TransactionReceipt
from tests.delegate import delegate_btc_success, delegate_coin_success
from .constant import Utils
from .utils import random_address, expect_event, padding_left, update_system_contract_address
from .common import *


@pytest.fixture(scope="module")
def required_margin(candidate_hub):
    return candidate_hub.requiredMargin()


@pytest.fixture(scope="module")
def set_candidate_status(candidate_hub):
    return candidate_hub.SET_CANDIDATE()


@pytest.fixture(scope="module")
def set_inactive_status(candidate_hub):
    return candidate_hub.SET_INACTIVE()


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_register(candidate_hub, required_margin):
    consensus_address = random_address()
    commission = 10
    tx: TransactionReceipt = candidate_hub.register(
        consensus_address, accounts[0], commission, random_vote_address(),
        {'from': accounts[0], 'value': required_margin}
    )
    assert tx.status == Status.Confirmed


def test_register_multiple_times():
    for idx in range(10):
        register_candidate(operator=accounts[idx])


def test_canDelegate_true(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    for operator in operators:
        assert candidate_hub.canDelegate(operator) is True
    turn_round()


def test_canDelegate_false(candidate_hub):
    operators = []
    for operator in accounts[5:8]:
        operators.append(operator)
    for operator in operators:
        assert candidate_hub.canDelegate(operator) is False
    turn_round()


@pytest.mark.parametrize("validator_state", [['minor', True], ['major', False]])
def test_slash_candelegate(candidate_hub, validator_state, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    tx0 = None
    if validator_state[0] == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        event_name = 'validatorMisdemeanor'
    else:
        slash_threshold = slash_indicator.felonyThreshold()
        event_name = 'validatorFelony'
    for count in range(slash_threshold):
        tx0 = slash_indicator.slash(consensuses[0])
    assert event_name in tx0.events
    assert candidate_hub.canDelegate(operators[0]) is validator_state[1]
    turn_round()


def test_cancel_registration_false(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    assert candidate_hub.canDelegate(operators[0]) is False
    turn_round()


def test_validator_not_exist_false(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    assert candidate_hub.canDelegate(consensuses[0]) is False
    turn_round()


def test_is_validator_true(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    assert candidate_hub.isValidator(operators[0]) is True
    turn_round()


def test_is_validator_false(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    assert candidate_hub.isValidator(consensuses[0]) is False
    turn_round()


@pytest.mark.parametrize("validator_state", ['minor', 'major'])
def test_slash_is_validator(candidate_hub, validator_state, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    if validator_state == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
    else:
        slash_threshold = slash_indicator.felonyThreshold()
    for count in range(slash_threshold):
        slash_indicator.slash(consensuses[0])
    assert candidate_hub.isValidator(operators[0]) is True
    turn_round()


def test_isValidator_canceled(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    assert candidate_hub.isValidator(operators[0]) is False
    turn_round()


def test_isValidator_not_exist(candidate_hub):
    turn_round()
    assert candidate_hub.isValidator(accounts[0]) is False


def test_isCandidateByOperate_true(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    assert candidate_hub.isCandidateByOperate(operators[0])


def test_isCandidateByOperate_fasle(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    assert candidate_hub.isCandidateByOperate(consensuses[0]) is False


def test_isCandidateByOperate_zeroAddress(candidate_hub, set_candidate):
    zero_address = "0x0000000000000000000000000000000000000000"
    assert candidate_hub.isCandidateByOperate(zero_address) is False


def test_only_validator_can_call(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    with brownie.reverts("the msg sender must be validatorSet contract"):
        candidate_hub.jailValidator(consensuses[0], 2, 1e5)


def test_jail_nonexistent_address(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(candidate_hub, validator_set=accounts[0])
    tx = candidate_hub.jailValidator(consensuses[0], 2, 1e5)
    assert len(tx.events) == 0


def test_jail_insufficient_deposit(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(candidate_hub, validator_set=accounts[0])
    new_dues = 1e10
    candidate_hub.setDues(new_dues)
    tx = candidate_hub.jailValidator(operators[0], 2, 1e5)
    assert 'unregistered' in tx.events


def test_jail_already_jailed(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(candidate_hub, validator_set=accounts[0])
    round = 2
    candidate_hub.jailValidator(operators[0], round, 1e5)
    assert candidate_hub.jailMap(operators[0]) == get_current_round() + round
    candidate_hub.jailValidator(operators[0], round, 1e5)
    assert candidate_hub.jailMap(operators[0]) == get_current_round() + round * 2


def test_jail_first_time(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(candidate_hub, validator_set=accounts[0])
    round = 2
    tx = candidate_hub.jailValidator(operators[0], round, 1e5)
    assert 'statusChanged' in tx.events
    assert candidate_hub.jailMap(operators[0]) == get_current_round() + round


def test_getRoundTag_success(candidate_hub):
    init_round = 7
    round_tag = candidate_hub.getRoundTag()
    assert round_tag == init_round


# turnRound
def test_turnRound_after_new_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for operator in accounts[10:12]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    tx = turn_round(consensuses, round_count=2)
    round_tag = 10
    assert tx.events['turnedRound']['round'] == round_tag


def test_turnRound_after_slash(candidate_hub, set_candidate, slash_indicator):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.misdemeanorThreshold(), slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[index])
    tx = turn_round(consensuses)
    round_tag = 9
    assert tx.events['turnedRound']['round'] == round_tag


def test_turnRound_after_validator_cancel(candidate_hub, set_candidate, slash_indicator):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    tx = turn_round(consensuses)
    assert tx.events['turnedRound']['round'] == get_current_round()


def test_turnRound_no_staked_validators(candidate_hub, set_candidate, slash_indicator):
    operators, consensuses = set_candidate
    turn_round()
    tx = turn_round(consensuses)
    assert tx.events['turnedRound']['round'] == get_current_round()


def test_turnRound_burn_validator_rewards(candidate_hub, set_candidate, slash_indicator):
    operators, consensuses = set_candidate
    turn_round()
    tx = turn_round(consensuses)
    assert 'receiveDeposit' in tx.events


def test_turnRound_update_validator_info(candidate_hub, set_candidate, slash_indicator):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    tx = turn_round(consensuses)
    assert 'validatorSetUpdated' in tx.events


def test_turnround_update_voteaddrlist_success(candidate_hub, validator_set, slash_indicator):
    operators = []
    consensuses = []
    init_vote_address = 0x99a1dbde53606922478636c65b06f9683e10bde7f6cbee8f0ebbb803d0beef91fa47f2727ef8533cb5166e54a52d08b8
    vote_address_list = [random_vote_address() for _ in range(3)]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
    assert validator_set.getValidatorsAndVoteAddresses()[1] == [Web3.to_hex(init_vote_address)] * 5
    tx = turn_round()
    assert 'validatorSetUpdated' in tx.events
    assert validator_set.getValidatorsAndVoteAddresses()[0] == consensuses
    assert validator_set.getValidatorsAndVoteAddresses()[1] == vote_address_list
    turn_round(consensuses)
    assert validator_set.currentValidatorSet(0) == [operators[0], consensuses[0], operators[0], 1000, 0]
    assert validator_set.exMap(consensuses[0])['voteAddr'] == vote_address_list[0]
    assert validator_set.exMap(consensuses[0])['voteWeight'] == 0
    assert validator_set.exMap(consensuses[0])['enterMaintenanceHeight'] == 0


def test_turnRound_update_validatorEx_success(candidate_hub, validator_set, slash_indicator):
    operators = []
    consensuses = []
    vote_address_list = [random_vote_address() for _ in range(3)]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
    turn_round(consensuses)
    weights = [30, 50, 80]
    chain_vote(consensuses, weights)
    for i in range(3):
        assert validator_set.exMap(consensuses[i])['voteAddr'] == vote_address_list[i]
        assert validator_set.exMap(consensuses[i])['voteWeight'] == weights[i]
        assert validator_set.exMap(consensuses[i])['enterMaintenanceHeight'] == 0
    turn_round(consensuses)
    for i in range(3):
        assert validator_set.exMap(consensuses[i])['voteAddr'] == vote_address_list[i]
        assert validator_set.exMap(consensuses[i])['voteWeight'] == 0
        assert validator_set.exMap(consensuses[i])['enterMaintenanceHeight'] == 0
    chain_vote(consensuses, weights)
    for i in range(3):
        assert validator_set.exMap(consensuses[i])['voteAddr'] == vote_address_list[i]
        assert validator_set.exMap(consensuses[i])['voteWeight'] == weights[i]
        assert validator_set.exMap(consensuses[i])['enterMaintenanceHeight'] == 0


@pytest.mark.parametrize("times", [
    1,
    pytest.param(2, marks=pytest.mark.xfail),
    pytest.param(5, marks=pytest.mark.xfail),
    pytest.param(10, marks=pytest.mark.xfail)
])
def test_duplicate_operator(candidate_hub, required_margin, times):
    for _ in range(times):
        candidate_hub.register(
            random_address(), accounts[0], 1, random_vote_address(),
            {'from': accounts[0], 'value': required_margin}
        )


def test_duplicate_consensus_address(candidate_hub, required_margin):
    consensus_address = random_address()
    candidate_hub.register(consensus_address, accounts[0], 1, random_vote_address(),
                           {'from': accounts[0], 'value': required_margin})
    with brownie.reverts("consensus already exists"):
        candidate_hub.register(
            consensus_address, accounts[1], 1, random_vote_address(), {'from': accounts[1], 'value': required_margin}
        )


@given(commission=strategy('uint32', max_value=1000, exclude=(0, 1000)))
def test_register_commission(candidate_hub, required_margin, commission):
    candidate_hub.register(
        random_address(), accounts[0], commission, random_vote_address(),
        {'from': accounts[0], 'value': required_margin}
    )


@pytest.mark.parametrize("commission", [
    pytest.param(0, marks=pytest.mark.xfail),
    pytest.param(-1, marks=pytest.mark.xfail),
    pytest.param(1000, marks=pytest.mark.xfail),
    pytest.param(1001, marks=pytest.mark.xfail),
    pytest.param(1000000, marks=pytest.mark.xfail)
])
def test_register_invalid_commission(candidate_hub, required_margin, commission):
    candidate_hub.register(
        random_address(), accounts[0], commission,
        {'from': accounts[0], 'value': required_margin}
    )


@pytest.mark.parametrize("margin", [
    pytest.param(0, marks=pytest.mark.xfail),
    pytest.param(1, marks=pytest.mark.xfail),
    Web3.to_wei(11000, 'ether')
])
def test_register_margin(candidate_hub, margin):
    candidate_hub.register(
        random_address(), accounts[0], 1, random_vote_address(),
        {'from': accounts[0], 'value': margin}
    )


def test_register_zero_consensus_address(candidate_hub, required_margin):
    zero_address = "0x0000000000000000000000000000000000000000"
    with brownie.reverts("consensus address should not be zero"):
        candidate_hub.register(
            zero_address, accounts[0], 1, random_vote_address(),
            {'from': accounts[0], 'value': required_margin}
        )


def test_register_zero_fee_address(candidate_hub, required_margin):
    zero_address = "0x0000000000000000000000000000000000000000"
    with brownie.reverts("fee address should not be zero"):
        candidate_hub.register(
            random_address(), zero_address, 1, random_vote_address(),
            {'from': accounts[0], 'value': required_margin}
        )


def test_register_exceeds_validator_limit(candidate_hub, required_margin):
    zero_address = "0x0000000000000000000000000000000000000000"
    with brownie.reverts("fee address should not be zero"):
        candidate_hub.register(
            random_address(), zero_address, 1, random_vote_address(),
            {'from': accounts[0], 'value': required_margin}
        )


def test_register_requires_init_first(candidate_hub, required_margin):
    candidate_hub.setAlreadyInit(False)
    with brownie.reverts("the contract not init yet"):
        candidate_hub.register(
            random_address(), accounts[0], 1, random_vote_address(),
            {'from': accounts[0], 'value': required_margin}
        )


def test_register_zero_payment_amount(candidate_hub, required_margin):
    with brownie.reverts("deposit is not enough"):
        candidate_hub.register(
            random_address(), accounts[0], 1, random_vote_address(),
            {'from': accounts[0], 'value': 0}
        )


def test_reregister_after_cancel(candidate_hub, required_margin):
    candidate_hub.register(
        random_address(), accounts[0], 1, random_vote_address(),
        {'from': accounts[0], 'value': required_margin}
    )
    candidate_hub.refuseDelegate({'from': accounts[0]})
    turn_round()
    candidate_hub.unregister({'from': accounts[0]})
    tx = candidate_hub.register(
        random_address(), accounts[0], 1, random_vote_address(),
        {'from': accounts[0], 'value': required_margin}
    )
    assert 'registered' in tx.events


@pytest.mark.parametrize("candidate_size", [
    999, 1000, 1001, 1002
])
def test_candidate_size_exceeds_total_limit(candidate_hub, required_margin, candidate_size):
    operator = accounts[0]
    candidate_hub.mockRegister(candidate_size)
    if candidate_size <= 1000:
        tx = candidate_hub.register(
            random_address(), accounts[1], 1, random_vote_address(),
            {'from': operator, 'value': required_margin}
        )
        assert 'registered' in tx.events
    else:
        with brownie.reverts("maximum candidate size reached"):
            candidate_hub.register(
                random_address(), accounts[1], 1, random_vote_address(),
                {'from': operator, 'value': required_margin}
            )


def test_vote_addr_invalid_length(candidate_hub, required_margin):
    operator = accounts[0]
    with brownie.reverts("vote address length should be 48"):
        candidate_hub.register(
            random_address(), accounts[1], 1, accounts[0].address,
            {'from': operator, 'value': required_margin}
        )


def test_duplicate_vote_addr(candidate_hub, required_margin):
    operator = accounts[0]
    vote_address = random_vote_address()
    candidate_hub.register(
        random_address(), accounts[1], 1, vote_address,
        {'from': operator, 'value': required_margin}
    )
    with brownie.reverts("vote address already exists"):
        candidate_hub.register(
            random_address(), accounts[0], 1, vote_address,
            {'from': accounts[2], 'value': required_margin}
        )


def test_vote_addr_list_contains_duplicates(candidate_hub, required_margin, validator_set, set_candidate):
    turn_round()
    vote_address = validator_set.getValidatorsAndVoteAddresses()[1][0]
    with brownie.reverts("vote address already exists"):
        candidate_hub.register(
            random_address(), accounts[0], 1, vote_address,
            {'from': accounts[1], 'value': required_margin}
        )


def test_registration_index_correct_after_success(candidate_hub, required_margin):
    vote_address = random_vote_address()
    consensus_addr = random_address()
    commission_thousandths = 100
    tx = candidate_hub.register(
        consensus_addr, accounts[0], commission_thousandths, vote_address,
        {'from': accounts[1], 'value': required_margin}
    )
    expect_event(tx, "registered", {
        'operateAddr': accounts[1],
        'consensusAddr': consensus_addr,
        'feeAddress': accounts[0],
        'commissionThousandths': commission_thousandths,
        'margin': required_margin,
        'voteAddr': vote_address
    })
    commission_last_round = 100
    status = 1
    assert candidate_hub.candidateSet(0) == (
        accounts[1],
        consensus_addr,
        accounts[0],
        commission_thousandths,
        required_margin,
        status,
        get_current_round(),
        commission_last_round
    )
    assert candidate_hub.exMap(accounts[1])['voteAddr'] == vote_address
    assert candidate_hub.exMap(accounts[1])['agent'] == ZERO_ADDRESS
    assert candidate_hub.operateMap(accounts[1]) == 1
    assert candidate_hub.getConsensusMap(consensus_addr) == 1
    consensus = register_candidate(operator=accounts[2])
    assert candidate_hub.operateMap(accounts[2]) == 2
    assert candidate_hub.getConsensusMap(consensus) == 2
    assert candidate_hub.candidateSet(1)['operateAddr'] == accounts[2]


# updateParam
def test_only_gov_can_call(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(candidate_hub.dues() + 10), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        candidate_hub.updateParam("requiredMargin", value)


def test_param_length_error(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(candidate_hub.dues() + 10), 65)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts("MismatchParamLength: requiredMargin"):
        candidate_hub.updateParam("requiredMargin", value)


@pytest.mark.parametrize("newRequiredMargin", [1, 1000, 102220])
def test_update_required_margin_success(candidate_hub, required_margin, newRequiredMargin):
    dues = candidate_hub.dues()
    value = padding_left(Web3.to_hex(dues + newRequiredMargin), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("requiredMargin", value)
    assert candidate_hub.requiredMargin() == dues + newRequiredMargin


def test_update_required_margin_zero_success(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(0), 64)
    uint256_max = 2 ** 256 - 1
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: requiredMargin, 0, 10001, {uint256_max}"):
        candidate_hub.updateParam("requiredMargin", value)


@pytest.mark.parametrize("newRequiredMargin", [1, 10, 5000])
def test_required_margin_cannot_less_than_dues(candidate_hub, required_margin, newRequiredMargin):
    dues = candidate_hub.dues()
    value = padding_left(Web3.to_hex(dues - newRequiredMargin), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(f"OutOfBounds: requiredMargin, {dues - newRequiredMargin}, 10001, {uint256_max}"):
        candidate_hub.updateParam("requiredMargin", value)


@pytest.mark.parametrize("new_dues", [1, 1000, 8000])
def test_update_dues_success(candidate_hub, required_margin, new_dues):
    value = padding_left(Web3.to_hex(required_margin - new_dues), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("dues", value)
    assert candidate_hub.dues() == required_margin - new_dues


def test_dues_zero(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(0), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: dues, 0, 1, {required_margin - 1}"):
        candidate_hub.updateParam("dues", value)


def test_dues_cannot_greater_than_required_margin(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(required_margin + 1), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: dues, {required_margin + 1}, 1, {required_margin - 1}"):
        candidate_hub.updateParam("dues", value)


# updateParam-validatorCount
@pytest.mark.parametrize("validator_count", [6, 25, 41])
def test_govern_validator_count_success(candidate_hub, required_margin, validator_count):
    value = padding_left(Web3.to_hex(validator_count), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("validatorCount", value)
    assert candidate_hub.validatorCount() == validator_count


@pytest.mark.parametrize("validator_count", [0, 4, 5, 42, 43, 100])
def test_validator_count_out_of_range(candidate_hub, required_margin, validator_count):
    value = padding_left(Web3.to_hex(validator_count), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: validatorCount, {validator_count}, 6, 41"):
        candidate_hub.updateParam("validatorCount", value)


@pytest.mark.parametrize("validator_count", [19, 20, 21, 22])
def test_update_validator_count_after_max_alternate_count(candidate_hub, validator_count):
    old_validator_count = candidate_hub.validatorCount()
    max_alternate = old_validator_count // 3
    value = padding_left(Web3.to_hex(max_alternate), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("maxAlternateCount", value)
    assert candidate_hub.maxAlternateCount() == max_alternate
    assert old_validator_count == 21
    assert max_alternate == 7
    value2 = padding_left(Web3.to_hex(validator_count), 64)
    if validator_count < 21:
        with brownie.reverts(f"OutOfBounds: maxAlternateCount, {max_alternate}, 0, {validator_count // 3}"):
            candidate_hub.updateParam("validatorCount", value2)
    else:
        candidate_hub.updateParam("validatorCount", value2)
        assert candidate_hub.validatorCount() == validator_count


@pytest.mark.parametrize("maxCommissionChange", [1, 500, 1000])
def test_govern_max_commission_change_success(candidate_hub, required_margin, maxCommissionChange):
    value = padding_left(Web3.to_hex(maxCommissionChange), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("maxCommissionChange", value)
    assert candidate_hub.maxCommissionChange() == maxCommissionChange


def test_max_commission_change_zero(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(0), 64)
    uint256_max = 2 ** 256 - 1
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: maxCommissionChange, 0, 1, {uint256_max}"):
        candidate_hub.updateParam("maxCommissionChange", value)


def test_governance_param_error(candidate_hub, required_margin):
    value = padding_left(Web3.to_hex(required_margin), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(f"UnsupportedGovParam: error_key"):
        candidate_hub.updateParam("error_key", value)


# updateParam - maxAlternateCount
@pytest.mark.parametrize("maxAlternateCount", [0, 1, 2, 6, 7])
def test_govern_max_alternate_count_success(candidate_hub, maxAlternateCount):
    value = padding_left(Web3.to_hex(maxAlternateCount), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    candidate_hub.updateParam("maxAlternateCount", value)
    assert candidate_hub.maxAlternateCount() == maxAlternateCount


def test_max_alternate_count_out_of_range(candidate_hub):
    value = padding_left(Web3.to_hex(candidate_hub.validatorCount() // 3 + 1), 64)
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    with brownie.reverts(
            f"OutOfBounds: maxAlternateCount, {candidate_hub.validatorCount() // 3 + 1}, 0, {candidate_hub.validatorCount() // 3}"):
        candidate_hub.updateParam("maxAlternateCount", value)


def test_refuse_delegate_success(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    assert candidate_hub.canDelegate(operators[0]) is False
    turn_round()


def test_refuse_delegate_nonexistent_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.refuseDelegate({'from': consensuses[0]})


def test_refuse_delegate_zero_address(candidate_hub, set_candidate):
    zero_address = "0x0000000000000000000000000000000000000000"
    turn_round()
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.refuseDelegate({'from': zero_address})


def test_refuse_delegate_canceled_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.refuseDelegate({'from': operators[0]})


def test_refuse_delegate_slashed_validator(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.misdemeanorThreshold(), slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[index])
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    candidate_hub.refuseDelegate({'from': operators[1]})
    turn_round(consensuses)


def test_refuse_delegate_repeated(candidate_hub, slash_indicator, set_candidate):
    validator_state = 17
    operators, consensuses = set_candidate
    turn_round()
    tx = candidate_hub.refuseDelegate({'from': operators[0]})
    assert tx.events['statusChanged']['oldStatus'] == validator_state
    assert tx.events['statusChanged']['newStatus'] == validator_state + 2
    tx = candidate_hub.refuseDelegate({'from': operators[0]})
    assert 'statusChanged' not in tx.events
    turn_round(consensuses)


def test_accept_delegate_success(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    assert candidate_hub.canDelegate(operators[0]) is False
    turn_round()
    candidate_hub.acceptDelegate({'from': operators[0]})
    assert candidate_hub.canDelegate(operators[0])


def test_accept_delegate_nonexistent_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.acceptDelegate({'from': consensuses[0]})


def test_accept_delegate_zero_address(candidate_hub, set_candidate):
    zero_address = "0x0000000000000000000000000000000000000000"
    turn_round()
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.acceptDelegate({'from': zero_address})


def test_accept_delegate_canceled_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    turn_round()
    candidate_hub.unregister({'from': operators[0]})
    with brownie.reverts(f"candidate does not exist"):
        candidate_hub.acceptDelegate({'from': operators[0]})


def test_accept_delegate_slashed_validator(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.misdemeanorThreshold(), slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[index])
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    candidate_hub.acceptDelegate({'from': operators[0]})
    candidate_hub.refuseDelegate({'from': operators[1]})
    candidate_hub.acceptDelegate({'from': operators[1]})
    turn_round(consensuses)
    assert candidate_hub.canDelegate(operators[0])
    assert candidate_hub.canDelegate(operators[1]) is False


def test_accept_delegate_repeated(candidate_hub, slash_indicator, set_candidate):
    validator_state = 19
    operators, consensuses = set_candidate
    turn_round()
    candidate_hub.refuseDelegate({'from': operators[0]})
    tx = candidate_hub.acceptDelegate({'from': operators[0]})
    assert tx.events['statusChanged']['oldStatus'] == validator_state
    assert tx.events['statusChanged']['newStatus'] == validator_state - 2
    tx = candidate_hub.acceptDelegate({'from': operators[0]})
    assert 'statusChanged' not in tx.events
    turn_round(consensuses)


def test_add_margin_insufficient_funds(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[0])
    turn_round(consensuses)
    assert candidate_hub.canDelegate(operators[0]) is False
    candidate_hub.addMargin({'from': operators[0], 'value': 100})
    assert candidate_hub.canDelegate(operators[0]) is False


def test_get_candidates_success(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[0])
    turn_round(consensuses)
    candidate_hub.refuseDelegate({'from': operators[1]})
    turn_round(consensuses)
    candidate_hub.unregister({'from': operators[1]})
    assert operators[0] in candidate_hub.getCandidates()
    assert operators[2] in candidate_hub.getCandidates()


def test_is_candidate_by_consensus_success(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    assert candidate_hub.isCandidateByConsensus(consensuses[0])


def test_query_consensus_by_non_validator(candidate_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    assert candidate_hub.isCandidateByConsensus(operators[0]) is False


def test_is_jailed_success(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[0])
    turn_round(consensuses)
    assert candidate_hub.isJailed(operators[0])


def test_query_jail_round_by_non_validator(candidate_hub, slash_indicator, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    for index, slash in enumerate([slash_indicator.felonyThreshold()]):
        for i in range(slash):
            slash_indicator.slash(consensuses[0])
    turn_round(consensuses)
    assert candidate_hub.isJailed(operators[1]) is False


def test_is_candidate_by_operate(candidate_hub, required_margin):
    operator = accounts[0]
    candidate_hub.register(
        random_address(), accounts[0], 1, random_vote_address(),
        {'from': operator, 'value': required_margin}
    )
    assert candidate_hub.isCandidateByOperate(operator) is True


def test_is_candidate_by_consensus(candidate_hub, required_margin):
    consensus_address = random_address()
    candidate_hub.register(
        consensus_address, accounts[0], 1, random_vote_address(),
        {'from': accounts[0], 'value': required_margin}
    )
    assert candidate_hub.isCandidateByConsensus(consensus_address) is True


def test_get_candidates(candidate_hub, required_margin):
    operator = accounts[0]
    candidate_hub.register(
        random_address(), accounts[0], 1, random_vote_address(),
        {'from': operator, 'value': required_margin}
    )
    assert operator in candidate_hub.getCandidates()


def test_accept_delegate(candidate_hub, required_margin):
    fee_address = random_address()

    tests = [
        (accounts[1], None, None, None, None, False, "candidate does not exist"),
        (accounts[2], True, None, "1", False, True, ""),
        (accounts[3], True, 17, "17", False, True, ""),
        (accounts[4], True, 1, "1", False, True, ""),
        (accounts[5], True, 49, "49", False, True, ""),
        (accounts[6], True, 3, "1", True, True, ""),
        (accounts[7], True, 19, "17", True, True, ""),
        (accounts[8], True, 11, "9", True, True, ""),
    ]

    for operate_addr, register, set_status, status, check_event, ret, err in tests:
        old_status = 1
        if register:
            candidate_hub.register(random_address(), fee_address, 10, random_vote_address(),
                                   {'from': operate_addr, 'value': required_margin})
        if set_status is not None:
            candidate_hub.setCandidateStatus(operate_addr, set_status, {'from': operate_addr})
            old_status = set_status
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.acceptDelegate({'from': operate_addr})
        else:
            tx = candidate_hub.acceptDelegate({"from": operate_addr})
            if check_event:
                expect_event(tx, "statusChanged", {
                    "operateAddr": operate_addr,
                    "oldStatus": old_status,
                    "newStatus": status
                })
            assert candidate_hub.getCandidate(operate_addr).dict()['status'] == status


def test_refuse_delegate(candidate_hub, required_margin):
    fee_address = random_address()

    tests = [
        (accounts[1], False, "candidate does not exist", None, None, None, None),
        (accounts[2], True, "", True, 3, "3", False),
        (accounts[3], True, "", True, None, "3", True)
    ]
    for operate_addr, ret, err, register, set_status, status, check_event in tests:
        old_status = 1
        if register:
            candidate_hub.register(random_address(), fee_address, 10, random_vote_address(),
                                   {'from': operate_addr, 'value': required_margin})
        if set_status is not None:
            candidate_hub.setCandidateStatus(operate_addr, set_status, {'from': operate_addr})
            old_status = set_status
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.refuseDelegate({'from': operate_addr})
        else:
            tx = candidate_hub.refuseDelegate({'from': operate_addr})
            if check_event:
                expect_event(tx, "statusChanged", {
                    "operateAddr": operate_addr,
                    "oldStatus": old_status,
                    "newStatus": status
                })
            assert candidate_hub.getCandidate(operate_addr).dict()['status'] == status


def test_unregister_when_only_one_validator(candidate_hub, validator_set, set_candidate_status, set_inactive_status):
    consensus = register_candidate()
    turn_round()
    assert len(validator_set.getValidators()) == 1

    candidate_hub.refuseDelegate()
    turn_round()
    candidate = get_candidate(accounts[0])
    assert candidate['status'] == set_candidate_status | set_inactive_status
    candidate_hub.unregister()
    turn_round()
    validators = validator_set.getValidators()
    assert validators == [consensus]
    turn_round([consensus])


def test_unregister_all(candidate_hub, validator_set):
    register_candidate(operator=accounts[1])
    register_candidate(operator=accounts[2])
    turn_round()

    assert len(validator_set.getValidators()) == 2

    candidate_hub.refuseDelegate({'from': accounts[1]})
    candidate_hub.refuseDelegate({'from': accounts[2]})
    turn_round()
    assert len(validator_set.getValidators()) == 2


def test_bond_update_registration_failure(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    update_system_contract_address(candidate_hub, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(required_margin * 2), 64)
    candidate_hub.updateParam('requiredMargin', hex_value)
    with brownie.reverts('deposit is not enough'):
        candidate_hub.register(consensus_address, fee_address, 1, random_vote_address(),
                               {'from': accounts[1], 'value': required_margin})


def test_register_candidate(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()

    tests = [
        (accounts[1], consensus_address, fee_address, 0, required_margin, False,
         "commissionThousandths should be in (0, 1000)"),
        (accounts[1], consensus_address, fee_address, 1000, required_margin, False,
         "commissionThousandths should be in (0, 1000)"),
        (accounts[1], consensus_address, fee_address, 1, required_margin - 1, False, "deposit is not enough"),
        (accounts[3], consensus_address, fee_address, 1, required_margin, False, "it is in jail"),
        (accounts[1], consensus_address, fee_address, 100, required_margin, True, ""),
        (accounts[1], random_address(), fee_address, 100, required_margin, False, "candidate already exists"),
        (accounts[2], consensus_address, fee_address, 100, required_margin, False, "consensus already exists")
    ]

    candidate_hub.setJailMap(accounts[3], 299, {'from': accounts[3]})
    assert candidate_hub.jailMap(accounts[3]) == 299

    for operate_addr, consensus_addr, fee_addr, commission, value, ret, err in tests:
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.register(consensus_addr, fee_addr, commission, random_vote_address(),
                                       {'from': operate_addr, 'value': value})
        else:
            tx = candidate_hub.register(consensus_addr, fee_addr, commission, random_vote_address(),
                                        {'from': operate_addr, 'value': value})
            expect_event(tx, "registered", {
                "operateAddr": operate_addr,
                "consensusAddr": consensus_addr,
                "feeAddress": fee_addr,
                "commissionThousandths": commission,
                "margin": value
            })


def test_unregister_candidate(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()

    candidate_hub.register(consensus_address, fee_address, 10, random_vote_address(),
                           {'from': accounts[3], 'value': required_margin})

    tests = [
        (accounts[1], None, False, "candidate does not exist", None, None, None),
        (accounts[3], 4, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 5, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 6, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 7, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 13, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 14, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 15, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 16, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 17, False, "candidate status is not cleared", None, None, None),
        (accounts[3], 1, True, "", 0, None, None),
        (accounts[3], None, True, "", candidate_hub.dues(), True, consensus_address),
        (accounts[2], None, True, "", None, True, consensus_address),
    ]

    for operate_addr, set_status, ret, err, set_margin, register, consensus_addr in tests:
        if register is True:
            if consensus_addr is None:
                consensus_addr = random_address()
            candidate_hub.register(consensus_addr, fee_address, 10, random_vote_address(),
                                   {'from': operate_addr, "value": required_margin})
        if consensus_addr is None:
            consensus_addr = consensus_address
        if set_status is not None:
            candidate_hub.setCandidateStatus(operate_addr, set_status, {'from': operate_addr})
        if set_margin is not None:
            candidate_hub.setCandidateMargin(operate_addr, set_margin, {'from': operate_addr})
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.unregister({"from": operate_addr})
        else:
            tx = candidate_hub.unregister({'from': operate_addr})
            expect_event(tx, "unregistered", {
                'operateAddr': operate_addr,
                'consensusAddr': consensus_addr
            })


def test_add_margin(candidate_hub, required_margin):
    fee_address = random_address()

    tests = [
        (accounts[1], None, None, 1, None, None, None, False, "candidate does not exist"),
        (accounts[2], True, None, 0, None, None, None, False, "value should not be zero"),
        (accounts[2], None, required_margin, 1, None, 1, False, True, ""),
        (accounts[2], None, 1, 1, 9, "9", False, True, ""),
        (accounts[2], None, 1, required_margin - 1, 9, "1", True, True, ""),
        (accounts[2], None, 1, required_margin - 1, 11, "3", True, True, ""),
        (accounts[2], None, 1, required_margin - 1, 25, "17", True, True, ""),
        (accounts[2], None, 1, required_margin, 9, "1", True, True, "")
    ]
    for operate_addr, register, set_margin, value, set_status, status, check_event, ret, err in tests:
        old_status = 1
        if register:
            candidate_hub.register(random_address(), fee_address, 10, random_vote_address(),
                                   {'from': operate_addr, 'value': required_margin})
        if set_status is not None:
            candidate_hub.setCandidateStatus(operate_addr, set_status, {'from': operate_addr})
            old_status = set_status
        if set_margin is not None:
            candidate_hub.setCandidateMargin(operate_addr, set_margin, {'from': operate_addr})
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.addMargin({'from': operate_addr, 'value': value})
        else:
            tx = candidate_hub.addMargin({'from': operate_addr, 'value': value})
            if check_event:
                expect_event(tx, "statusChanged", {
                    "operateAddr": operate_addr,
                    "oldStatus": old_status,
                    "newStatus": status
                })
            expect_event(tx, "addedMargin", {
                "operateAddr": operate_addr,
                "margin": value,
                "totalMargin": set_margin + value
            })
            assert candidate_hub.getCandidate(operate_addr).dict()['status'] == status


# getValidators
def test_get_validators(candidate_hub):
    candidates = []
    score_list1 = []
    score_list2 = []
    indexes = []

    for i in range(1000):
        candidates.append(Account.create(str(random.random())).address)
        score_list1.append(i)
        score_list2.append(999 - i)
        indexes.append(i)

    tests = [
        (candidates, score_list1, indexes, 1, 1),
        (candidates, score_list1, indexes, 10, 10),
        (candidates, score_list2, indexes, 1, 1),
        (candidates, score_list2, indexes, 10, 10),
        (candidates[:21], score_list2[:21], indexes[:21], 21, 21),
        (candidates[:10], score_list1[:10], indexes[:10], 21, 10),
        (candidates[:10], score_list2[:10], indexes[:10], 21, 10),
    ]
    sorted_count = 0
    for candidate_list, score_list, index_list, count, expect_count in tests:
        validator_list = candidate_hub.getValidatorsMock(candidate_list, score_list, count, sorted_count)
        index_list.sort(key=lambda e: score_list[e], reverse=True)
        for i in range(expect_count):
            flag = False
            for validator in validator_list:
                if validator == candidates[index_list[i]]:
                    flag = True
                    break
            assert flag is True
        assert len(validator_list) == expect_count


def test_get_validators_single_candidate(candidate_hub):
    candidates = [accounts[1]]
    scores = [123]
    result = candidate_hub.getValidatorsMock(candidates, scores, 1, 0)
    assert result == [accounts[1]]
    result2 = candidate_hub.getValidatorsMock(candidates, scores, 3, 0)
    assert result2 == [accounts[1]]
    with brownie.reverts():
        result3 = candidate_hub.getValidatorsMock(candidates, scores, 3, 1)


def test_get_validators_basic(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3]]
    scores = [100, 200, 150]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 0)
    assert result == candidates
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 2)
    assert result == [accounts[2], accounts[3], accounts[1]]


def test_get_validators_more_candidates(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3], accounts[4], accounts[5]]
    scores = [100, 200, 150, 300, 250]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 0)
    assert result == [accounts[4], accounts[5], accounts[2]]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 2)
    assert result == [accounts[4], accounts[5], accounts[2]]


def test_get_validators_candidates_less_than_count(candidate_hub):
    candidates = [accounts[1], accounts[2]]
    scores = [100, 200]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 0)
    assert set(result) == set(candidates)
    assert len(result) == 2
    result2 = candidate_hub.getValidatorsMock(candidates, scores, 3, 1)
    assert result2 == [accounts[2], accounts[1]]
    assert len(result2) == 2


def test_get_validators_mixed_order_with_sorted_count(candidate_hub):
    candidates = [random_address() for _ in range(10)]
    scores = [3000, 2000, 1100, 8000, 1000, 7000, 4000, 10000, 5000, 6000]
    max_alternate_count = 12
    count = 8
    get_alternate_count = candidate_hub.getAlternateCountMock(max_alternate_count, count, len(candidates))
    assert get_alternate_count == 2
    result = candidate_hub.getValidatorsMock(candidates, scores, count + get_alternate_count, get_alternate_count)
    assert result[-2] == candidates[2]
    assert result[-1] == candidates[4]
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    expected = [candidates[i] for i in sorted_indices[:8]]
    assert result[:-2] != expected[:-2]


def test_get_validators_sorted_count_eq_count(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3], accounts[4], accounts[5]]
    scores = [500, 400, 300, 200, 100]
    with brownie.reverts("count should be greater than sortedCount"):
        result = candidate_hub.getValidatorsMock(candidates, scores, 3, 3)


def test_get_validators_with_sorted_count_equal_scores(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3], accounts[4], accounts[5]]
    scores = [200, 300, 200, 300, 100]
    result = candidate_hub.getValidatorsMock(candidates, scores, 4, 2)
    assert len(result) == 4
    assert result[0] in [accounts[2], accounts[4]]
    assert result[1] in [accounts[2], accounts[4]]
    assert result[2] in [accounts[1], accounts[3]]
    assert result[3] in [accounts[1], accounts[3]]


def test_get_validators_with_sorted_count_zero_scores(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3], accounts[4], accounts[5]]
    scores = [0, 0, 300, 0, 200]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 1)
    assert result == [accounts[3], accounts[5], accounts[4]]


def test_get_validators_many_candidates_with_sorted_count(candidate_hub):
    candidates = [accounts[i] for i in range(1, 31)]
    scores = [1000 - i * 10 for i in range(30)]
    random.shuffle(scores)
    canditates_dict = {accounts[i]: scores[i - 1] for i in range(1, 31)}

    result = candidate_hub.getValidatorsMock(candidates, scores, 21, 10)
    sorted_canditates = sorted(canditates_dict.items(), key=lambda x: x[1], reverse=True)
    for i in sorted_canditates[:11]:
        assert i[0] in result[:11]
    assert result[11:] == [i[0] for i in sorted_canditates[11:21]]
    for validator in result:
        assert validator in candidates


def test_get_validators_with_equal_scores(candidate_hub):
    candidates = [accounts[1], accounts[2], accounts[3], accounts[4]]
    scores = [200, 200, 150, 200]
    result = candidate_hub.getValidatorsMock(candidates, scores, 3, 0)
    assert len(result) == 3
    for addr in result:
        assert addr in [accounts[1], accounts[2], accounts[4]]


def test_jail_validator(candidate_hub, validator_set, required_margin):
    fee_address = random_address()

    tests = [
        (accounts[1], None, 1, None, None, None, 1, False, True, ""),
        (accounts[2], True, 1, required_margin, 17, 29, 1, None, True, ""),
        (accounts[3], True, 1, required_margin, 19, 31, 1, True, True, ""),
        (accounts[4], True, 1, required_margin, 17, 29, required_margin, None, True, ""),
        (accounts[5], True, 1, required_margin + 1, 19, 23, 1, True, True, ""),
        (accounts[6], True, 1, required_margin, 17, 29, required_margin * 2, True, True, "")
    ]

    for operate_addr, register, _round, set_margin, set_status, status, fine, check_event, ret, err in tests:
        old_status = 1
        if register:
            candidate_hub.register(random_address(), fee_address, 10, random_vote_address(),
                                   {'from': operate_addr, 'value': required_margin})
        if set_status is not None:
            candidate_hub.setCandidateStatus(operate_addr, set_status, {'from': operate_addr})
            old_status = set_status
        if set_margin is not None:
            candidate_hub.setCandidateMargin(operate_addr, set_margin, {'from': operate_addr})
        if ret is False:
            with brownie.reverts(err):
                validator_set.jailValidator(operate_addr, _round, fine, {'from': operate_addr})
        else:
            tx = validator_set.jailValidator(operate_addr, _round, fine, {'from': operate_addr})
            if not register:
                assert len(tx.events.keys()) == 0
            else:
                if set_margin >= candidate_hub.dues() + fine:
                    expect_event(tx, "statusChanged", {
                        "operateAddr": operate_addr,
                        "oldStatus": old_status,
                        "newStatus": status
                    })
                    expect_event(tx, "deductedMargin", {
                        "operateAddr": operate_addr,
                        "margin": fine,
                        "totalMargin": set_margin - fine
                    })
                    assert candidate_hub.getCandidate(operate_addr).dict()['status'] == status
                else:
                    expect_event(tx, "unregistered", {
                        "operateAddr": operate_addr
                    })
                    expect_event(tx, "deductedMargin", {
                        "operateAddr": operate_addr,
                        "margin": set_margin,
                        "totalMargin": 0
                    })


def test_turn_round(candidate_hub, core_agent, validator_set, required_margin):
    required_coin_deposit = core_agent.requiredCoinDeposit()
    validator_count = candidate_hub.validatorCount()

    tests = [
        ([accounts[1]], [required_coin_deposit], [1], [17]),
        (accounts[1:3], [0, required_coin_deposit], [1, 1], [17, 17]),
        (accounts[1:validator_count + 2], [0] + [required_coin_deposit] * validator_count, [1] * (validator_count + 1),
         [1] + [17] * validator_count),
        (accounts[1:validator_count + 2], [0, 0] + [required_coin_deposit] * (validator_count - 1),
         [1] * (validator_count + 1), [1] + [17] * (validator_count)),
        (accounts[1:6], [0] * 5, [1, 3, 5, 9, 17], [17, 3, 5, 9, 17])
    ]
    for agents, deposit, set_status, status in tests:
        for agent, _set_status in zip(agents, set_status):
            candidate_hub.register(agent, agent, 10, random_vote_address(), {'from': agent, 'value': required_margin})
            candidate_hub.setCandidateStatus(agent, _set_status, {'from': agent})
        for agent, _deposit in zip(agents, deposit):
            if _deposit > 0:
                __delegate_coin_success(core_agent, agent, agent, 0, _deposit)

        turn_round()

        for agent, _status in zip(agents, status):
            assert candidate_hub.getCandidate(agent).dict()['status'] == _status
        for agent in agents:
            candidate_hub.refuseDelegate({'from': agent})

        turn_round()

        for agent, _deposit in zip(agents, deposit):
            current_status = candidate_hub.getCandidate(agent).dict()['status']
            if current_status == (current_status & candidate_hub.UNREGISTER_STATUS()):
                candidate_hub.unregister({'from': agent})
            if _deposit > 0:
                core_agent.undelegateCoin(agent, _deposit, {'from': agent})


def test_unregister_reentry(candidate_hub, required_margin, stake_hub):
    candidate_hub_proxy = UnRegisterReentry.deploy(candidate_hub.address, stake_hub, {'from': accounts[0]})
    register_candidate(operator=accounts[1])
    candidate_hub_proxy.register(random_address(), candidate_hub_proxy.address, 500, {'value': required_margin})
    tx = candidate_hub_proxy.unregister()
    expect_event(tx, "proxyUnregister", {
        "success": False,
        "msg": "candidate does not exist"
    })


def test_getRoundInterval_success(candidate_hub, required_margin, stake_hub):
    interval = 86400
    assert interval == candidate_hub.getRoundInterval()


def __delegate_coin_success(core_agent, agent, delegator, old_value, new_value):
    tx = core_agent.delegateCoin(agent, {'from': delegator, 'value': new_value})
    expect_event(tx, "delegatedCoin", {
        "candidate": agent,
        "delegator": delegator,
        "amount": new_value,
        "realtimeAmount": new_value + old_value
    })


# updateAgent
def test_update_agent_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.updateAgent(accounts[1], {'from': accounts[1]})


def test_update_agent_success(candidate_hub, accounts):
    operator = accounts[5]
    new_agent = accounts[6]

    consensus_addr = accounts[7]
    fee_addr = accounts[8]
    vote_addr = random_vote_address()

    candidate_hub.register(
        consensus_addr,
        fee_addr,
        100,  # commissionThousandths
        vote_addr,
        {'from': operator, 'value': 1e18}
    )

    tx = candidate_hub.updateAgent(new_agent, {'from': operator})

    assert len(tx.events['AgentUpdated']) > 0
    assert tx.events['AgentUpdated']['operateAddr'] == operator
    assert tx.events['AgentUpdated']['newAgent'] == new_agent
    assert candidate_hub.exMap(operator)['agent'] == new_agent
    assert candidate_hub.agentMap(new_agent) != 0


def test_update_agent_zero_address(candidate_hub, accounts):
    operator = accounts[5]

    consensus_addr = accounts[7]
    fee_addr = accounts[8]
    vote_addr = random_vote_address()

    candidate_hub.register(
        consensus_addr,
        fee_addr,
        100,
        vote_addr,
        {'from': operator, 'value': 1e18}
    )

    with brownie.reverts("agent address cannot be zero"):
        candidate_hub.updateAgent(ZERO_ADDRESS, {'from': operator})


def test_update_agent_already_exists(candidate_hub):
    operator1 = accounts[5]
    operator2 = accounts[6]
    agent = accounts[7]

    candidate_hub.register(
        accounts[8],
        accounts[9],
        100,
        random_vote_address(),
        {'from': operator1, 'value': 1e18}
    )

    candidate_hub.register(
        accounts[10],
        accounts[11],
        100,
        random_vote_address(),
        {'from': operator2, 'value': 1e18}
    )

    candidate_hub.updateAgent(agent, {'from': operator1})
    with brownie.reverts("agent address already exists"):
        candidate_hub.updateAgent(agent, {'from': operator2})
    candidate_hub.updateAgent(accounts[13], {'from': operator2})
    assert candidate_hub.agentMap(accounts[13]) == 2
    candidate_hub.updateAgent(accounts[11], {'from': operator1})
    candidate_hub.updateAgent(agent, {'from': operator2})
    assert candidate_hub.agentMap(accounts[11]) == 1
    assert candidate_hub.agentMap(agent) == 2


def test_update_agent_multiple_times(candidate_hub, accounts):
    operator = accounts[5]
    first_agent = accounts[6]
    second_agent = accounts[7]

    candidate_hub.register(
        accounts[8],
        accounts[9],
        100,
        random_vote_address(),
        {'from': operator, 'value': 1e18}
    )

    tx1 = candidate_hub.updateAgent(first_agent, {'from': operator})
    assert len(tx1.events['AgentUpdated']) > 0
    assert candidate_hub.agentMap(first_agent) != 0

    tx2 = candidate_hub.updateAgent(second_agent, {'from': operator})
    assert len(tx2.events['AgentUpdated']) > 0
    assert candidate_hub.agentMap(second_agent) != 0
    assert candidate_hub.agentMap(first_agent) == 0


# removeAgent
def test_remove_agent_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.removeAgent({'from': accounts[1]})
    candidate_hub.register(
        accounts[8],
        accounts[9],
        100,
        random_vote_address(),
        {'from': accounts[1], 'value': 1e18}
    )
    candidate_hub.updateAgent(accounts[2], {'from': accounts[1]})
    with brownie.reverts("candidate does not exist"):
        candidate_hub.removeAgent({'from': accounts[2]})


def test_remove_agent_no_agent(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator)

    with brownie.reverts("agent address does not exist"):
        candidate_hub.removeAgent({'from': operator})


def test_remove_agent_success(candidate_hub, accounts):
    operator = accounts[5]
    agent = accounts[6]
    register_candidate(operator=operator)

    candidate_hub.updateAgent(agent, {'from': operator})
    assert candidate_hub.agentMap(agent) != 0
    assert candidate_hub.exMap(operator)['agent'] == agent

    candidate_hub.removeAgent({'from': operator})
    assert candidate_hub.agentMap(agent) == 0
    assert candidate_hub.exMap(operator)['agent'] == ZERO_ADDRESS


# editConsensusAddress
def test_edit_consensus_address_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.editConsensusAddress(accounts[1], {'from': accounts[1]})


def test_edit_consensus_address_duplicate(candidate_hub, accounts):
    operator1 = accounts[5]
    operator2 = accounts[6]
    consensus1 = register_candidate(operator=operator1)
    consensus2 = register_candidate(operator=operator2)

    with brownie.reverts("consensus already exists"):
        candidate_hub.editConsensusAddress(consensus2, {'from': operator1})


def test_edit_consensus_address_success(candidate_hub, accounts):
    operator = accounts[5]
    old_consensus = register_candidate(operator=operator)
    new_consensus = accounts[7]

    tx = candidate_hub.editConsensusAddress(new_consensus, {'from': operator})

    assert 'ConsensusAddressEdited' in tx.events
    assert tx.events['ConsensusAddressEdited']['operateAddr'] == operator
    assert tx.events['ConsensusAddressEdited']['newConsensusAddr'] == new_consensus
    assert candidate_hub.isCandidateByConsensus(old_consensus) is False
    assert candidate_hub.isCandidateByConsensus(new_consensus)
    assert candidate_hub.candidateSet(0).dict()['consensusAddr'] == new_consensus


def test_edit_consensus_address_by_agent_success(candidate_hub, accounts):
    operator = accounts[5]
    agent = accounts[6]
    old_consensus = register_candidate(operator=operator)
    new_consensus = accounts[7]

    candidate_hub.updateAgent(agent, {'from': operator})

    tx = candidate_hub.editConsensusAddress(new_consensus, {'from': agent})

    assert 'ConsensusAddressEdited' in tx.events


# editCommissionRate
def test_edit_commission_rate_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.editCommissionRate(100, {'from': accounts[1]})


def test_edit_commission_rate_range(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator)

    with brownie.reverts("commissionThousandths should in range (0, 1000)"):
        candidate_hub.editCommissionRate(0, {'from': operator})

    with brownie.reverts("commissionThousandths should in range (0, 1000)"):
        candidate_hub.editCommissionRate(1000, {'from': operator})


def test_edit_commission_rate_adjustment_range(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator, commission=500)
    max_change = candidate_hub.maxCommissionChange()

    with brownie.reverts("commissionThousandths out of adjustment range"):
        candidate_hub.editCommissionRate(
            500 + max_change + 1, {'from': operator})

    with brownie.reverts("commissionThousandths out of adjustment range"):
        candidate_hub.editCommissionRate(
            500 - max_change - 1, {'from': operator})
    tx = candidate_hub.editCommissionRate(500 + max_change, {'from': operator})
    assert 'CommissionRateEdited' in tx.events
    with brownie.reverts("commissionThousandths out of adjustment range"):
        candidate_hub.editCommissionRate(
            500 + max_change + 1, {'from': operator})


def test_edit_commission_rate_by_agent_success(candidate_hub, accounts):
    operator = accounts[5]
    agent = accounts[6]
    register_candidate(operator=operator, commission=500)
    new_rate = 600

    candidate_hub.updateAgent(agent, {'from': operator})

    tx = candidate_hub.editCommissionRate(new_rate, {'from': agent})
    assert 'CommissionRateEdited' in tx.events


def test_edit_commission_rate_success(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator, commission=500)
    new_rate = 600

    tx = candidate_hub.editCommissionRate(new_rate, {'from': operator})

    assert 'CommissionRateEdited' in tx.events
    assert tx.events['CommissionRateEdited']['operateAddr'] == operator
    assert tx.events['CommissionRateEdited']['newRate'] == new_rate
    assert candidate_hub.candidateSet(
        0).dict()['commissionThousandths'] == new_rate
    assert candidate_hub.candidateSet(
        0).dict()['commissionLastChangeRound'] == get_current_round()
    assert candidate_hub.candidateSet(
        0).dict()['commissionLastRoundValue'] == 500


def test_edit_commission_rate_same_round_multiple_times(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator, commission=500)
    max_change = candidate_hub.maxCommissionChange()

    new_rate1 = 500 + max_change
    tx1 = candidate_hub.editCommissionRate(new_rate1, {'from': operator})
    assert 'CommissionRateEdited' in tx1.events
    assert tx1.events['CommissionRateEdited']['newRate'] == new_rate1

    new_rate2 = 500 + max_change
    tx2 = candidate_hub.editCommissionRate(new_rate2, {'from': operator})
    assert 'CommissionRateEdited' in tx2.events
    assert tx2.events['CommissionRateEdited']['newRate'] == new_rate2

    new_rate3 = 500 - max_change
    tx3 = candidate_hub.editCommissionRate(new_rate3, {'from': operator})
    assert 'CommissionRateEdited' in tx3.events
    assert tx3.events['CommissionRateEdited']['newRate'] == new_rate3

    candidate = candidate_hub.candidateSet(0).dict()
    assert candidate['commissionThousandths'] == new_rate3
    assert candidate['commissionLastChangeRound'] == get_current_round()
    assert candidate['commissionLastRoundValue'] == 500

    with brownie.reverts("commissionThousandths out of adjustment range"):
        candidate_hub.editCommissionRate(
            500 + max_change + 1, {'from': operator})

    with brownie.reverts("commissionThousandths out of adjustment range"):
        candidate_hub.editCommissionRate(
            500 - max_change - 1, {'from': operator})


def test_remove_candidate_agent_map_index(candidate_hub, slash_indicator):
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    turn_round()
    agents = [accounts[10], accounts[11], accounts[12], accounts[13], accounts[14]]
    candidate_hub.setDues(1e18)
    for i in range(1, 5):
        candidate_hub.updateAgent(agents[i], {'from': operators[i]})
    for i in range(5):
        assert candidate_hub.operateMap(operators[i]) == i + 1
        assert candidate_hub.getConsensusMap(consensuses[i]) == i + 1
    for i in range(1, 5):
        assert candidate_hub.agentMap(agents[i]) == i + 1
    assert candidate_hub.agentMap(agents[0]) == 0
    vote_addr = random_vote_address()
    candidate_hub.editVoteAddress(vote_addr, {'from': operators[0]})
    assert candidate_hub.exMap(operators[0])['voteAddr'] == vote_addr
    felony_threshold = slash_indicator.felonyThreshold()
    for _ in range(felony_threshold):
        tx = slash_indicator.slash(consensuses[0])
    candidate_hub.editVoteAddress(random_vote_address(), {'from': agents[-1]})
    result = [0, 2, 3, 4, 1]
    for r in range(1, 5):
        assert candidate_hub.operateMap(operators[r]) == result[r]
        assert candidate_hub.getConsensusMap(consensuses[r]) == result[r]
        assert candidate_hub.agentMap(agents[r]) == result[r]
    assert candidate_hub.agentMap(agents[0]) == 0
    assert candidate_hub.operateMap(operators[0]) == 0
    assert candidate_hub.getConsensusMap(consensuses[0]) == 0
    assert candidate_hub.exMap(operators[0])['voteAddr'] == ZERO_ADDRESS


def test_remove_candidate_agent_map_index_with_all_agents(candidate_hub, slash_indicator):
    operators = []
    consensuses = []
    for operator in accounts[5:12]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    agents = [accounts[13], accounts[14], accounts[15], accounts[16], accounts[17], accounts[18], accounts[19]]
    for i in range(7):
        candidate_hub.updateAgent(agents[i], {'from': operators[i]})
    for i in range(7):
        assert candidate_hub.operateMap(operators[i]) == i + 1
        assert candidate_hub.getConsensusMap(consensuses[i]) == i + 1
        assert candidate_hub.agentMap(agents[i]) == i + 1
    candidate_hub.unregister({'from': operators[2]})
    candidate_list = candidate_hub.getCandidates()
    assert len(candidate_list) == 6
    assert candidate_hub.operateMap(operators[-1]) == 3
    assert candidate_hub.getConsensusMap(consensuses[-1]) == 3
    assert candidate_hub.agentMap(agents[-1]) == 3
    vote_addr = random_vote_address()
    candidate_hub.editVoteAddress(vote_addr, {'from': agents[-1]})
    assert candidate_hub.exMap(operators[-1])['voteAddr'] == vote_addr
    assert candidate_hub.candidateSet(2).dict()['operateAddr'] == operators[-1]


# editVoteAddress
def test_edit_vote_address_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.editVoteAddress(
            random_vote_address(), {'from': accounts[1]})


def test_edit_vote_address_length(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator)

    invalid_vote_addr = "0x1234"
    with brownie.reverts("vote address length should be 48"):
        candidate_hub.editVoteAddress(invalid_vote_addr, {'from': operator})


def test_edit_vote_address_duplicate(candidate_hub, accounts):
    operator1 = accounts[5]
    operator2 = accounts[6]
    operator3 = accounts[7]
    consensus1 = register_candidate(operator=operator1)
    vote_addr1 = candidate_hub.exMap(operator1)['voteAddr']
    register_candidate(operator=operator2)
    register_candidate(operator=operator3)
    with brownie.reverts("vote address already exists"):
        candidate_hub.editVoteAddress(vote_addr1, {'from': operator2})
    vote_addr2 = candidate_hub.exMap(operator3)['voteAddr']
    with brownie.reverts("vote address already exists"):
        candidate_hub.editVoteAddress(vote_addr2, {'from': operator2})


def test_edit_vote_address_success(candidate_hub, accounts):
    operator = accounts[5]
    consensus = register_candidate(operator=operator)
    old_vote_addr = candidate_hub.exMap(operator)['voteAddr']
    new_vote_addr = random_vote_address()

    tx = candidate_hub.editVoteAddress(new_vote_addr, {'from': operator})

    assert 'VoteAddressEdited' in tx.events
    assert tx.events['VoteAddressEdited']['operateAddr'] == operator
    assert tx.events['VoteAddressEdited']['newVoteAddr'] == new_vote_addr
    assert candidate_hub.exMap(operator)['voteAddr'] == new_vote_addr


def test_edit_vote_address_by_agent_success(candidate_hub, accounts):
    operator = accounts[5]
    agent = accounts[6]
    register_candidate(operator=operator)
    new_vote_addr = random_vote_address()

    candidate_hub.updateAgent(agent, {'from': operator})

    tx = candidate_hub.editVoteAddress(new_vote_addr, {'from': agent})
    assert 'VoteAddressEdited' in tx.events


# editFeeAddress
def test_edit_fee_address_permission(candidate_hub, accounts):
    with brownie.reverts("candidate does not exist"):
        candidate_hub.editFeeAddress(accounts[1], {'from': accounts[1]})


def test_edit_fee_address_zero_address(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator)

    with brownie.reverts("fee address cannot be zero"):
        candidate_hub.editFeeAddress(ZERO_ADDRESS, {'from': operator})


def test_edit_fee_address_success(candidate_hub, accounts):
    operator = accounts[5]
    register_candidate(operator=operator)
    new_fee_addr = accounts[7]

    tx = candidate_hub.editFeeAddress(new_fee_addr, {'from': operator})

    assert 'FeeAddressEdited' in tx.events
    assert tx.events['FeeAddressEdited']['operateAddr'] == operator
    assert tx.events['FeeAddressEdited']['newFeeAddr'] == new_fee_addr
    assert candidate_hub.candidateSet(0).dict()['feeAddr'] == new_fee_addr


def test_edit_fee_address_by_agent_fail(candidate_hub, accounts):
    operator = accounts[5]
    agent = accounts[6]
    register_candidate(operator=operator)
    new_fee_addr = accounts[7]

    candidate_hub.updateAgent(agent, {'from': operator})

    with brownie.reverts("candidate does not exist"):
        tx = candidate_hub.editFeeAddress(new_fee_addr, {'from': agent})


def test_candidate_update_and_turn_round(candidate_hub, accounts, validator_set, set_candidate):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    lock_script = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
    validator_set.updateBlockReward(30000)
    operators, consensuses = set_candidate
    for i, delegator in enumerate(accounts[:3]):
        delegate_coin_success(operators[i], delegator, 10000)
        delegate_btc_success(operators[i], delegator, 200, lock_script, relay=delegator)
    turn_round()
    validator_count = len(consensuses)
    for i in range(validator_count):
        candidate_hub.updateAgent(accounts[i], {'from': operators[i]})
    turn_round(consensuses)
    candidate_hub.editVoteAddress(random_vote_address(), {'from': operators[0]})
    turn_round(consensuses)
    for i in range(validator_count):
        candidate_hub.editFeeAddress(accounts[i], {'from': operators[i]})
    for i in range(validator_count):
        new_commission = 500 + i
        candidate_hub.editCommissionRate(new_commission, {'from': operators[i]})
    turn_round(consensuses)
    for i, operator in enumerate(operators):
        index = candidate_hub.operateMap(operator)
        c = candidate_hub.candidateSet(index - 1).dict()
        assert candidate_hub.exMap(operator)['agent'] == accounts[i]
        assert c['feeAddr'] == accounts[i]
        assert c['commissionThousandths'] == 500 + i
    tx = stake_hub_claim_reward(accounts[0])
    assert 'claimedReward' in tx.events
    turn_round(consensuses)


# getAlternateCount
def test_get_alternate_count_basic_scenarios(candidate_hub):
    # candidateSize <= validatorCount, return 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 3, 2)
    assert alternate_count == 0

    # candidateSize = validatorCount, return 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 3, 3)
    assert alternate_count == 0

    # candidateSize < validatorCount + maxAlternateCount, return candidateSize - validatorCount
    alternate_count = candidate_hub.mockGetAlternateCount(5, 3, 5)
    assert alternate_count == 2  # 5 - 3 = 2

    # candidateSize >= validatorCount + maxAlternateCount, return maxAlternateCount
    alternate_count = candidate_hub.mockGetAlternateCount(5, 3, 10)
    assert alternate_count == 5


def test_get_alternate_count_edge_cases(candidate_hub):
    # all parameters are 0
    alternate_count = candidate_hub.mockGetAlternateCount(0, 0, 0)
    assert alternate_count == 0

    # maxAlternateCount is 0
    alternate_count = candidate_hub.mockGetAlternateCount(0, 3, 5)
    assert alternate_count == 0

    # validatorCount is 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 0, 3)
    assert alternate_count == 3

    # candidateSize is 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 3, 0)
    assert alternate_count == 0


def test_get_alternate_count_typical_scenarios(candidate_hub):
    # candidateSize = validatorCount, return 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 10, 10)
    assert alternate_count == 0

    # candidateSize > validatorCount, return candidateSize - validatorCount
    alternate_count = candidate_hub.mockGetAlternateCount(5, 10, 12)
    assert alternate_count == 2

    # candidateSize > validatorCount + maxAlternateCount, return maxAlternateCount
    alternate_count = candidate_hub.mockGetAlternateCount(5, 10, 20)
    assert alternate_count == 5

    # candidateSize < validatorCount, return 0
    alternate_count = candidate_hub.mockGetAlternateCount(5, 10, 8)
    assert alternate_count == 0


#  removeCandidate
def test_remove_candidate_success(candidate_hub, validator_set):
    operators = [acc for acc in accounts[5:10]]
    vote_addresses = [random_vote_address() for _ in range(5)]
    update_agents = [f'0x{"0" * 39}{i + 1}' for i in range(5)]
    consensuses = [register_candidate(operator=op) for op in operators]
    for op, agent, vote_addr in zip(operators, update_agents, vote_addresses):
        candidate_hub.updateAgent(agent, {'from': op})
        candidate_hub.editVoteAddress(vote_addr, {'from': op})

    turn_round()
    for i, op in enumerate(operators):
        candidate = candidate_hub.candidateSet(i)
        assert candidate == [op, consensuses[i], op, 500, 1000000, 17, 7, 500]
        assert candidate_hub.operateMap(op) == i + 1
        assert candidate_hub.getConsensusMap(consensuses[i]) == i + 1
        assert candidate_hub.exMap(op) == [update_agents[i], vote_addresses[i]]
        assert candidate_hub.agentMap(update_agents[i]) == i + 1

    candidate_hub.removeCandidateMock(2, {'from': operators[0]})
    candidate_set_order = [0,4,2,3]
    for index,i in enumerate(candidate_set_order):
        candidate = candidate_hub.candidateSet(index)
        assert candidate == [operators[i], consensuses[i], operators[i], 500, 1000000, 17, 7, 500]
        assert candidate_hub.operateMap(operators[i]) == index + 1
        assert candidate_hub.getConsensusMap(consensuses[i]) == index + 1
        assert candidate_hub.exMap(operators[i]) == [update_agents[i], vote_addresses[i]]
        assert candidate_hub.agentMap(update_agents[i]) == index + 1

    candidate_hub.removeCandidateMock(1, {'from': operators[0]})

    assert len(candidate_hub.getCandidates()) == 3
    candidate_set_order = [3, 4, 2]
    for index, i in enumerate(candidate_set_order):
        candidate = candidate_hub.candidateSet(index)
        assert candidate == [operators[i], consensuses[i], operators[i], 500, 1000000, 17, 7, 500]
        assert candidate_hub.operateMap(operators[i]) == index + 1
        assert candidate_hub.getConsensusMap(consensuses[i]) == index + 1
        assert candidate_hub.exMap(operators[i]) == [update_agents[i], vote_addresses[i]]
        assert candidate_hub.agentMap(update_agents[i]) == index + 1
