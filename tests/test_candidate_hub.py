import random
import pytest
import brownie
from web3 import Web3
from eth_account import Account
from brownie import accounts, UnRegisterReentry
from brownie.test import given, strategy
from brownie.network.transaction import Status, TransactionReceipt
from .utils import random_address, expect_event
from .common import register_candidate, turn_round, get_candidate


@pytest.fixture(scope="module")
def required_margin(candidate_hub):
    return candidate_hub.requiredMargin()


@pytest.fixture(scope="module")
def set_candidate_status(candidate_hub):
    return candidate_hub.SET_CANDIDATE()


@pytest.fixture(scope="module")
def set_inactive_status(candidate_hub):
    return candidate_hub.SET_INACTIVE()


def test_register(candidate_hub, required_margin):
    consensus_address = random_address()
    commission = 10
    tx: TransactionReceipt = candidate_hub.register(
        consensus_address, accounts[0], commission,
        {'from': accounts[0], 'value': required_margin}
    )
    assert tx.status == Status.Confirmed


def test_register_multiple_times():
    for idx in range(10):
        register_candidate(operator=accounts[idx])


@pytest.mark.parametrize("times", [
    1,
    pytest.param(2, marks=pytest.mark.xfail),
    pytest.param(5, marks=pytest.mark.xfail),
    pytest.param(10, marks=pytest.mark.xfail)
])
def test_duplicate_operator(candidate_hub, required_margin, times):
    for _ in range(times):
        candidate_hub.register(
            random_address(), accounts[0], 1,
            {'from': accounts[0], 'value': required_margin}
        )


def test_duplicate_consensus_address(candidate_hub, required_margin):
    consensus_address = random_address()
    candidate_hub.register(consensus_address, accounts[0], 1, {'from': accounts[0], 'value': required_margin})
    with brownie.reverts("consensus already exists"):
        candidate_hub.register(
            consensus_address, accounts[1], 1, {'from': accounts[1], 'value': required_margin}
        )


@given(commission=strategy('uint32', max_value=1000, exclude=(0, 1000)))
def test_register_commission(candidate_hub, required_margin, commission):
    candidate_hub.register(
        random_address(), accounts[0], commission,
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
    Web3.toWei(11000, 'ether')
])
def test_register_margin(candidate_hub, margin):
    candidate_hub.register(
        random_address(), accounts[0], 1,
        {'from': accounts[0], 'value': margin}
    )


def test_is_candidate_by_operate(candidate_hub, required_margin):
    operator = accounts[0]
    candidate_hub.register(
        random_address(), accounts[0], 1,
        {'from': operator, 'value': required_margin}
    )
    assert candidate_hub.isCandidateByOperate(operator) is True


def test_is_candidate_by_consensus(candidate_hub, required_margin):
    consensus_address = random_address()
    candidate_hub.register(
        consensus_address, accounts[0], 1,
        {'from': accounts[0], 'value': required_margin}
    )
    assert candidate_hub.isCandidateByConsensus(consensus_address) is True


