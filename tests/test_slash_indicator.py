import pytest
import brownie
from .common import *
from .delegate import delegate_coin_success
from .utils import *
from eth_abi import encode


@pytest.fixture(scope="module", autouse=True)
def set_up(slash_indicator):
    hex_value = padding_left(Web3.to_hex(150), 64)
    execute_proposal(
        slash_indicator.address,
        0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['felonyThreshold', Web3.to_bytes(hexstr=hex_value)]),
        "update felonyThreshold"
    )


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture()
def set_candidate_maintenance(candidate_hub):
    candidate_hub.setValidatorCount(3)
    operators = []
    consensuses = []
    for operator in accounts[5:10]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    for operator in operators[:3]:
        delegate_coin_success(operator, accounts[0], 1e18)
        delegate_coin_success(operator, accounts[1], 1e18)
    return operators, consensuses


# slash
def test_slash(slash_indicator, validator_set):
    for slash_address, times, count in (
            (random_address(), 1, 1),
            (random_address(), slash_indicator.felonyThreshold(), 0)
    ):
        validator_set.setValidatorSetMap(slash_address)
        for _ in range(times):
            tx = slash_indicator.slash(slash_address)
            expect_event(tx, "validatorSlashed", {'validator': slash_address})
        result = slash_indicator.getSlashIndicator(slash_address)
        assert result[1] == count


def test_slash_force_enter_maintenance(slash_indicator, candidate_hub, validator_set, set_candidate_maintenance):
    candidate_hub.setMaxAlternateCount(5)
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    operator = operators[0]
    turn_round()
    slash_indicator.setMisdemeanorThreshold(2)
    slash_indicator.setFelonyThreshold(5)
    validator_set.deposit(validator, {"value": 10000, "from": accounts[99]})

    for _ in range(2):
        tx = slash_indicator.slash(validator)
    assert 'validatorEnterMaintenance' in tx.events
    validator = validator_set.getValidatorExByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] != 0
    old_enter_maintenance_height = validator['enterMaintenanceHeight']

    result = slash_indicator.getSlashIndicator(consensuses[0])
    assert result[1] == 2
    slash_indicator.slash(consensuses[0])
    tx = slash_indicator.slash(consensuses[0])
    assert 'validatorEnterMaintenance' not in tx.events
    validator = validator_set.getValidatorExByConsensus(consensuses[0])
    assert validator['enterMaintenanceHeight'] == old_enter_maintenance_height

@pytest.mark.parametrize("slash", ['felony', 'misdemeanor'])
def test_slash_force_update_voteWeight_success(slash_indicator,validator_set,set_candidate,slash):
    operators, consensuses = set_candidate
    turn_round()
    vote_weight = [10, 20, 30]
    chain_vote(consensuses, vote_weight)
    for i in range(3):
        assert validator_set.getValidatorExByConsensus(consensuses[i])['voteWeight'] == vote_weight[i]
    if slash == 'felony':
        slash_indicator.setFelonyThreshold(3)
        event_name = 'validatorFelony'
        actual_weight = 0
    else:
        event_name = 'validatorMisdemeanor'
        slash_indicator.setFelonyThreshold(10)
        slash_indicator.setMisdemeanorThreshold(3)
        actual_weight = 10
    validator = validator_set.exMap(consensuses[0])
    assert validator['voteWeight'] == vote_weight[0]
    for _ in range(3):
        tx = slash_indicator.slash(consensuses[0])
    assert event_name in tx.events
    validator = validator_set.exMap(consensuses[0])
    assert validator['voteWeight'] == actual_weight

