import pytest
import brownie
from brownie import accounts, Wei
from brownie.test import given, strategy
from brownie.network.transaction import Status
from eth_abi import encode
from web3 import Web3
from .constant import Utils
from .common import execute_proposal, register_candidate, turn_round
from .delegate import delegate_btc_success, StakeManager, delegate_power_success, delegate_coin_success


stake_manager = StakeManager()


BLOCK_REWARD = 0
TOTAL_REWARD = 0
BTC_VALUE = 2000
LOCK_SCRIPT = '0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac'
LOCK_TIMESTAMP = 1736956800


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_up(min_init_delegate_value, core_agent, candidate_hub, validator_set):
    global BLOCK_REWARD
    global TOTAL_REWARD

    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    tx_fee = 100
    BLOCK_REWARD = (block_reward + tx_fee) * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


@pytest.fixture(scope="module")
def required_margin(channel):
    return channel.requiredMargin()


@pytest.fixture(scope="module")
def dues(channel):
    return channel.dues()


@pytest.fixture(scope="module")
def commission_limit(channel):
    return channel.commissionLimit()


@pytest.fixture()
def set_channel_partner(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )

    partner_id = channel.partnerIdMap(partner)
    return partner, fee_address, partner_id, core_commission_rate, btc_commission_rate


def test_init(channel):
    assert channel.alreadyInit() is True
    assert channel.requiredMargin() == channel.INIT_REQUIRED_MARGIN()
    assert channel.dues() == 0
    assert channel.commissionLimit() == channel.DEFAULT_COMMISSION_LIMIT()


def test_register_success(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    
    partner_id = channel.partnerIdMap(partner)
    assert partner_id > 0
    
    partner_info = channel.partners(partner_id)
    assert partner_info[0] == partner
    assert partner_info[1] == fee_address
    assert partner_info[2] == core_commission_rate
    assert partner_info[3] == btc_commission_rate
    assert partner_info[4] == 1
    assert partner_info[5] == required_margin
    assert partner_info[6] == 0


def test_register_insufficient_margin(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    insufficient_margin = required_margin // 2
    
    with brownie.reverts(f"InsufficientAmount: {required_margin}, {insufficient_margin}"):
        channel.register(
            fee_address, 1000, 1500,
            {'from': partner, 'value': insufficient_margin}
        )


@pytest.mark.parametrize("core_commission_rate", [
    pytest.param(2001, marks=pytest.mark.xfail),
    pytest.param(3000, marks=pytest.mark.xfail),
    pytest.param(10000, marks=pytest.mark.xfail)
])
def test_register_core_commission_rate_too_high(channel, required_margin, core_commission_rate):
    partner = accounts[1]
    fee_address = accounts[2]
    
    with brownie.reverts(f"OutOfBounds: coreCommissionRate, {core_commission_rate}, 0, {channel.commissionLimit()}"):
        channel.register(
            fee_address, core_commission_rate, 1500,
            {'from': partner, 'value': required_margin}
        )


@pytest.mark.parametrize("btc_commission_rate", [
    pytest.param(2001, marks=pytest.mark.xfail),
    pytest.param(3000, marks=pytest.mark.xfail),
    pytest.param(10000, marks=pytest.mark.xfail)
])
def test_register_btc_commission_rate_too_high(channel, required_margin, btc_commission_rate):
    partner = accounts[1]
    fee_address = accounts[2]
    
    with brownie.reverts(f"OutOfBounds: btcCommissionRate, {btc_commission_rate}, 0, {channel.commissionLimit()}"):
        channel.register(
            fee_address, 1000, btc_commission_rate,
            {'from': partner, 'value': required_margin}
        )


def test_register_duplicate_partner(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    
    channel.register(
        fee_address, 1000, 1500,
        {'from': partner, 'value': required_margin}
    )

    with brownie.reverts(f"DuplicateRegister: {partner.address.lower()}"):
        channel.register(
            fee_address, 1200, 1700,
            {'from': partner, 'value': required_margin}
        )


def test_unregister_success(channel, set_channel_partner, dues, required_margin):
    partner, fee_address, partner_id, _, _ = set_channel_partner
    
    initial_balance = partner.balance()
    
    channel.unregister({'from': partner})
    
    partner_info = channel.partners(partner_id)
    assert partner_info[4] == 0
    
    expected_refund = required_margin - dues
    assert partner.balance() == initial_balance + expected_refund


def test_unregister_nonexistent_partner(channel):
    non_existent_partner = accounts[99]
    with brownie.reverts(f"NoPartner: 0"):
        channel.unregister({'from': non_existent_partner})


def test_set_fee_address_success(channel, set_channel_partner):
    partner, _, partner_id, _, _ = set_channel_partner
    new_fee_address = accounts[5]
    
    channel.setFeeAddress(new_fee_address, {'from': partner})
    
    partner_info = channel.partners(partner_id)
    assert partner_info[1] == new_fee_address


def test_set_fee_address_nonexistent_partner(channel):
    non_existent_partner = accounts[99]
    new_fee_address = accounts[5]
    
    with brownie.reverts(f"NoPartner: 0"):
        channel.setFeeAddress(new_fee_address, {'from': non_existent_partner})


def test_set_core_commission_rate_success(channel, set_channel_partner):
    partner, _, partner_id, _, _ = set_channel_partner
    new_rate = 1200
    
    channel.setCoreCommissionRate(new_rate, {'from': partner})
    
    partner_info = channel.partners(partner_id)
    assert partner_info[2] == new_rate


@pytest.mark.parametrize("invalid_rate", [
    pytest.param(2001, marks=pytest.mark.xfail),
    pytest.param(3000, marks=pytest.mark.xfail),
    pytest.param(10000, marks=pytest.mark.xfail)
])
def test_set_core_commission_rate_invalid(channel, set_channel_partner, invalid_rate):
    partner, _, _, _, _ = set_channel_partner
    
    with brownie.reverts(f"OutOfBounds: coreCommissionRate, {invalid_rate}, 0, {channel.commissionLimit()}"):
        channel.setCoreCommissionRate(invalid_rate, {'from': partner})


def test_set_btc_commission_rate_success(channel, set_channel_partner):
    partner, _, partner_id, _, _ = set_channel_partner
    new_rate = 1700
    
    channel.setBtcCommissionRate(new_rate, {'from': partner})
    
    partner_info = channel.partners(partner_id)
    assert partner_info[3] == new_rate


@pytest.mark.parametrize("invalid_rate", [
    pytest.param(2001, marks=pytest.mark.xfail),
    pytest.param(3000, marks=pytest.mark.xfail),
    pytest.param(10000, marks=pytest.mark.xfail)
])
def test_set_btc_commission_rate_invalid(channel, set_channel_partner, invalid_rate):
    partner, _, _, _, _ = set_channel_partner
    
    with brownie.reverts(f"OutOfBounds: btcCommissionRate, {invalid_rate}, 0, {channel.commissionLimit()}"):
        channel.setBtcCommissionRate(invalid_rate, {'from': partner})


def test_reset_commission_success(channel, set_channel_partner, stake_hub):
    partner, _, partner_id, _, _ = set_channel_partner
    
    channel.resetCommission(partner, {'from': stake_hub})
    
    partner_info = channel.partners(partner_id)
    assert partner_info[6] == 0


def test_reset_commission_zero_commission(channel, set_channel_partner, stake_hub):
    partner, _, partner_id, _, _ = set_channel_partner
    partner_info = channel.partners(partner_id)
    assert partner_info[6] == 0
    channel.resetCommission(partner, {'from': stake_hub})

    partner_info = channel.partners(partner_id)
    assert partner_info[6] == 0


def test_reset_commission_nonexistent_partner(channel, stake_hub):
    non_existent_partner = accounts[99]
    channel.resetCommission(non_existent_partner, {'from': stake_hub})


def test_reset_commission_unauthorized_caller(channel, set_channel_partner, stake_hub):
    partner, _, _, _, _ = set_channel_partner
    unauthorized_caller = accounts[99]
    
    with brownie.reverts(f"NotPermissionalCaller: {stake_hub.address.lower()}, {unauthorized_caller.address.lower()}"):
        channel.resetCommission(partner, {'from': unauthorized_caller})


def test_governance_update_required_margin(channel, gov_hub):
    new_margin = Wei("15 ether")

    execute_proposal(
        channel.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ["requiredMargin", new_margin.to_bytes(32, "big")]),
        "Update required margin"
    )
    
    assert channel.requiredMargin() == new_margin


def test_governance_update_dues(channel, required_margin):
    new_dues = required_margin // 2

    execute_proposal(
        channel.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ["dues", new_dues.to_bytes(32)]),
        "Update dues"
    )
    
    assert channel.dues() == new_dues


def test_governance_update_commission_limit(channel, gov_hub):
    new_limit = 2500
    execute_proposal(
        channel.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ["commissionLimit", new_limit.to_bytes(32)]),
        "Update commissionLimit"
    )
    assert channel.commissionLimit() == new_limit


