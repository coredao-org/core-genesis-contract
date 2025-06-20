import random
import pytest
import brownie
from web3 import Web3
from eth_account import Account
from brownie import accounts, UnRegisterReentry, chain
from brownie.test import given, strategy
from brownie.network.transaction import Status, TransactionReceipt
from .constant import Utils
from .utils import random_address, expect_event, padding_left, update_system_contract_address
from .common import register_candidate, turn_round, get_candidate, get_current_round, random_vote_address


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
    vote_address_list = [Web3.to_hex(random_vote_address()) for _ in range(3)]
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_address_list[index]))
    assert validator_set.getValidatorsAndVoteAddresses()[1] == [Web3.to_hex(init_vote_address)] * 5
    tx = turn_round()
    assert 'validatorSetUpdated' in tx.events
    assert validator_set.getValidatorsAndVoteAddresses()[0] == consensuses
    assert validator_set.getValidatorsAndVoteAddresses()[1] == vote_address_list
    turn_round(consensuses)
    assert validator_set.currentValidatorSet(0) == [operators[0], consensuses[0], operators[0], 1000, 0,
                                                    vote_address_list[0], 0]


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
        commission_last_round,
        vote_address,
    )
    assert candidate_hub.operateMap(accounts[1]) == 1
    assert candidate_hub.getConsensusMap(consensus_addr) == 1
    consensus = register_candidate(operator=accounts[2])
    assert candidate_hub.operateMap(accounts[2]) == 2
    assert candidate_hub.getConsensusMap(consensus) == 2
    assert candidate_hub.candidateSet(1)['operateAddr'] == accounts[2]


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