def test_double_sign_slash(slash_indicator, candidate_hub):
    tests = [(
        accounts[0],
        "0xf9025aa0a5590a3b8d6297b716b35d943cb36c4554d09a312b7b82dd77760fec347f3a83a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d493479401bca3615d24d3c638836691517b2b9b49b054b1a0c3df286f72593c7897cd3354a07b405615b7d1067499eb98fa2cad2e5cd0cf6ea07f35ff816e77f5692164d1500f092a63003538d0ffe9b737121f7eaf4b1b32eda07f9af29628d2dea2ff343d4330b9b3a058bcaebf3dfc218d97a96afc36ab43a6b9010000000000000000401000000000000000000000400000000000000000000000000000000002000000000000000000000080000000000080008000000008000000000000000000000000000000100000002010000000000000000000000200000000000020000200000000000000000000000000000000000000000000000000000000000000000000000020000000000000000400000000000000000000000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000010184025ff7a7831d771d8462a833a6b861da83010000846765746889676f312e31352e31348664617277696e00884e571ae213ec5e5bbfd7c03675fb69d4d2874caaa016d9e388d8d09d34a7aa6a53a9802a9e933f3e3c1967f1190089969076a9bea1efbfa432b5aa8c7aa9189ea80c0200a00000000000000000000000000000000000000000000000000000000000000000880000000000000000",
        "0xf9025aa0a5590a3b8d6297b716b35d943cb36c4554d09a312b7b82dd77760fec347f3a83a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d493479401bca3615d24d3c638836691517b2b9b49b054b1a0c3df286f72593c7897cd3354a07b405615b7d1067499eb98fa2cad2e5cd0cf6ea07f35ff816e77f5692164d1500f092a63003538d0ffe9b737121f7eaf4b1b32eda07f9af29628d2dea2ff343d4330b9b3a058bcaebf3dfc218d97a96afc36ab43a6b9010000000000000000401000000000000000000000400000000000000000000000000000000002000000000000000000000080000000000080008000000008000000000000000000000000000000100000002010000000000000000000000200000000000020000200000000000000000000000000000000000000000000000000000000000000000000000020000000000000000400000000000000000000000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000010184025ff7a7831d771d8462a836bbb861da83010000846765746889676f312e31352e31348664617277696e00884e571a468503e2be73d187f1eb0289400ae93aec279739a679a72658c4a29e9cf2b2e86633f956022aaac8315dcd6a3fedd4a8aca169dd2c94b94d918a2c9343a19fac00a00000000000000000000000000000000000000000000000000000000000000000880000000000000000",
        True,
        ""
    ), ]
    candidate_hub.registerMock(
        "0x01Bca3615D24d3c638836691517b2B9b49b054B1",
        "0x01Bca3615D24d3c638836691517b2B9b49b054B1",
        "0x01Bca3615D24d3c638836691517b2B9b49b054B1",
        100,
        random_vote_address()
    )
    for operate_address, header1, header2, ret, err in tests:
        if ret:
            tx = slash_indicator.doubleSignSlash(header1, header2, {'from': operate_address, 'value': 0})
            expect_event(tx, "rewardEmpty")
        else:
            with brownie.reverts(err):
                slash_indicator.doubleSignSlash(header1, header2, {'from': operate_address, 'value': 0})


def test_parse_header(slash_indicator):
    tests = [(
        "0xf9025aa0a5590a3b8d6297b716b35d943cb36c4554d09a312b7b82dd77760fec347f3a83a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d493479401bca3615d24d3c638836691517b2b9b49b054b1a0c3df286f72593c7897cd3354a07b405615b7d1067499eb98fa2cad2e5cd0cf6ea07f35ff816e77f5692164d1500f092a63003538d0ffe9b737121f7eaf4b1b32eda07f9af29628d2dea2ff343d4330b9b3a058bcaebf3dfc218d97a96afc36ab43a6b9010000000000000000401000000000000000000000400000000000000000000000000000000002000000000000000000000080000000000080008000000008000000000000000000000000000000100000002010000000000000000000000200000000000020000200000000000000000000000000000000000000000000000000000000000000000000000020000000000000000400000000000000000000000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000010184025ff7a7831d771d8462a979d1b861da83010000846765746889676f312e31352e31348664617277696e00884e571a2eccf960ed12bea02b45d860602b3edbc81d621f60c3cac6f782d93057084ac211ee448ed6a69e355f8dd68a2611f94924a25a864dd2a4cd8aa17debbf8c1c0201a00000000000000000000000000000000000000000000000000000000000000000880000000000000000",
        "0xce4b26f51b1c6b10bc4c9694ab175e05f328be77204b050a30d3f0c830b36c8e",
        "0x01Bca3615D24d3c638836691517b2B9b49b054B1"
    ), (
        "0xf9025aa0a5590a3b8d6297b716b35d943cb36c4554d09a312b7b82dd77760fec347f3a83a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d493479401bca3615d24d3c638836691517b2b9b49b054b1a0c3df286f72593c7897cd3354a07b405615b7d1067499eb98fa2cad2e5cd0cf6ea07f35ff816e77f5692164d1500f092a63003538d0ffe9b737121f7eaf4b1b32eda07f9af29628d2dea2ff343d4330b9b3a058bcaebf3dfc218d97a96afc36ab43a6b9010000000000000000401000000000000000000000400000000000000000000000000000000002000000000000000000000080000000000080008000000008000000000000000000000000000000100000002010000000000000000000000200000000000020000200000000000000000000000000000000000000000000000000000000000000000000000020000000000000000400000000000000000000000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000010184025ff7a7831d771d8462a9812ab861da83010000846765746889676f312e31352e31348664617277696e00884e571a08da1339177b6bbe119f3007ee576b00e4c37a0041c9dc8c3a79d6a72977448b3a518d9c4d04b3cf73996d493dcdab46783aa06a2d7b28515c78917adead402020a00000000000000000000000000000000000000000000000000000000000000000880000000000000000",
        "0xb195a130cca4c6ece8a7894b215d5b3e2505c6fe5f1dca177b98215c951469e6",
        "0x0000000000000000000000000000000000000000"
    )]

    for header, _hash, validator in tests:
        data = slash_indicator.parseHeader(header)
        assert data[0] == _hash
        assert data[1] == validator