def test_governance_unauthorized_caller(channel, gov_hub):
    unauthorized_caller = accounts[99]
    new_margin = Wei("15 ether")

    with brownie.reverts(f"NotPermissionalCaller: {gov_hub.address.lower()}, {unauthorized_caller.address.lower()}"):
        channel.updateParam(
            "requiredMargin", new_margin.to_bytes(32),
            {'from': unauthorized_caller}
        )


def test_governance_invalid_param_length(channel, gov_hub):
    invalid_value = b"invalid"
    
    with brownie.reverts("MismatchParamLength: requiredMargin"):
        channel.updateParam("requiredMargin", invalid_value, {'from': gov_hub})


def test_governance_unsupported_param(channel, gov_hub):
    new_value = 100
    
    with brownie.reverts("UnsupportedGovParam: unsupportedParam"):
        channel.updateParam("unsupportedParam", new_value.to_bytes(32), {'from': gov_hub})


def test_governance_required_margin_invalid_range(channel, gov_hub, dues):
    MAX_UINT256 = 2 ** 256 - 1
    invalid_margin = dues

    with brownie.reverts(f"OutOfBounds: requiredMargin, {invalid_margin}, {dues+1}, {MAX_UINT256}"):
        channel.updateParam(
            "requiredMargin", invalid_margin.to_bytes(32),
            {'from': gov_hub}
        )


def test_governance_dues_invalid_range(channel, gov_hub, required_margin):
    invalid_dues = required_margin

    with brownie.reverts(f"OutOfBounds: dues, {invalid_dues}, 1, {required_margin - 1}"):
        channel.updateParam(
            "dues", invalid_dues.to_bytes(32),
            {'from': gov_hub}
        )


def test_governance_commission_limit_invalid_range(channel, gov_hub):
    invalid_limit = Utils.DENOMINATOR + 1
    invalid_limit_hex = "0x" + invalid_limit.to_bytes(32).hex()
    
    with brownie.reverts(f"OutOfBounds: commissionLimit, {invalid_limit}, 0, 10000"):
        channel.updateParam(
            "commissionLimit", invalid_limit_hex,
            {'from': gov_hub}
        )


def test_partner_id_generator_increment(channel, required_margin):
    initial_generator = channel.partnerIdGenerator()
    
    partner1 = accounts[1]
    fee_address1 = accounts[2]
    tx1 = channel.register(
        fee_address1, 1000, 1500,
        {'from': partner1, 'value': required_margin}
    )
    assert tx1.status == Status.Confirmed
    
    partner2 = accounts[3]
    fee_address2 = accounts[4]
    tx2 = channel.register(
        fee_address2, 1100, 1600,
        {'from': partner2, 'value': required_margin}
    )
    assert tx2.status == Status.Confirmed
    
    final_generator = channel.partnerIdGenerator()
    assert final_generator == initial_generator + 2