def test_get_candidates(candidate_hub, required_margin):
    operator = accounts[0]
    candidate_hub.register(
        random_address(), accounts[0], 1,
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
            candidate_hub.register(random_address(), fee_address, 10, {'from': operate_addr, 'value': required_margin})
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
            candidate_hub.register(random_address(), fee_address, 10, {'from': operate_addr, 'value': required_margin})
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


def test_register_candidate(candidate_hub, required_margin):
    consensus_address = random_address()
    fee_address = random_address()

    tests = [
        (accounts[1], consensus_address, fee_address, 0, required_margin, False, "commissionThousandths should be in (0, 1000)"),
        (accounts[1], consensus_address, fee_address, 1000, required_margin, False, "commissionThousandths should be in (0, 1000)"),
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
                candidate_hub.register(consensus_addr, fee_addr, commission, {'from': operate_addr, 'value': value})
        else:
            tx = candidate_hub.register(consensus_addr, fee_addr, commission, {'from': operate_addr, 'value': value})
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

    candidate_hub.register(consensus_address, fee_address, 10, {'from': accounts[3], 'value': required_margin})

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
            candidate_hub.register(consensus_addr, fee_address, 10, {'from': operate_addr, "value": required_margin})
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
        (accounts[2], True, consensus_address, fee_address, 0, False, "commissionThousandths should in range (0, 1000)", None),
        (accounts[3], True, random_address(), fee_address, 1000, False, "commissionThousandths should in range (0, 1000)", None),
        (accounts[3], None, consensus_address, fee_address, 100, False, "the consensus already exists", None),
        (accounts[3], None, random_address(), fee_address, 201 + max_commission_change, False, "commissionThousandths out of adjustment range", None),
        (accounts[3], None, random_address(), fee_address, 199 - max_commission_change, False, "commissionThousandths out of adjustment range", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 - max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change, True, "", None),
        (accounts[3], None, random_address(), fee_address, 200 + max_commission_change * 2, True, "", True),
    ]

    for operate_addr, register, consensus_addr, fee_addr, commission, ret, err, need_turn_round in tests:
        if need_turn_round:
            turn_round()
        if register:
            if consensus_addr is None:
                consensus_addr = random_address()
            candidate_hub.register(consensus_addr, fee_addr, 200, {'from': operate_addr, 'value': required_margin})
        if consensus_addr is None:
            consensus_addr = consensus_address
        if ret is False:
            with brownie.reverts(err):
                candidate_hub.update(consensus_addr, fee_addr, commission, {'from': operate_addr})
        else:
            tx = candidate_hub.update(consensus_addr, fee_addr, commission, {'from': operate_addr})
            expect_event(tx, "updated", {
                "operateAddr": operate_addr,
                "consensusAddr": consensus_addr,
                "feeAddress": fee_addr,
                "commissionThousandths": commission
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
            candidate_hub.register(random_address(), fee_address, 10, {'from': operate_addr, 'value': required_margin})
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
            candidate_hub.register(random_address(), fee_address, 10, {'from': operate_addr, 'value': required_margin})
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


def test_turn_round(candidate_hub, pledge_agent, validator_set, required_margin):
    required_coin_deposit = pledge_agent.requiredCoinDeposit()
    validator_count = candidate_hub.validatorCount()

    tests = [
        ([accounts[1]], [required_coin_deposit], [1], [17]),
        (accounts[1:3], [0, required_coin_deposit], [1, 1], [17, 17]),
        (accounts[1:validator_count+2], [0] + [required_coin_deposit] * validator_count, [1] * (validator_count+1), [1] + [17] * validator_count),
        (accounts[1:validator_count+2], [0, 0] + [required_coin_deposit] * (validator_count-1), [1] * (validator_count+1), [1] + [17] * (validator_count)),
        (accounts[1:6], [0] * 5, [1, 3, 5, 9, 17], [17, 3, 5, 9, 17])
    ]
    for agents, deposit, set_status, status in tests:
        for agent, _set_status in zip(agents, set_status):
            candidate_hub.register(agent, agent, 10, {'from': agent, 'value': required_margin})
            candidate_hub.setCandidateStatus(agent, _set_status, {'from': agent})
        for agent, _deposit in zip(agents, deposit):
            if _deposit > 0:
                __delegate_coin_success(pledge_agent, agent, agent, 0, _deposit)

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
                pledge_agent.undelegateCoin(agent, {'from': agent})


def test_unregister_reentry(candidate_hub, required_margin):
    candidate_hub_proxy = UnRegisterReentry.deploy(candidate_hub.address, {'from': accounts[0]})
    register_candidate(operator=accounts[1])
    candidate_hub_proxy.register(random_address(), candidate_hub_proxy.address, 500, {'value': required_margin})
    tx = candidate_hub_proxy.unregister()
    expect_event(tx, "proxyUnregister", {
        "success": False,
        "msg": "candidate does not exist"
    })


def __delegate_coin_success(pledge_agent, agent, delegator, old_value, new_value):
    tx = pledge_agent.delegateCoin(agent, {'from': delegator, 'value': new_value})
    expect_event(tx, "delegatedCoin", {
        "agent": agent,
        "delegator": delegator,
        "amount": new_value,
        "totalAmount": new_value + old_value
    })