def test_clean(slash_indicator, candidate_hub):
    tests = [(
        accounts[0], [], [], [], [], 0
    ), (
        accounts[0], [accounts[0]], [38], [accounts[0]], [1], 1
    ), (
        accounts[0], [accounts[0]], [37], [], [], 0
    ), (
        accounts[0], accounts[:2], [38, 37], [accounts[0]], [1], 1
    ), (
        accounts[0], accounts[:2], [37, 38], [accounts[1]], [1], 1
    ), (
        accounts[0], accounts[:2], [37, 37], [], [], 0
    ), (
        accounts[0], accounts[:3], [38, 37, 39], [accounts[2], accounts[0]], [2, 1], 2
    )]

    for operator_address, validators, counts, cleaned_validator, cleaned_counts, cleaned_validator_length in tests:
        slash_indicator.setIndicators(validators, counts)
        tx = candidate_hub.cleanMock({'from': operator_address, 'value': 0})
        if len(validators) > 0:
            expect_event(tx, "indicatorCleaned", {})
        data = slash_indicator.getIndicators()

        _validators = data[0]
        _counts = data[1]

        for idx, _validator in enumerate(_validators):
            assert cleaned_validator[idx] == _validator
            assert cleaned_counts[idx] == _counts[idx]

        assert len(_validators) == cleaned_validator_length


def test_ecrecovery_faild(slash_indicator, candidate_hub):
    max_num = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
    num = int(max_num) * int(1e18)
    num_bytes = num.to_bytes(65, byteorder='big')
    address = slash_indicator.mockEcrecovery(random_btc_tx_id(), num_bytes).return_value
    assert address == ZERO_ADDRESS