def test_partner_mapping_consistency(channel, set_channel_partner):
    partner, _, partner_id, _, _ = set_channel_partner
    
    mapped_id = channel.partnerIdMap(partner)
    assert mapped_id == partner_id
    
    partner_info = channel.partners(partner_id)
    assert partner_info[0] == partner


def test_commission_calculation_accuracy(channel, set_channel_partner):
    partner, _, partner_id, _, btc_commission_rate = set_channel_partner
    
    partner_info = channel.partners(partner_id)
    assert partner_info[2] == 1000
    assert partner_info[3] == btc_commission_rate
    
    assert partner_info[6] == 0


def test_partner_status_management(channel, set_channel_partner):
    partner, _, partner_id, _, _ = set_channel_partner
    
    partner_info = channel.partners(partner_id)
    assert partner_info[4] == 1
    
    channel.unregister({'from': partner})
    partner_info = channel.partners(partner_id)
    assert partner_info[4] == 0


def test_margin_refund_calculation(channel, required_margin, dues):
    partner = accounts[1]
    fee_address = accounts[2]
    
    channel.register(
        fee_address, 1000, 1500,
        {'from': partner, 'value': required_margin}
    )
    
    initial_balance = partner.balance()
    
    channel.unregister({'from': partner})
    
    expected_refund = required_margin - dues
    assert partner.balance() == initial_balance + expected_refund


