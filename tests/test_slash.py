import brownie
import pytest
from brownie.test import strategy
from eth_account.signers.local import LocalAccount

from .delegate import delegate_coin_success
from .utils import *
from .common import register_candidate, turn_round, execute_proposal, stake_hub_claim_reward

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


def build_vote_data(src_num, src_hash, tar_num, tar_hash, sig):
    return [src_num, src_hash, tar_num, tar_hash, sig]


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


def test_old_block_involved_failed(slash_indicator, validator_set, set_candidate):
    signature = os.urandom(96).hex()
    chain.mine(86400 + chain.height)
    vote_a = build_vote_data(100, random_btc_tx_id(), 150, random_btc_tx_id(), signature)
    vote_b = build_vote_data(120, random_btc_tx_id(), 140, random_btc_tx_id(), signature)
    vote_addr = random_vote_address()
    with brownie.reverts(f"too old block involved"):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(120, random_btc_tx_id(), 150, random_btc_tx_id(), signature)
    vote_b = build_vote_data(100, random_btc_tx_id(), 140, random_btc_tx_id(), signature)
    vote_addr = random_vote_address()
    with brownie.reverts(f"too old block involved"):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})


def test_identical_votes_failed(slash_indicator, validator_set, set_candidate):
    signature = os.urandom(96).hex()
    src_num = 100
    vote_addr = random_vote_address()
    src_hash = 'fa3ee718ac7585d9fc58f4bbd4c17f745d96609e17ac5e81f444bd0b538c52fb'
    tar_hash = '6e30353bfa10cc63c000c454184b4fa9f4c6844eb65897976940d7e3af9199ab'
    vote_a = build_vote_data(src_num, src_hash, src_num, tar_hash, signature)
    vote_b = build_vote_data(src_num, src_hash, src_num, tar_hash, signature)
    with brownie.reverts('two identical votes'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(src_num, src_hash, src_num, src_hash, signature)
    vote_b = build_vote_data(src_num, tar_hash, src_num, src_hash, signature)
    with brownie.reverts('srcNum bigger than tarNum'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(src_num, src_hash, src_num, src_hash, signature)
    vote_b = build_vote_data(src_num, src_hash, src_num, tar_hash, signature)
    with brownie.reverts('srcNum bigger than tarNum'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})


@pytest.mark.parametrize("new_tar_num", [98, 99, 100])
def test_src_num_exceeds_tar_num_failed(slash_indicator, set_candidate, new_tar_num):
    signature = os.urandom(96).hex()
    tar_num = 101
    src_num = 100
    vote_addr = random_vote_address()
    src_hash_list = [random_bytes_data() for _ in range(2)]
    tar_hash_list = [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], new_tar_num, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], new_tar_num, tar_hash_list[1], signature)
    with brownie.reverts('srcNum bigger than tarNum'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(src_num, src_hash_list[0], tar_num, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], new_tar_num, tar_hash_list[1], signature)
    with brownie.reverts('srcNum bigger than tarNum'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(src_num, src_hash_list[0], new_tar_num, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], tar_num, tar_hash_list[1], signature)
    with brownie.reverts('srcNum bigger than tarNum'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})
    vote_a = build_vote_data(src_num, src_hash_list[0], tar_num, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], tar_num, tar_hash_list[1], signature)
    with brownie.reverts('verify signature failed'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})