# exitMaintenanceSlash
def test_revert_when_caller_is_not_validator_contract(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    block_count = 5

    with brownie.reverts("the msg sender must be validatorSet contract"):
        slash_indicator.exitMaintenanceSlash(validator, block_count, {'from': operators[0]})


def test_revert_when_contract_not_initialized(slash_indicator, validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    slash_indicator.setAlreadyInit(False)
    validator = consensuses[0]
    block_count = 5
    slash_indicator.exitMaintenanceSlash(validator, block_count, {'from': validator_set.address})


@pytest.mark.parametrize("block_count", [2, 150])
def test_exit_maintenance_slash_validator_success(slash_indicator, validator_set, block_count,
                                                  set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]
    tx = slash_indicator.exitMaintenanceSlash(validator, block_count, {'from': validator_set.address})
    if block_count == 2:
        expect_event(tx, "validatorMisdemeanor")
        result = slash_indicator.getSlashIndicator(validator)
        assert result[1] == block_count
    else:
        expect_event(tx, "validatorFelony")
        result = slash_indicator.getSlashIndicator(validator)
        assert result[1] == 0
    expect_event(tx, "validatorSlashed", {'validator': validator, 'blockCount': block_count})
    turn_round(consensuses)


@pytest.mark.parametrize("block_count", [20, 120])
def test_exit_maintenance_slash_existing_validator_success(slash_indicator, validator_set, block_count,
                                                           set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    turn_round()
    slash_indicator.setMisdemeanorThreshold(50)
    for i in range(30):
        slash_indicator.slash(validator)
    assert slash_indicator.getSlashIndicator(validator)[1] == 30
    tx = slash_indicator.exitMaintenanceSlash(validator, block_count, {'from': validator_set.address})
    if block_count == 20:
        expect_event(tx, "validatorMisdemeanor")
    else:
        expect_event(tx, "validatorFelony")


def test_exit_maintenance_slash_felony_threshold_exceeded_success(slash_indicator, validator_set,
                                                                  set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    slash_indicator.setMisdemeanorThreshold(5)
    slash_indicator.setFelonyThreshold(10)
    turn_round()
    for _ in range(10):
        tx = slash_indicator.slash(validator)
    expect_event(tx, "validatorFelony")
    assert slash_indicator.getSlashIndicator(validator)[1] == 0
    tx = slash_indicator.exitMaintenanceSlash(validator, 11, {'from': validator_set.address})
    assert len(tx.events) == 1
    expect_event(tx, "validatorSlashed", {'validator': validator, 'blockCount': 11})
    assert slash_indicator.getSlashIndicator(validator)[1] == 0
    tx = slash_indicator.exitMaintenanceSlash(validator, 5, {'from': validator_set.address})
    assert len(tx.events) == 1
    expect_event(tx, "validatorSlashed", {'validator': validator, 'blockCount': 5})


def test_exit_maintenance_slash_misdemeanor_threshold_crossed_success(slash_indicator, candidate_hub, validator_set,
                                                                      set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    slash_indicator.setMisdemeanorThreshold(40)
    slash_indicator.setFelonyThreshold(150)
    turn_round()
    validator_set.deposit(validator, {"value": 10000, "from": accounts[99]})
    for _ in range(20):
        slash_indicator.slash(validator)
    tx = slash_indicator.exitMaintenanceSlash(validator, 61, {'from': validator_set.address})
    expect_event(tx, "validatorMisdemeanor", {'validator': operators[0], 'amount': 40000})
    turn_round(consensuses)


def test_exit_maintenance_slash_no_threshold_crossed_success(slash_indicator, validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    slash_indicator.setMisdemeanorThreshold(10)
    slash_indicator.setFelonyThreshold(15)
    turn_round()
    tx = slash_indicator.exitMaintenanceSlash(validator, 2, {'from': validator_set.address})
    assert 'validatorMisdemeanor' not in tx.events
    for _ in range(2):
        slash_indicator.slash(validator)
    tx = slash_indicator.exitMaintenanceSlash(validator, 2, {'from': validator_set.address})
    assert 'validatorMisdemeanor' not in tx.events
    assert slash_indicator.getSlashIndicator(validator)[1] == 6


def test_exit_maintenance_slash_zero_block_count_success(slash_indicator, validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    validator = consensuses[0]
    turn_round()

    tx = slash_indicator.exitMaintenanceSlash(validator, 0, {'from': validator_set.address})

    expect_event(tx, "validatorSlashed", {'validator': validator, 'blockCount': 0})

    result = slash_indicator.getSlashIndicator(validator)
    assert result[1] == 0


# slashWithBlockCount
def test_slash_with_block_count_new_validator_success(slash_indicator, validator_set, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]
    block_count = 5

    slash_indicator.mockSlashWithBlockCount(validator, block_count)

    result = slash_indicator.getSlashIndicator(validator)
    assert result[0] == chain.height
    assert result[1] == block_count

    assert slash_indicator.validators(0) == validator


def test_slash_with_block_count_existing_validator_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]

    slash_indicator.mockSlashWithBlockCount(validator, 5)
    result1 = slash_indicator.getSlashIndicator(validator)
    assert result1[1] == 5

    slash_indicator.mockSlashWithBlockCount(validator, 3)
    result2 = slash_indicator.getSlashIndicator(validator)
    assert result2[1] == 8

    assert result2[0] == chain.height


def test_slash_with_block_count_multiple_validators_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()

    for i, validator in enumerate(consensuses[:3]):
        tx = slash_indicator.mockSlashWithBlockCount(validator, i + 1)
        result = slash_indicator.getSlashIndicator(validator)
        assert result[1] == i + 1
        assert result[0] == chain.height

    assert slash_indicator.validators(0) == consensuses[0]
    assert slash_indicator.validators(1) == consensuses[1]
    assert slash_indicator.validators(2) == consensuses[2]


def test_slash_with_block_count_zero_block_count_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]

    slash_indicator.mockSlashWithBlockCount(validator, 0)

    result = slash_indicator.getSlashIndicator(validator)
    assert result[0] == chain.height
    assert result[1] == 0

    assert slash_indicator.validators(0) == validator


def test_slash_with_block_count_height_update_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]

    slash_indicator.mockSlashWithBlockCount(validator, 1)
    result1 = slash_indicator.getSlashIndicator(validator)
    initial_height = result1[0]

    chain.mine(5)

    slash_indicator.mockSlashWithBlockCount(validator, 2)
    result2 = slash_indicator.getSlashIndicator(validator)

    assert result2[0] > initial_height
    assert result2[0] == chain.height
    assert result2[1] == 3  # 1 + 2 = 3


def test_slash_with_block_count_indicator_structure_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]
    slash_indicator.setMisdemeanorThreshold(20)
    for _ in range(10):
        slash_indicator.slash(validator)
    slash_indicator.mockSlashWithBlockCount(validator, 10)
    indicator = slash_indicator.indicators(validator)
    assert indicator['height'] == chain.height
    assert indicator['count'] == 20
    assert indicator['exist'] == True


def test_slash_with_block_count_accumulation_success(slash_indicator, set_candidate_maintenance):
    operators, consensuses = set_candidate_maintenance
    turn_round()
    validator = consensuses[0]

    for i in range(5):
        slash_indicator.mockSlashWithBlockCount(validator, i + 1)
        result = slash_indicator.getSlashIndicator(validator)
        expected_count = sum(range(1, i + 2))
        assert result[1] == expected_count
        assert result[0] == chain.height
    final_result = slash_indicator.getSlashIndicator(validator)
    assert final_result[1] == 15