def test_commission_limit_boundary(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    
    boundary_rate = channel.commissionLimit()
    above_boundary_rate = boundary_rate + 1
    
    with brownie.reverts(f"OutOfBounds: coreCommissionRate, {above_boundary_rate}, 0, {boundary_rate}"):
        channel.register(
            fee_address, above_boundary_rate, above_boundary_rate,
            {'from': partner, 'value': required_margin}
        )


def test_register_reuse_id_after_unregister(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    
    channel.register(
        fee_address, 1000, 1500,
        {'from': partner, 'value': required_margin}
    )
    partner_id1 = channel.partnerIdMap(partner)
    
    channel.unregister({'from': partner})
    
    channel.register(
        fee_address, 1200, 1700,
        {'from': partner, 'value': required_margin}
    )
    partner_id2 = channel.partnerIdMap(partner)
    
    assert partner_id1 == partner_id2


def test_multiple_partners_registration(channel, required_margin):
    partners = []
    for i in range(3):
        partner = accounts[i + 1]
        fee_address = accounts[i + 4]
        core_commission_rate = 1000 + i * 100
        btc_commission_rate = 1500 + i * 100
        
        channel.register(
            fee_address, core_commission_rate, btc_commission_rate,
            {'from': partner, 'value': required_margin}
        )
        
        partner_id = channel.partnerIdMap(partner)
        partners.append({
            'partner': partner,
            'partner_id': partner_id,
            'core_commission_rate': core_commission_rate,
            'btc_commission_rate': btc_commission_rate
        })
    
    for i, partner_data in enumerate(partners):
        partner = partner_data['partner']
        partner_id = partner_data['partner_id']
        core_rate = partner_data['core_commission_rate']
        btc_rate = partner_data['btc_commission_rate']
        
        partner_info = channel.partners(partner_id)
        assert partner_info[0] == partner
        assert partner_info[2] == core_rate
        assert partner_info[3] == btc_rate
        assert partner_info[4] == 1


@given(commission_rate=strategy('uint16', max_value=2000))
def test_commission_rate_range(channel, required_margin, commission_rate):
    partner = accounts[1]
    fee_address = accounts[2]
    
    if commission_rate <= 2000:
        channel.register(
            fee_address, commission_rate, commission_rate,
            {'from': partner, 'value': required_margin}
        )
    else:
        with brownie.reverts("OutOfBounds"):
            channel.register(
                fee_address, commission_rate, commission_rate,
                {'from': partner, 'value': required_margin}
            )


def test_register_zero_fee_address(channel, required_margin):
    partner = accounts[1]
    zero_fee_address = "0x0000000000000000000000000000000000000000"
    
    channel.register(
        zero_fee_address, 1000, 1500,
        {'from': partner, 'value': required_margin}
    )
    
    partner_id = channel.partnerIdMap(partner)
    partner_info = channel.partners(partner_id)
    assert partner_info[1] == zero_fee_address


def test_register_zero_commission_rates(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    
    channel.register(
        fee_address, 0, 0,
        {'from': partner, 'value': required_margin}
    )
    
    partner_id = channel.partnerIdMap(partner)
    partner_info = channel.partners(partner_id)
    assert partner_info[2] == 0
    assert partner_info[3] == 0


def test_unregister_insufficient_margin_for_dues(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    
    channel.register(
        fee_address, 1000, 1500,
        {'from': partner, 'value': required_margin}
    )
    channel.unregister({'from': partner})


def test_set_core_commission_rate_nonexistent_partner(channel):
    non_existent_partner = accounts[99]
    
    with brownie.reverts("NoPartner: 0"):
        channel.setCoreCommissionRate(1200, {'from': non_existent_partner})


def test_set_btc_commission_rate_nonexistent_partner(channel):
    non_existent_partner = accounts[99]
    
    with brownie.reverts("NoPartner: 0"):
        channel.setBtcCommissionRate(1700, {'from': non_existent_partner})


def test_delegate_coin_success(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    partner_info = channel.partners(partner_id)
    assert partner_info[4] == 1
    
    delegator_amount = channel.getDelegatorAmount(partner_id, delegator)
    assert delegator_amount == delegate_amount
    
    channel_ids = channel.getIds(delegator)
    assert partner_id in channel_ids
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == delegate_amount


def test_delegate_coin_invalid_channel_id(channel, required_margin):
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    delegate_amount = Wei("10 ether")
    invalid_channel_id = 999
    
    with brownie.reverts(f"NoPartner: {invalid_channel_id}"):
        channel.delegateCoin(
            candidate, invalid_channel_id,
            {'from': delegator, 'value': delegate_amount}
        )


def test_undelegate_coin_success(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    undelegate_amount = Wei("3 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    initial_balance = delegator.balance()
    channel.undelegateCoin(
        candidate, undelegate_amount, partner_id,
        {'from': delegator}
    )
    
    remaining_amount = channel.getDelegatorAmount(partner_id, delegator)
    assert remaining_amount == delegate_amount - undelegate_amount
    
    assert delegator.balance() > initial_balance


def test_undelegate_coin_insufficient_amount(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    undelegate_amount = Wei("15 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    with brownie.reverts(f"InsufficientAmount: {undelegate_amount}, {delegate_amount}"):
        channel.undelegateCoin(
            candidate, undelegate_amount, partner_id,
            {'from': delegator}
        )


def test_undelegate_coin_complete_removal(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    channel_ids = channel.getIds(delegator)
    assert partner_id in channel_ids
    
    channel.undelegateCoin(
        candidate, delegate_amount, partner_id,
        {'from': delegator}
    )
    
    channel_ids = channel.getIds(delegator)
    assert partner_id not in channel_ids
    
    delegator_amount = channel.getDelegatorAmount(partner_id, delegator)
    assert delegator_amount == 0
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == 0


def test_undelegate_coin_invalid_channel_id(channel, required_margin):
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    undelegate_amount = Wei("3 ether")
    invalid_channel_id = 999

    initial_balance = delegator.balance()
    channel.undelegateCoin(
        candidate, undelegate_amount, invalid_channel_id,
        {'from': delegator}
    )
    assert delegator.balance() == initial_balance


def test_pay_commission_by_id_success(channel, required_margin, btc_stake):
    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500
    reward_amount = Wei("100 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    expected_commission = reward_amount * btc_commission_rate // 10000
    expected_remaining = reward_amount - expected_commission
    
    remaining_reward = channel.payCommissionById.call(
        partner_id, reward_amount,
        {'from': btc_stake.address}
    )
    channel.payCommissionById(
        partner_id, reward_amount,
        {'from': btc_stake.address}
    )
    
    new_commission = channel.partners(partner_id)[6]
    assert new_commission == expected_commission
    
    assert remaining_reward == expected_remaining


def test_pay_commission_by_id_zero_partner_id(channel, btc_stake):
    reward_amount = Wei("100 ether")
    
    remaining_reward = channel.payCommissionById.call(
        0, reward_amount,
        {'from': btc_stake.address}
    )
    channel.payCommissionById(
        0, reward_amount,
        {'from': btc_stake.address}
    )
    
    assert remaining_reward == reward_amount


def test_pay_commission_by_id_unauthorized_caller(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500
    reward_amount = Wei("100 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    with brownie.reverts(f"NotPermissionalCaller: {channel.BTC_STAKE_ADDR().lower()}, {accounts[5].address.lower()}"):
        channel.payCommissionById(
            partner_id, reward_amount,
            {'from': accounts[5]}
        )


def test_pay_commissions_success(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("50 ether")
    reward_amount = Wei("20 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    expected_commission = (delegate_amount * core_commission_rate // 10000) * reward_amount // delegate_amount
    expected_remaining = reward_amount - expected_commission
    
    remaining_reward = channel.payCommissions.call(
        delegator, delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    
    partner_info = channel.partners(partner_id)
    assert partner_info[6] == expected_commission
    
    assert remaining_reward == expected_remaining


def test_pay_commissions_zero_reward(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("50 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    remaining_reward = channel.payCommissions.call(
        delegator, delegate_amount, 0,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, delegate_amount, 0,
        {'from': core_agent.address}
    )
    
    assert remaining_reward == 0


def test_pay_commissions_unauthorized_caller(channel, required_margin):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("50 ether")
    reward_amount = Wei("20 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    with brownie.reverts(f"NotPermissionalCaller: {channel.CORE_AGENT_ADDR().lower()}, {accounts[5].address.lower()}"):
        channel.payCommissions(
            delegator, delegate_amount, reward_amount,
            {'from': accounts[5]}
        )


def test_pay_commissions_no_delegations(channel, core_agent):
    delegator = accounts[3]
    delegate_amount = Wei("50 ether")
    reward_amount = Wei("20 ether")
    
    remaining_reward = channel.payCommissions.call(
        delegator, delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    
    assert remaining_reward == reward_amount


def test_delegate_coin_integration_with_core_agent(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[1] == delegate_amount
    assert delegator_map[2] == delegate_amount
    
    channel_delegation = channel.getDelegatorAmount(partner_id, delegator)
    assert channel_delegation == delegate_amount
    
    channel_ids = channel.getIds(delegator)
    assert partner_id in channel_ids


def test_undelegate_coin_integration_with_core_agent(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    delegate_amount = Wei("10 ether")
    undelegate_amount = Wei("3 ether")
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    initial_balance = delegator.balance()
    initial_channel_delegation = channel.getDelegatorAmount(partner_id, delegator)
    initial_channel_amount = core_agent.getDelegatorMap(delegator)[2]
    
    tx = channel.undelegateCoin(
        candidate, undelegate_amount, partner_id,
        {'from': delegator}
    )
    
    assert tx.status == 1
    
    final_balance = delegator.balance()
    assert final_balance > initial_balance
    
    final_channel_delegation = channel.getDelegatorAmount(partner_id, delegator)
    assert final_channel_delegation == initial_channel_delegation - undelegate_amount
    
    channel_ids = channel.getIds(delegator)
    assert partner_id in channel_ids
    
    final_channel_amount = core_agent.getDelegatorMap(delegator)[2]
    assert final_channel_amount == initial_channel_amount - undelegate_amount


def test_delegate_coin_multiple_delegations(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    first_amount = Wei("5 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': first_amount}
    )
    
    second_amount = Wei("3 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': second_amount}
    )
    
    total_amount = channel.getDelegatorAmount(partner_id, delegator)
    assert total_amount == first_amount + second_amount
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == first_amount + second_amount


def test_pay_commissions_multiple_channels(channel, required_margin, core_agent):
    partner1 = accounts[1]
    partner2 = accounts[2]
    fee_address1 = accounts[3]
    fee_address2 = accounts[4]
    delegator = accounts[5]
    operator = accounts[6]
    register_candidate(operator=operator)
    candidate = operator
    
    core_commission_rate1 = 1000
    btc_commission_rate1 = 1500
    core_commission_rate2 = 800
    btc_commission_rate2 = 1200
    
    channel.register(
        fee_address1, core_commission_rate1, btc_commission_rate1,
        {'from': partner1, 'value': required_margin}
    )
    partner_id1 = channel.partnerIdMap(partner1)
    
    channel.register(
        fee_address2, core_commission_rate2, btc_commission_rate2,
        {'from': partner2, 'value': required_margin}
    )
    partner_id2 = channel.partnerIdMap(partner2)
    delegate_amount1 = Wei("30 ether")
    delegate_amount2 = Wei("20 ether")
    total_delegate_amount = delegate_amount1 + delegate_amount2
    
    channel.delegateCoin(
        candidate, partner_id1,
        {'from': delegator, 'value': delegate_amount1}
    )
    channel.delegateCoin(
        candidate, partner_id2,
        {'from': delegator, 'value': delegate_amount2}
    )
    
    reward_amount = Wei("25 ether")
    commission1 = (delegate_amount1 * core_commission_rate1 // 10000) * reward_amount // total_delegate_amount
    commission2 = (delegate_amount2 * core_commission_rate2 // 10000) * reward_amount // total_delegate_amount
    total_commission = commission1 + commission2
    expected_remaining = reward_amount - total_commission
    
    remaining_reward = channel.payCommissions.call(
        delegator, total_delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, total_delegate_amount, reward_amount,
        {'from': core_agent.address}
    )
    
    partner1_commission = channel.partners(partner_id1)[6]
    partner2_commission = channel.partners(partner_id2)[6]
    assert partner1_commission == commission1
    assert partner2_commission == commission2
    
    assert remaining_reward == expected_remaining


def test_delegate_coin_mixed_delegation_scenario(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel_amount = Wei("5 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': channel_amount}
    )
    
    direct_amount = Wei("3 ether")
    core_agent.delegateCoin(candidate, {'value': direct_amount, 'from': delegator})
    
    channel_delegation = channel.getDelegatorAmount(partner_id, delegator)
    assert channel_delegation == channel_amount
    
    channel_ids = channel.getIds(delegator)
    assert partner_id in channel_ids
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = delegator_map[1]
    channel_amount_tracked = delegator_map[2]
    
    assert channel_amount_tracked == channel_amount
    assert total_amount == channel_amount + direct_amount


def test_undelegate_coin_mixed_delegation_scenario(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel_amount = Wei("10 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': channel_amount}
    )
    
    direct_amount = Wei("5 ether")
    core_agent.delegateCoin(candidate, {'from': delegator, 'value': direct_amount})
    
    initial_channel_amount = core_agent.getDelegatorMap(delegator)[2]
    assert initial_channel_amount == channel_amount
    
    undelegate_channel_amount = Wei("3 ether")
    initial_balance = delegator.balance()
    
    channel.undelegateCoin(
        candidate, undelegate_channel_amount, partner_id,
        {'from': delegator}
    )
    
    remaining_channel_amount = channel.getDelegatorAmount(partner_id, delegator)
    assert remaining_channel_amount == channel_amount - undelegate_channel_amount
    
    assert delegator.balance() > initial_balance
    
    final_channel_amount = core_agent.getDelegatorMap(delegator)[2]
    assert final_channel_amount == initial_channel_amount - undelegate_channel_amount
    

def test_pay_commissions_mixed_delegation_scenario(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel_amount = Wei("30 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': channel_amount}
    )
    
    direct_amount = Wei("20 ether")
    core_agent.delegateCoin(candidate, {'from': delegator, 'value': direct_amount})
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == channel_amount
    assert delegator_map[1] == channel_amount + direct_amount
    
    total_delegation = channel_amount + direct_amount
    reward_amount = Wei("25 ether")
    
    expected_commission = (channel_amount * core_commission_rate // 10000) * reward_amount // total_delegation
    expected_remaining = reward_amount - expected_commission
    
    remaining_reward = channel.payCommissions.call(
        delegator, total_delegation, reward_amount,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, total_delegation, reward_amount,
        {'from': core_agent.address}
    )
    
    partner_info = channel.partners(partner_id)
    assert partner_info[6] == expected_commission
    
    assert remaining_reward == expected_remaining


def test_delegate_coin_channel_tracking_accuracy(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    delegations = [
        (Wei("5 ether"), partner_id),
        (Wei("3 ether"), 0),
        (Wei("2 ether"), partner_id),
        (Wei("4 ether"), 0),
        (Wei("1 ether"), partner_id),
    ]
    
    total_channel_amount = 0
    total_direct_amount = 0
    
    for amount, ch_id in delegations:
        if ch_id == partner_id:
            channel.delegateCoin(candidate, ch_id, {'from': delegator, 'value': amount})
            total_channel_amount += amount
        else:
            core_agent.delegateCoin(candidate, {'from': delegator, 'value': amount})
            total_direct_amount += amount
    
    channel_delegation = channel.getDelegatorAmount(partner_id, delegator)
    assert channel_delegation == total_channel_amount
    
    channel_ids = channel.getIds(delegator)
    assert len(channel_ids) == 1
    assert partner_id in channel_ids
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = delegator_map[1]
    channel_amount_tracked = delegator_map[2]
    
    assert total_amount == total_channel_amount + total_direct_amount
    assert channel_amount_tracked == total_channel_amount


def test_pay_commissions_mixed_delegation_edge_cases(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    channel_amount = Wei("1 ether")
    direct_amount = Wei("100 ether")
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': channel_amount}
    )
    core_agent.delegateCoin(candidate, {'from': delegator, 'value': direct_amount})
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == channel_amount
    assert delegator_map[1] == channel_amount + direct_amount
    
    total_delegation = channel_amount + direct_amount
    reward_amount = Wei("50 ether")
    
    expected_commission = (channel_amount * core_commission_rate // 10000) * reward_amount // total_delegation
    expected_remaining = reward_amount - expected_commission
    
    remaining_reward = channel.payCommissions.call(
        delegator, total_delegation, reward_amount,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator, total_delegation, reward_amount,
        {'from': core_agent.address}
    )
    
    partner_info = channel.partners(partner_id)
    assert partner_info[6] == expected_commission
    assert remaining_reward == expected_remaining
    
    partner2 = accounts[5]
    fee_address2 = accounts[6]
    
    channel.register(
        fee_address2, core_commission_rate, btc_commission_rate,
        {'from': partner2, 'value': required_margin}
    )
    partner_id2 = channel.partnerIdMap(partner2)
    
    delegator2 = accounts[7]
    equal_channel_amount = Wei("25 ether")
    equal_direct_amount = Wei("25 ether")
    
    channel.delegateCoin(candidate, partner_id2, {'from': delegator2, 'value': equal_channel_amount})
    core_agent.delegateCoin(candidate, {'from': delegator2, 'value': equal_direct_amount})
    
    delegator_map2 = core_agent.getDelegatorMap(delegator2)
    assert delegator_map2[2] == equal_channel_amount
    assert delegator_map2[1] == equal_channel_amount + equal_direct_amount
    
    total_equal_delegation = equal_channel_amount + equal_direct_amount
    reward_amount2 = Wei("20 ether")
    
    expected_commission2 = (equal_channel_amount * core_commission_rate // 10000) * reward_amount2 // total_equal_delegation
    expected_remaining2 = reward_amount2 - expected_commission2
    
    remaining_reward2 = channel.payCommissions.call(
        delegator2, total_equal_delegation, reward_amount2,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator2, total_equal_delegation, reward_amount2,
        {'from': core_agent.address}
    )
    
    partner_info2 = channel.partners(partner_id2)
    assert partner_info2[6] == expected_commission2
    assert remaining_reward2 == expected_remaining2
    
    delegator3 = accounts[8]
    only_channel_amount = Wei("40 ether")
    
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator3, 'value': only_channel_amount}
    )
    
    delegator_map3 = core_agent.getDelegatorMap(delegator3)
    assert delegator_map3[2] == only_channel_amount
    assert delegator_map3[1] == only_channel_amount
    
    reward_amount3 = Wei("15 ether")
    
    expected_commission3 = (only_channel_amount * core_commission_rate // 10000) * reward_amount3 // only_channel_amount
    expected_remaining3 = reward_amount3 - expected_commission3
    
    remaining_reward3 = channel.payCommissions.call(
        delegator3, only_channel_amount, reward_amount3,
        {'from': core_agent.address}
    )
    channel.payCommissions(
        delegator3, only_channel_amount, reward_amount3,
        {'from': core_agent.address}
    )
    
    partner_info3 = channel.partners(partner_id)
    assert partner_info3[6] >= expected_commission3
    assert remaining_reward3 == expected_remaining3


def test_pay_commission_by_id_through_btc_stake_claim_reward(
    channel, btc_stake, set_candidate, set_channel_partner, stake_hub
):
    operators, consensuses = set_candidate
    candidate = operators[0]
    delegator = accounts[0]

    partner, fee_address, partner_id, core_commission_rate, btc_commission_rate = set_channel_partner
    btc_tx_id = delegate_btc_success(
        candidate, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner_id)
    tx_map = btc_stake.btcTxMap(btc_tx_id)
    assert tx_map[2] == partner_id
    turn_round()
    turn_round(consensuses)

    expected_commission = TOTAL_REWARD * btc_commission_rate // 10000
    expected_remaining = TOTAL_REWARD - expected_commission

    init_balance = delegator.balance()
    stake_hub.claimReward({'from': delegator})
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission


@pytest.mark.parametrize("channel_id", [0, 252, 253, 0xffffffff])
def test_pay_commission_by_id_btc_stake_invalid_channel(channel, btc_stake, set_candidate, stake_hub, channel_id):
    operators, consensuses = set_candidate
    candidate = operators[0]
    delegator = accounts[0]

    btc_tx_id = delegate_btc_success(candidate, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=channel_id)
    tx_map = btc_stake.btcTxMap(btc_tx_id)
    assert tx_map[2] == channel_id
    turn_round()
    turn_round(consensuses)

    expected_commission = 0
    expected_remaining = TOTAL_REWARD - expected_commission

    init_balance = delegator.balance()
    stake_hub.claimReward({'from': delegator})
    assert delegator.balance() - init_balance == expected_remaining


def test_pay_commission_by_id_btc_stake_multiple_txs(
    channel, btc_stake, set_candidate, set_channel_partner, stake_hub
):
    operators, consensuses = set_candidate
    candidate1 = operators[0]
    candidate2 = operators[1]
    delegator = accounts[0]

    partner, fee_address, partner_id, core_commission_rate, btc_commission_rate = set_channel_partner
    delegate_btc_success(candidate1, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner_id)
    delegate_btc_success(candidate2, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner_id)
    turn_round()
    turn_round(consensuses)

    expected_commission = TOTAL_REWARD * btc_commission_rate // 10000 * 2
    expected_remaining = TOTAL_REWARD * 2 - expected_commission

    init_balance = delegator.balance()
    stake_hub.claimReward({'from': delegator})
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission


def test_pay_commission_by_id_btc_stake_mixed_channels(
    channel, btc_stake, set_candidate, stake_hub, required_margin
):
    operators, consensuses = set_candidate
    candidate = operators[0]
    delegator = accounts[0]

    partner1 = accounts[1]
    fee_address1 = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500

    channel.register(
        fee_address1, core_commission_rate, btc_commission_rate,
        {'from': partner1, 'value': required_margin}
    )
    partner1_id = channel.partnerIdMap(partner1)

    partner2 = accounts[3]
    fee_address2 = accounts[4]
    channel.register(
        fee_address2, core_commission_rate, btc_commission_rate,
        {'from': partner2, 'value': required_margin}
    )
    partner2_id = channel.partnerIdMap(partner2)

    delegate_btc_success(candidate, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner1_id)
    delegate_btc_success(candidate, delegator, BTC_VALUE, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner2_id)

    turn_round()
    turn_round(consensuses)

    expected_commission = TOTAL_REWARD // 2 * btc_commission_rate // 10000
    expected_remaining = TOTAL_REWARD - expected_commission * 2 - 1

    init_balance = delegator.balance()
    stake_hub.claimReward({'from': delegator})
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address1.balance()
    stake_hub.claimCommission({'from': partner1})
    assert fee_address1.balance() - partner_init_balance == expected_commission


def test_core_agent_channel_amount_tracking(channel, required_margin, core_agent):
    partner = accounts[1]
    fee_address = accounts[2]
    delegator = accounts[3]
    operator = accounts[4]
    register_candidate(operator=operator)
    candidate = operator
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == 0
    
    delegate_amount = Wei("10 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': delegate_amount}
    )
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == delegate_amount
    assert delegator_map[1] == delegate_amount
    
    direct_amount = Wei("5 ether")
    core_agent.delegateCoin(candidate, {'from': delegator, 'value': direct_amount})
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == delegate_amount
    assert delegator_map[1] == delegate_amount + direct_amount
    
    additional_channel_amount = Wei("3 ether")
    channel.delegateCoin(
        candidate, partner_id,
        {'from': delegator, 'value': additional_channel_amount}
    )
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    expected_channel_amount = delegate_amount + additional_channel_amount
    expected_total_amount = delegate_amount + direct_amount + additional_channel_amount
    assert delegator_map[2] == expected_channel_amount
    assert delegator_map[1] == expected_total_amount
    
    undelegate_amount = Wei("2 ether")

    channel.undelegateCoin(
        candidate, undelegate_amount, partner_id,
        {'from': delegator}
    )
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    final_channel_amount = expected_channel_amount - undelegate_amount
    final_total_amount = expected_total_amount - undelegate_amount
    assert delegator_map[2] == final_channel_amount
    assert delegator_map[1] == final_total_amount
    
    remaining_channel_amount = final_channel_amount
    channel.undelegateCoin(
        candidate, remaining_channel_amount, partner_id,
        {'from': delegator}
    )
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    assert delegator_map[2] == 0
    assert delegator_map[1] == direct_amount
    assert delegator_map[1] == direct_amount


def test_claim_reward_after_channel_delegation(
    channel, required_margin, core_agent, set_candidate, min_init_delegate_value, stake_hub
):
    delegator = accounts[0]
    operators, consensuses = set_candidate
    turn_round()

    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500

    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)

    channel_delegate_amount = 800
    channel.delegateCoin(
        operators[0], partner_id,
        {'value': channel_delegate_amount}
    )

    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = channel_delegate_amount
    assert delegator_map[1] == total_amount
    assert delegator_map[2] == channel_delegate_amount

    expected_commission = channel_delegate_amount * core_commission_rate // 10000 * TOTAL_REWARD // total_amount
    expected_remaining = TOTAL_REWARD - expected_commission

    turn_round()
    turn_round(consensuses)

    init_balance = delegator.balance()
    stake_hub.claimReward()
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission


def test_claim_reward_after_direct_and_channel_delegation(
    channel, required_margin, core_agent, set_candidate, min_init_delegate_value, stake_hub
):
    delegator = accounts[0]
    operators, consensuses = set_candidate
    direct_delegate_amount = 1200
    turn_round()

    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500

    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)

    channel_delegate_amount = 800
    channel.delegateCoin(
        operators[0], partner_id,
        {'value': channel_delegate_amount}
    )

    core_agent.delegateCoin(operators[0], {'value': direct_delegate_amount})

    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = direct_delegate_amount + channel_delegate_amount
    assert delegator_map[1] == total_amount
    assert delegator_map[2] == channel_delegate_amount

    expected_commission = channel_delegate_amount * core_commission_rate // 10000 * TOTAL_REWARD // total_amount
    expected_remaining = TOTAL_REWARD - expected_commission

    turn_round()
    turn_round(consensuses)

    init_balance = delegator.balance()
    stake_hub.claimReward()
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission


def test_claim_reward_before_channel_delegation(
    channel, required_margin, core_agent, set_candidate, min_init_delegate_value,
    stake_hub
):
    delegator = accounts[0]
    operators, consensuses = set_candidate
    direct_delegate_amount = min_init_delegate_value
    core_agent.delegateCoin(operators[0], {'value': direct_delegate_amount})
    turn_round()
    turn_round(consensuses)

    partner = accounts[1]
    fee_address = accounts[2]
    core_commission_rate = 1000
    btc_commission_rate = 1500
    
    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)

    channel_delegate_amount = 1000
    channel.delegateCoin(
        operators[0], partner_id,
        {'value': channel_delegate_amount}
    )
    
    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = direct_delegate_amount + channel_delegate_amount
    assert delegator_map[1] == total_amount
    assert delegator_map[2] == channel_delegate_amount
    
    expected_remaining = TOTAL_REWARD
    expected_commission = 0

    init_balance = delegator.balance()
    stake_hub.claimReward()
    assert delegator.balance() - init_balance == expected_remaining

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission


def test_claim_reward_after_multi_channel_delegation(
    channel, required_margin, core_agent, set_candidate, min_init_delegate_value, stake_hub
):
    delegator = accounts[0]
    operators, consensuses = set_candidate
    direct_delegate_amount = 1200
    turn_round()

    partner1 = accounts[1]
    fee_address1 = accounts[2]
    core_commission_rate1 = 1000
    btc_commission_rate = 1500

    partner2 = accounts[21]
    fee_address2 = accounts[22]
    core_commission_rate2 = 2000

    channel.register(
        fee_address1, core_commission_rate1, btc_commission_rate,
        {'from': partner1, 'value': required_margin}
    )
    partner_id1 = channel.partnerIdMap(partner1)
    channel.register(
        fee_address2, core_commission_rate2, btc_commission_rate,
        {'from': partner2, 'value': required_margin}
    )
    partner_id2 = channel.partnerIdMap(partner2)

    channel_delegate_amount1 = 200
    channel_delegate_amount2 = 600

    channel.delegateCoin(
        operators[0], partner_id1,
        {'value': channel_delegate_amount1}
    )
    channel.delegateCoin(
        operators[0], partner_id2,
        {'value': channel_delegate_amount2}
    )

    core_agent.delegateCoin(operators[0], {'value': direct_delegate_amount})

    delegator_map = core_agent.getDelegatorMap(delegator)
    total_amount = direct_delegate_amount + channel_delegate_amount1 + channel_delegate_amount2
    assert delegator_map[1] == total_amount
    assert delegator_map[2] == channel_delegate_amount1 + channel_delegate_amount2

    expected_commission1 = channel_delegate_amount1 * core_commission_rate1 // 10000 * TOTAL_REWARD // total_amount
    expected_commission2 = channel_delegate_amount2 * core_commission_rate2 // 10000 * TOTAL_REWARD // total_amount
    expected_remaining = TOTAL_REWARD - expected_commission1 - expected_commission2

    turn_round()
    turn_round(consensuses)

    init_balance = delegator.balance()
    stake_hub.claimReward()
    assert delegator.balance() - init_balance == expected_remaining

    partner1_init_balance = fee_address1.balance()
    stake_hub.claimCommission({'from': partner1})
    assert fee_address1.balance() - partner1_init_balance == expected_commission1

    partner2_init_balance = fee_address2.balance()
    stake_hub.claimCommission({'from': partner2})
    assert fee_address2.balance() - partner2_init_balance == expected_commission2


def test_claim_reward_after_multi_users_delegate_through_same_channel(
    channel, required_margin, core_agent, set_candidate, min_init_delegate_value, stake_hub
):
    delegator1 = accounts[0]
    delegator2 = accounts[1]
    operators, consensuses = set_candidate
    direct_delegate_amount = 1200
    turn_round()

    partner = accounts[2]
    fee_address = accounts[3]
    core_commission_rate = 1000
    btc_commission_rate = 1500

    channel.register(
        fee_address, core_commission_rate, btc_commission_rate,
        {'from': partner, 'value': required_margin}
    )
    partner_id = channel.partnerIdMap(partner)

    channel_delegate_amount = 800
    channel.delegateCoin(
        operators[0], partner_id,
        {'value': channel_delegate_amount, 'from': delegator1}
    )
    channel.delegateCoin(
        operators[1], partner_id,
        {'value': channel_delegate_amount, 'from': delegator2}
    )

    core_agent.delegateCoin(operators[0], {'value': direct_delegate_amount, 'from': delegator1})
    core_agent.delegateCoin(operators[1], {'value': direct_delegate_amount, 'from': delegator2})

    total_amount = direct_delegate_amount + channel_delegate_amount

    expected_commission = channel_delegate_amount * core_commission_rate // 10000 * TOTAL_REWARD // total_amount
    expected_remaining = TOTAL_REWARD - expected_commission

    turn_round()
    turn_round(consensuses)

    init_balance1 = delegator1.balance()
    stake_hub.claimReward({'from': delegator1})
    assert delegator1.balance() - init_balance1 == expected_remaining

    stake_hub.calculateReward(delegator2)

    partner_init_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - partner_init_balance == expected_commission * 2


def test_delegate_coin_and_btc_mixed(
    channel, core_agent, set_candidate, stake_hub, set_channel_partner, btc_stake, btc_agent
):
    stake_manager.set_lp_rates([[0, 1000], [10000, 5000], [20000, 10000]])
    btc_agent.setAssetWeight(1)
    delegate_amount = 1000000
    channel_delegate_amount = 3000000
    btc_value = 1000
    power_value = 1
    stake_manager.set_tlp_rates()
    stake_manager.set_is_stake_hub_active(True)

    delegator = accounts[0]
    operators, consensuses = set_candidate
    turn_round()

    partner, fee_address, partner_id, core_commission_rate, btc_commission_rate = set_channel_partner

    total_coin_amount = delegate_amount + channel_delegate_amount
    expected_coin_commission = channel_delegate_amount * core_commission_rate // 10000 * TOTAL_REWARD // total_coin_amount
    expected_btc_commission = btc_commission_rate * TOTAL_REWARD // 2 * 1000 // 10000 // 10000
    expected_coin_remaining = TOTAL_REWARD - expected_coin_commission - 1
    expected_btc_remaining = TOTAL_REWARD // 10 // 2 - expected_btc_commission + TOTAL_REWARD // 10 // 2

    delegate_coin_success(operators[0], delegator, delegate_amount)
    channel.delegateCoin(
        operators[0], partner_id,
        {'value': channel_delegate_amount, 'from': delegator}
    )
    delegate_btc_success(operators[2], delegator, btc_value // 2, LOCK_SCRIPT)
    delegate_btc_success(operators[2], delegator, btc_value // 2, LOCK_SCRIPT, lock_data=LOCK_TIMESTAMP, channel_id=partner_id)
    delegate_power_success(operators[1], delegator, power_value)
    turn_round(consensuses, round_count=2)

    coin_reward, hash_reward, btc_reward = stake_hub.claimReward.call({'from': delegator})
    assert coin_reward == expected_coin_remaining
    assert hash_reward == TOTAL_REWARD
    assert btc_reward == expected_btc_remaining

    stake_hub.claimReward({'from': delegator})

    init_partner_balance = fee_address.balance()
    stake_hub.claimCommission({'from': partner})
    assert fee_address.balance() - init_partner_balance == expected_coin_commission + expected_btc_commission