def test_no_violation_detected_failed(slash_indicator, set_candidate):
    signature = os.urandom(96).hex()
    src_num = 100
    vote_addr = random_vote_address()
    src_hash_list = [random_bytes_data() for _ in range(2)]
    tar_hash_list = [random_bytes_data() for _ in range(2)]
    # 1 voteA.srcNum < voteB.srcNum  &&  voteB.tarNum < voteA.tarNum
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    with brownie.reverts('verify signature failed'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})

    # 2 voteB.srcNum < voteA.srcNum && voteA.tarNum < voteB.tarNum
    vote_a = build_vote_data(src_num + 1, src_hash_list[0], 120, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], 200, tar_hash_list[1], signature)
    with brownie.reverts('verify signature failed'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})

    # 3 voteA.tarNum == voteB.tarNum
    vote_a = build_vote_data(src_num + 1, src_hash_list[0], 120, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num, src_hash_list[1], 120, tar_hash_list[1], signature)
    with brownie.reverts('verify signature failed'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})

    #  no violation of vote rules
    vote_a = build_vote_data(100, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(150, src_hash_list[1], 250, tar_hash_list[1], signature)
    with brownie.reverts('no violation of vote rules'):
        slash_indicator.submitFinalityViolationEvidence((vote_a, vote_b, vote_addr), {'from': accounts[0]})


def test_zero_reward_default_value(slash_indicator, system_reward):
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))
    signature = os.urandom(96).hex()
    src_num = 100
    vote_addr_list = [random_vote_address() for _ in range(3)]
    operators = []
    consensuses = []
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_addr_list[index]))
    turn_round()
    src_hash_list = [random_bytes_data() for _ in range(2)]
    tar_hash_list = [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    tracker = get_tracker(accounts[2])
    slash_indicator.mockSubmitFinalityViolationEvidence((vote_a, vote_b, vote_addr_list[1]), {'from': accounts[2]})
    assert tracker.delta() == slash_indicator.INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION()


@pytest.mark.parametrize("report_reward", [100, 1e21, 1e18, 100])
def test_update_reward_for_report_success(slash_indicator, system_reward, report_reward):
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))
    signature = os.urandom(96).hex()
    src_num = 100
    vote_addr_list = [random_vote_address() for _ in range(3)]
    operators = []
    consensuses = []
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_addr_list[index]))
    turn_round()
    hex_value = padding_left(Web3.to_hex(int(report_reward)), 64)
    execute_proposal(
        slash_indicator.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['rewardForReportFinalityViolation', Web3.to_bytes(hexstr=hex_value)]),
        "update rewardForReportFinalityViolation"
    )
    src_hash_list, tar_hash_list = [random_bytes_data() for _ in range(2)], [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    tracker = get_tracker(accounts[2])
    slash_indicator.mockSubmitFinalityViolationEvidence((vote_a, vote_b, vote_addr_list[0]), {'from': accounts[2]})
    assert tracker.delta() == report_reward


def test_felony_submission_success(slash_indicator, validator_set, candidate_hub, system_reward):
    validator_set.updateBlockReward(30000)
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))
    signature = os.urandom(96).hex()
    src_num = 100
    delegate_amount = 10000
    vote_addr_list = [random_vote_address() for _ in range(3)]
    operators = []
    consensuses = []
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_addr_list[index]))
        delegate_coin_success(operator, accounts[0], delegate_amount)
    turn_round()
    src_hash_list, tar_hash_list = [random_bytes_data() for _ in range(2)], [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    tracker = get_tracker(accounts[2])
    tx = slash_indicator.mockSubmitFinalityViolationEvidence((vote_a, vote_b, vote_addr_list[1]), {'from': accounts[2]})
    assert tracker.delta() == slash_indicator.INIT_REWARD_FOR_REPORT_FINALITY_VIOLATION()
    expect_event(tx, "validatorFelony", {
        'validator': operators[1],
        'amount': 0
    })
    expect_event(tx, "deductedMargin", {
        "operateAddr": operators[1],
        "margin": slash_indicator.felonyDeposit(),
        "totalMargin": candidate_hub.requiredMargin() - slash_indicator.felonyDeposit()
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    total_reward = 13545
    assert tracker.delta() == total_reward * 2


def test_validator_restoration_after_felony_success(slash_indicator, validator_set, candidate_hub, system_reward):
    validator_set.updateBlockReward(30000)
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))
    signature = os.urandom(96).hex()
    src_num = 100
    delegate_amount = 10000
    vote_addr_list = [random_vote_address() for _ in range(3)]
    operators = []
    consensuses = []
    for index, operator in enumerate(accounts[5:8]):
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator, vote_address=vote_addr_list[index]))
        delegate_coin_success(operator, accounts[0], delegate_amount)
    turn_round()
    src_hash_list, tar_hash_list = [random_bytes_data() for _ in range(2)], [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    tx = slash_indicator.mockSubmitFinalityViolationEvidence((vote_a, vote_b, vote_addr_list[2]), {'from': accounts[2]})
    candidate_hub.addMargin({'from': operators[2], 'value': slash_indicator.felonyDeposit()})
    assert 'validatorFelony' in tx.events
    turn_round(consensuses, round_count=2)
    assert len(validator_set.getValidators()) == 2
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    total_reward = 13545
    assert len(validator_set.getValidators()) == 3
    stake_hub_claim_reward(accounts[0])
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == total_reward * 3


def test_penalty_non_validator_voter(slash_indicator, validator_set, system_reward, set_candidate):
    operators, consensuses = set_candidate
    validator_set.updateBlockReward(30000)
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))
    signature = os.urandom(96).hex()
    src_num = 100
    delegate_amount = 10000
    for operator in operators:
        delegate_coin_success(operator, accounts[0], delegate_amount)
    turn_round()
    src_hash_list, tar_hash_list = [random_bytes_data() for _ in range(2)], [random_bytes_data() for _ in range(2)]
    vote_a = build_vote_data(src_num, src_hash_list[0], 200, tar_hash_list[0], signature)
    vote_b = build_vote_data(src_num + 1, src_hash_list[1], 120, tar_hash_list[1], signature)
    tx = slash_indicator.mockSubmitFinalityViolationEvidence((vote_a, vote_b, random_vote_address()),
                                                             {'from': accounts[2]})
    assert 'validatorFelony' not in tx.events
    turn_round(consensuses, round_count=2)
    assert len(validator_set.getValidators()) == 3


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


@pytest.mark.parametrize("report_reward", [1, 2, 3, 1000, 1e20, 1e21])
def test_update_report_reward_success(slash_indicator, report_reward):
    value = padding_left(Web3.to_hex(int(report_reward)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    slash_indicator.updateParam('rewardForReportFinalityViolation', value)
    assert slash_indicator.rewardForReportFinalityViolation() == value


@pytest.mark.parametrize("report_reward", [0, 1e22])
def test_update_report_reward_failed(slash_indicator, report_reward):
    value = padding_left(Web3.to_hex(int(report_reward)), 64)
    update_system_contract_address(slash_indicator, gov_hub=accounts[0])
    with brownie.reverts(
            f"OutOfBounds: rewardForReportFinalityViolation, {int(report_reward)}, 1, 1000000000000000000000"):
        slash_indicator.updateParam('rewardForReportFinalityViolation', value)


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