def test_update_candidate(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    max_commission_change = candidate_hub.maxCommissionChange()

    tests = [
        (accounts[1], None, consensus_address, fee_address, 100, False, "candidate does not exist", None),
        (accounts[2], True, consensus_address, fee_address, 0, False, "commissionThousandths should in range (0, 1000)",
         None),
        (accounts[3], True, random_address(), fee_address, 1000, False,
         "commissionThousandths should in range (0, 1000)", None),
        (accounts[3], None, consensus_address, fee_address, 100, False, "the consensus already exists", None),
        (accounts[3], None, random_address(), fee_address, 201 + max_commission_change, False,
         "commissionThousandths out of adjustment range", None),
        (accounts[3], None, random_address(), fee_address, 199 - max_commission_change, False,
         "commissionThousandths out of adjustment range", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 - max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change * 2, True, "", True),
    ]
    i = 0
    for operate_addr, register, consensus_addr, fee_addr, commission, ret, err, need_turn_round in tests:
        if need_turn_round:
            turn_round()
        i += 1
        vote_address0 = random_vote_address()
        vote_address1 = random_vote_address()
        vote_address2 = random_vote_address()
        if register:
            if consensus_addr is None:
                consensus_addr = random_address()
            candidate_hub.register(consensus_addr, fee_addr, 200, vote_address0,
                                   {'from': operate_addr, 'value': required_margin})
        if consensus_addr is None:
            consensus_addr = consensus_address
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.update(consensus_addr, fee_addr, commission, vote_address1, {'from': operate_addr})
        else:
            tx = candidate_hub.update(consensus_addr, fee_addr, commission, vote_address2,
                                      {'from': operate_addr})
            expect_event(tx, "updated", {
                "operateAddr": operate_addr,
                "consensusAddr": consensus_addr,
                "feeAddress": fee_addr,
                "commissionThousandths": commission,
                "voteAddr": vote_address2
            })


def test_update_success(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    vote_address0 = random_vote_address()
    round_value = 200
    candidate_hub.register(consensus_address, fee_address, round_value, vote_address0,
                           {'from': accounts[0], 'value': required_margin})
    turn_round()
    consensus_ = accounts[1]
    fee_address_ = accounts[2]
    vote_address1 = '0x938821669157ba8ed89e2cdd3956cadb9242c2ed8467bc322f636bb3bb5aeff4020e98dd949e47c081df84688c6cb881'
    candidate_hub.update(consensus_, fee_address_, 300, vote_address1,
                         {'from': accounts[0]})
    state = 17
    assert candidate_hub.candidateSet(0) == (
        accounts[0], consensus_, fee_address_, 300, required_margin, state, get_current_round(), round_value,
        vote_address1)


def test_update_vote_addr_invalid_length_failed(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    vote_address0 = random_vote_address()
    round_value = 200
    candidate_hub.register(consensus_address, fee_address, round_value, vote_address0,
                           {'from': accounts[0], 'value': required_margin})
    consensus_ = accounts[1]
    fee_address_ = accounts[2]
    error_vote_address1 = '0x938821669157ba8ed89e2cdd3956cadb9242c2ed8467bc322f636bb3bb5aeff4020e98dd949e47c081df84688c6cb8'
    with brownie.reverts("vote address length should be 48"):
        candidate_hub.update(consensus_, fee_address_, 300, error_vote_address1,
                             {'from': accounts[0]})


def test_self_vote_addr_duplicate_failed(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    vote_address0 = random_vote_address()
    round_value = 200
    candidate_hub.register(consensus_address, fee_address, round_value, vote_address0,
                           {'from': accounts[0], 'value': required_margin})
    consensus_ = accounts[1]
    fee_address_ = accounts[2]
    candidate_hub.update(consensus_, fee_address_, 300, vote_address0,
                         {'from': accounts[0]})
    state = 1
    assert candidate_hub.candidateSet(0) == (
        accounts[0], consensus_, fee_address_, 300, required_margin, state, get_current_round(), round_value,
        vote_address0)


def test_update_vote_addr_list_contains_duplicates_failed(candidate_hub, required_margin):
    vote_address_list = []
    round_value = 200
    for i in range(5):
        vote_address = random_vote_address()
        candidate_hub.register(random_address(), random_address(), round_value, vote_address,
                               {'from': accounts[i], 'value': required_margin})
        vote_address_list.append(vote_address)
    consensus_ = accounts[6]
    fee_address_ = accounts[7]
    for i in range(1, 5):
        with brownie.reverts(f"vote address already exists"):
            candidate_hub.update(consensus_, fee_address_, 300, vote_address_list[i],
                                 {'from': accounts[0]})


def test_update_single_address_repeated_changes_success(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()
    vote_address0 = random_vote_address()
    round_value = 200
    candidate_hub.register(consensus_address, fee_address, round_value, vote_address0,
                           {'from': accounts[0], 'value': required_margin})
    new_consensus_address = random_address()
    assert candidate_hub.candidateSet(0)['consensusAddr'] == consensus_address
    candidate_hub.update(new_consensus_address, fee_address, round_value, random_vote_address(), {'from': accounts[0]})
    assert candidate_hub.candidateSet(0)['consensusAddr'] == new_consensus_address
    new_vote_address = random_vote_address()
    candidate_hub.update(new_consensus_address, fee_address, round_value, new_vote_address, {'from': accounts[0]})
    assert candidate_hub.candidateSet(0)['voteAddr'] == new_vote_address
    new_fee_address = random_address()
    candidate_hub.update(new_consensus_address, new_fee_address, round_value, new_vote_address, {'from': accounts[0]})
    assert candidate_hub.candidateSet(0)['consensusAddr'] == new_consensus_address
    assert candidate_hub.candidateSet(0)['feeAddr'] == new_fee_address
    assert candidate_hub.candidateSet(0)['voteAddr'] == new_vote_address


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

    for candidate_list, score_list, index_list, count, expect_count in tests:
        validator_list = candidate_hub.getValidatorsMock(candidate_list, score_list, count)
        index_list.sort(key=lambda e: score_list[e], reverse=True)
        for i in range(expect_count):
            flag = False
            for validator in validator_list:
                if validator == candidates[index_list[i]]:
                    flag = True
                    break
            assert flag is True
        assert len(validator_list) == expect_count


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
