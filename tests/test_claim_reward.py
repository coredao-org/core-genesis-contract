import brownie
import pytest
import rlp

from .calc_reward import set_delegate, parse_delegation, Discount, set_btc_lst_delegate
from .common import *
from eth_utils import to_bytes
from .delegate import *
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
DELEGATE_VALUE = 0
BLOCK_REWARD = 0
COIN_VALUE = 10000
BTC_VALUE = 200
POWER_VALUE = 20
TX_FEE = 100
FEE = 0
MONTH = 30
TOTAL_REWARD = 0
# BTC delegation-related
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
LOCK_TIME = 1736956800
stake_manager = StakeManager()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture()
def init_system_reward_balance(system_reward):
    incentive_balance = 10000000e18
    system_reward.receiveRewards({'value': incentive_balance, 'from': accounts[97]})
    assert system_reward.balance() == incentive_balance


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_stake, stake_hub, pledge_agent,
                     gov_hub, btc_agent, system_reward, core_agent):
    global BLOCK_REWARD, FEE, DELEGATE_VALUE, TOTAL_REWARD, MIN_INIT_DELEGATE_VALUE
    global BTC_STAKE, STAKE_HUB, CANDIDATE_HUB, PLEDGE_AGENT, block_reward
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    MIN_INIT_DELEGATE_VALUE = core_agent.requiredCoinDeposit()
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 1000
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CANDIDATE_HUB = candidate_hub
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    set_block_time_stamp(150, LOCK_TIME)
    tlp_rates_keys, tlp_rates_values, lp_rates_keys, lp_rates_values = Discount().get_init_discount()
    btc_agent.setAssetWeight(1)
    btc_stake.setInitTlpRates(tlp_rates_keys, tlp_rates_values)
    btc_agent.setInitLpRates(lp_rates_keys, lp_rates_values)
    btc_stake.setIsActive(True)
    btc_agent.setIsActive(True)
    PLEDGE_AGENT = pledge_agent
    system_reward.setOperator(stake_hub.address)


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def set_validator_count(validator_count=6, alternate_count=2):
    CandidateHubMock[0].setValidatorCount(validator_count)
    CandidateHubMock[0].setMaxAlternateCount(alternate_count)


def add_candidates(count=25):
    start_count = 10
    operators = []
    consensuses = []
    for operator in accounts[start_count:start_count + count]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def mock_current_round():
    current_round = 19998
    timestamp = current_round * Utils.ROUND_INTERVAL
    return current_round, timestamp


def mock_btc_stake_lock_time(timestamp, stake_round=None):
    if stake_round is None:
        stake_round = random.randint(1, 10)
    timestamp = timestamp + (Utils.ROUND_INTERVAL * stake_round)
    end_round = timestamp // Utils.ROUND_INTERVAL
    return timestamp, end_round


def setup_validators_and_delegates(validator_count=9, alternate_count=3, candidate_count=15):
    validator_set = ValidatorSetMock[0]
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    set_validator_count(validator_count=validator_count, alternate_count=alternate_count)
    operators, consensuses = add_candidates(candidate_count)
    return operators, consensuses


def delegate_validator(operators, valudator_index=None, delegator=None, delegate_amount=None, btc_amount=1000):
    if delegate_amount is None:
        delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    if valudator_index is None:
        valudator_index = [0, 6]
    if delegator is None:
        delegator = accounts[0:2]
    if isinstance(valudator_index, list):
        for i in range(valudator_index[0], valudator_index[1]):
            if type(delegator) == list:
                for acc in delegator:
                    delegate_coin_success(operators[i], acc, delegate_amount)
                    delegate_btc_success(operators[i], acc, btc_amount, LOCK_SCRIPT, relay=acc)
            else:
                delegate_coin_success(operators[i], delegator, delegate_amount)
                delegate_btc_success(operators[i], delegator, btc_amount, LOCK_SCRIPT, relay=delegator)
    else:
        if type(delegator) == list:
            for acc in delegator:
                delegate_coin_success(operators[valudator_index], acc, delegate_amount)
                delegate_btc_success(operators[valudator_index], acc, btc_amount, LOCK_SCRIPT, relay=acc)
        else:
            delegate_coin_success(operators[valudator_index], delegator, delegate_amount)
            delegate_btc_success(operators[valudator_index], delegator, btc_amount, LOCK_SCRIPT, relay=delegator)


def expect_validator_consensus(consensuses):
    assert len(chain_get_validator_consensus()) == len(consensuses)
    for consensus in chain_get_validator_consensus():
        assert consensus in consensuses


@pytest.mark.parametrize("hard_cap", [
    [['coreHardcap', 2000], ['hashHardcap', 9000], ['btcHardcap', 10000]],
    [['coreHardcap', 3000], ['hashHardcap', 3000], ['btcHardcap', 3000]],
    [['coreHardcap', 100000], ['hashHardcap', 50000], ['btcHardcap', 30000]],
])
def test_claim_reward_after_hardcap_update(stake_hub, hard_cap, set_candidate):
    update_system_contract_address(stake_hub, gov_hub=accounts[0])
    for h in hard_cap:
        hex_value = padding_left(Web3.to_hex(h[1]), 64)
        stake_hub.updateParam(h[0], hex_value)
    operators, consensuses = set_candidate
    turn_round()
    delegate_coin_success(operators[0], accounts[0], COIN_VALUE)
    delegate_btc_success(operators[1], accounts[1], BTC_VALUE, LOCK_SCRIPT, relay=accounts[1])
    delegate_power_success(operators[2], accounts[2], POWER_VALUE)
    turn_round(consensuses, round_count=2, tx_fee=TX_FEE)
    _, unclaimed_rewards, account_rewards, _ = parse_delegation([{
        "address": operators[0],
        "coin": [set_delegate(accounts[0], COIN_VALUE)],
    }, {
        "address": operators[1],
        "btc": [set_delegate(accounts[1], BTC_VALUE, stake_duration=Utils.MONTH)],
    }, {
        "address": operators[2],
        "power": [set_delegate(accounts[2], POWER_VALUE)]
    }
    ], BLOCK_REWARD // 2,
        state_map={'core_lp': 4},
        reward_cap={
            'coin': hard_cap[0][-1],
            'power': hard_cap[1][-1],
            'btc': hard_cap[2][-1]
        }
    )
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    tracker2 = get_tracker(accounts[2])
    claim_stake_and_relay_reward(accounts[:3])
    assert tracker0.delta() == account_rewards[accounts[0]]
    assert tracker1.delta() == account_rewards[accounts[1]]
    assert tracker2.delta() == account_rewards[accounts[2]]


def init_hybrid_score_mock():
    STAKE_HUB.initHybridScoreMock()
    set_round_tag(get_current_round())


def move_btc_data(tx_ids):
    BTC_STAKE.moveData(tx_ids)



# bep127 & bep131
def test_bep127_alternate_replace_after_major_offense(candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    set_validator_count()
    operators, consensuses = add_candidates(8)
    for i in range(6):
        for acc in accounts[0:2]:
            delegate_coin_success(operators[i], acc, delegate_amount)
    delegate_coin_success(operators[6], accounts[2], 1000)
    delegate_coin_success(operators[6], accounts[3], 1000)
    delegate_coin_success(operators[7], accounts[4], 1000)
    delegate_coin_success(operators[7], accounts[5], 1000)
    turn_round()
    enter_maintenance(operators[0])
    slash_validator(consensuses[1])
    chain_deposit(consensuses[7], deposit_count=1)
    tx = turn_round(chain_get_validator_consensus())
    tracker2 = get_tracker(accounts[2])
    tracker4 = get_tracker(accounts[4])
    stake_hub_claim_reward(accounts[2])
    stake_hub_claim_reward(accounts[4])
    reward = block_reward + 100
    validator6_reward = reward * 90 // 100
    validator7_reward = reward * 2 * 90 // 100
    assert tracker2.delta() == validator6_reward // 4
    assert tracker4.delta() == validator7_reward // 4


def test_bep127_major_offense_alternate_replace_and_repeat(slash_indicator):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    set_validator_count()
    operators, consensuses = add_candidates(8)
    for i in range(6):
        for acc in accounts[0:2]:
            delegate_coin_success(operators[i], acc, delegate_amount)
            delegate_btc_success(operators[i], acc, 1000, LOCK_SCRIPT, relay=acc)
    delegate_coin_success(operators[6], accounts[2], 1000)
    delegate_coin_success(operators[6], accounts[3], 1000)
    delegate_btc_success(operators[6], accounts[2], 1000, LOCK_SCRIPT, relay=accounts[2])
    delegate_btc_success(operators[6], accounts[3], 1000, LOCK_SCRIPT, relay=accounts[3])
    delegate_coin_success(operators[7], accounts[4], 1000)
    delegate_coin_success(operators[7], accounts[5], 1000)
    turn_round()
    assert chain_get_validator_consensus() == consensuses[:6]
    slash_validator(consensuses[0])
    expect_validator_consensus(
        [consensuses[1], consensuses[2], consensuses[3], consensuses[4], consensuses[5], consensuses[6]])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:6])
    stake_hub_claim_reward(accounts[:6])
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[4].delta() == 0


def test_bep127_major_offense_alternate_replace_until_no_alternate_then_claim_reward(validator_set):
    set_validator_count()
    tx_fee = 10000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(8)
    delegate_validator(operators)
    delegate_coin_success(operators[6], accounts[2], 1000)
    delegate_coin_success(operators[6], accounts[3], 1000)
    delegate_coin_success(operators[7], accounts[4], 1000)
    delegate_coin_success(operators[7], accounts[5], 1000)
    turn_round()
    expect_validator_consensus(consensuses[:6])
    assert chain_get_validator_consensus() == consensuses[:6]
    slash_validator(consensuses[0])
    chain_deposit(consensuses[6], deposit_count=1, tx_fee=tx_fee)
    slash_validator(consensuses[6])
    chain_deposit(consensuses[7], deposit_count=2, tx_fee=tx_fee)
    total_reward = 30000 + tx_fee
    assert validator_set.getIncoming(consensuses[1]) == total_reward // 6
    slash_validator(consensuses[7])
    assert validator_set.getIncoming(consensuses[1]) == total_reward // 6 + (total_reward * 2 + total_reward // 6) // 5
    assert validator_set.getIncoming(consensuses[6]) == 0
    assert validator_set.getIncoming(consensuses[7]) == 0
    assert len(chain_get_validator_consensus()) == 5
    block_validators = chain_get_validator_consensus()
    expect_validator_consensus([consensuses[1], consensuses[2], consensuses[3], consensuses[4], consensuses[5]])
    turn_round(block_validators)
    tracker2 = get_tracker(accounts[2])
    tracker4 = get_tracker(accounts[4])
    stake_hub_claim_reward(accounts[2])
    stake_hub_claim_reward(accounts[4])
    assert tracker2.delta() == 0
    assert tracker4.delta() == 0
    turn_round(chain_get_validator_consensus())


def test_bep127_major_offense_no_alternate_block_after_exit_maintenance(validator_set, slash_indicator):
    set_validator_count()
    validator_set.setMaintainSlashPercent(30)
    tx_fee = 10000
    operators, consensuses = add_candidates(8)
    delegate_validator(operators)
    delegate_coin_success(operators[6], accounts[2], 1000)
    delegate_coin_success(operators[6], accounts[3], 1000)
    delegate_coin_success(operators[7], accounts[4], 1000)
    delegate_coin_success(operators[7], accounts[5], 1000)
    turn_round()
    assert chain_get_validator_consensus() == consensuses[:6]
    chain_deposit(consensuses[0], deposit_count=1, tx_fee=tx_fee)
    enter_maintenance(operators[0])
    slash_validator(consensuses[5])
    slash_validator(consensuses[6])
    slash_validator(consensuses[7])
    chain.mine(300)
    exit_maintenance(operators[0])
    assert validator_set.getIncoming(consensuses[5]) == 0
    assert validator_set.getIncoming(consensuses[6]) == 0
    assert validator_set.getIncoming(consensuses[7]) == 0
    assert validator_set.getIncoming(consensuses[1]) == 40000 // 4
    assert len(chain_get_validator_consensus()) == 4
    expect_validator_consensus([consensuses[1], consensuses[2], consensuses[3], consensuses[4]])
    turn_round(chain_get_validator_consensus(), round_count=3)


@pytest.mark.parametrize("slash_type", ["minor", "felony"])
def test_bep127_minor_offense_enter_maintenance_alternate_replace(slash_type, validator_set):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    set_validator_count()
    btc_amount = 1000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(8)
    delegate_validator(operators, btc_amount=1000)
    delegate_validator(operators, [6, 7], accounts[2:4], delegate_amount - 1, btc_amount - 1)
    delegate_validator(operators, [7, 8], accounts[4:6], delegate_amount - 1, btc_amount)
    turn_round()
    assert chain_get_validator_consensus() == consensuses[:6]
    tx = slash_validator(consensuses[2], slash_type=slash_type)
    if slash_type == 'minor':
        assert 'validatorEnterMaintenance' in tx.events
    else:
        with brownie.reverts("no match validator"):
            validator_set.getValidatorByConsensus(consensuses[2])
    assert consensuses[7] in chain_get_validator_consensus()
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:6])
    stake_hub_claim_reward(accounts[:6])
    assert trackers[4].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[5].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[2].delta() == 0
    assert trackers[3].delta() == 0
    assert trackers[0].delta() > 0
    assert trackers[1].delta() > 0


def test_bep127_minor_then_felony_alternate_replace(validator_set, candidate_hub):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    btc_amount = 1000
    set_validator_count()
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(8)
    delegate_validator(operators)
    delegate_validator(operators, [6, 7], accounts[2:4], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [7, 8], accounts[4:6], delegate_amount - 2, btc_amount)
    delegate_coin_success(operators[5], accounts[6], 10000)
    turn_round()
    expect_validator_consensus(consensuses[:6])
    tx = slash_validator(consensuses[5], slash_type="minor")
    assert 'validatorEnterMaintenance' in tx.events
    chain.mine(300)
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:7])
    stake_hub_claim_reward(accounts[:7])
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[3].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[6].delta() == 0
    turn_round(chain_get_validator_consensus())


@pytest.mark.parametrize("slash_type", ["minor", "felony"])
def test_bep127_minor_no_alternate_replace(validator_set, slash_type):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    btc_amount = 1000
    set_validator_count()
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(8)
    delegate_validator(operators)
    delegate_validator(operators, [6, 7], accounts[2:4], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [7, 8], accounts[4:6], delegate_amount - 1, btc_amount)
    delegate_coin_success(operators[2], accounts[3], 10000)
    turn_round()
    slash_validator(consensuses[2], slash_type=slash_type)
    turn_round([consensuses[0], consensuses[1], consensuses[3], consensuses[4], consensuses[5]])
    trackers = get_trackers(accounts[:6])
    stake_hub_claim_reward(accounts[:6])
    assert trackers[0].delta() > 0
    assert trackers[3].delta() == 0


def test_bep127_alternate_replace_with_maintenance_and_felony(validator_set):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    btc_amount = 1000
    set_validator_count(validator_count=9, alternate_count=3)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(15)
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    delegate_validator(operators, [9, 11], accounts[2], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [11, 12], accounts[4], delegate_amount - 2, btc_amount)
    delegate_validator(operators, [12, 15], accounts[5], delegate_amount - 3, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])

    enter_maintenance(operators[2])
    enter_maintenance(operators[3])
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 9, 10]])
    turn_round(chain_get_validator_consensus())
    slash_validator(consensuses[2], slash_type="felony")
    slash_validator(consensuses[3], slash_type="felony")
    chain_deposit(consensuses[9], deposit_count=3)
    chain_deposit(consensuses[10], deposit_count=3)
    enter_maintenance(operators[9])
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[10])
    slash_validator(consensuses[10], slash_type="felony")
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 11]])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:6])
    stake_hub_claim_reward(accounts[:6])
    assert trackers[1].delta() > 0
    assert trackers[2].delta() > 0
    assert trackers[4].delta() > 0
    assert trackers[5].delta() == 0
    turn_round(chain_get_validator_consensus())
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 9, 11]])
    validators = validator_set.getValidators()
    assert len(validators) == 12
    for c in [consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14]]:
        assert c in validators
    turn_round(chain_get_validator_consensus())


def test_bep127_all_alternates_in_maintenance(validator_set):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    btc_amount = 1000
    set_validator_count(validator_count=9, alternate_count=3)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(15)
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    delegate_validator(operators, [9, 12], accounts[2], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [12, 15], accounts[4], delegate_amount - 2, btc_amount)
    delegate_coin_success(operators[2], accounts[3], 10000)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    enter_maintenance(operators[2])
    enter_maintenance(operators[3])
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 9, 10]])
    turn_round(chain_get_validator_consensus())
    enter_maintenance(operators[9])
    enter_maintenance(operators[10])
    enter_maintenance(operators[11])

    slash_validator(consensuses[2], slash_type="felony")
    slash_validator(consensuses[3], slash_type="felony")
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8]])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:6])
    stake_hub_claim_reward(accounts[:6])
    assert trackers[1].delta() > 0
    assert trackers[3].delta() == 0
    validators = validator_set.getValidators()
    assert len(validators) == 12
    turn_round(chain_get_validator_consensus())


def test_bep127_alternate_high_score_in_maintenance(validator_set):
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    validator_set.setMaintainSlashPercent(30)
    btc_amount = 1000
    set_validator_count(validator_count=9, alternate_count=3)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(15)
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    delegate_validator(operators, 2, accounts[6], delegate_amount - 1, btc_amount)
    delegate_validator(operators, 3, accounts[6], delegate_amount - 1, btc_amount)
    delegate_validator(operators, 9, accounts[2], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [10, 12], accounts[3], delegate_amount - 2, btc_amount)
    delegate_validator(operators, 12, accounts[4], delegate_amount - 3, btc_amount)
    delegate_validator(operators, [13, 15], accounts[5], delegate_amount - 4, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    enter_maintenance(operators[2])
    enter_maintenance(operators[3])
    slash_validator(consensuses[2], slash_type="felony")
    slash_validator(consensuses[3], slash_type="felony")
    enter_maintenance(operators[9])
    expect_validator_consensus([consensuses[i] for i in [0, 1, 4, 5, 6, 7, 8, 10, 11]])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:7])
    stake_hub_claim_reward(accounts[:7])
    assert trackers[6].delta() == 0
    turn_round(chain_get_validator_consensus())


def test_bep127_validator_maintenance_and_return(validator_set):
    btc_amount = 1000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    delegate_validator(operators, 2, accounts[6], delegate_amount, btc_amount)
    delegate_validator(operators, 9, accounts[2], delegate_amount - 1, btc_amount)
    delegate_validator(operators, [10, 12], accounts[3], delegate_amount - 2, btc_amount)
    delegate_validator(operators, 12, accounts[4], delegate_amount - 3, btc_amount)
    delegate_validator(operators, [13, 15], accounts[5], delegate_amount - 4, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    enter_maintenance(operators[2])
    expect_validator_consensus([consensuses[i] for i in [0, 1, 3, 4, 5, 6, 7, 8, 9]])
    chain_deposit(consensuses[9], deposit_count=3)
    exit_maintenance(operators[2])
    expect_validator_consensus(consensuses[:9])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:7])
    stake_hub_claim_reward(accounts[:7])
    assert trackers[6].delta() > 0
    assert trackers[2].delta() == TOTAL_REWARD * 3 - 2


@pytest.mark.parametrize("slash_type", ["minor", "felony", "active"])
def test_bep127_validator_maintenance_with_minor_slash(validator_set, slash_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    delegate_validator(operators, 9, accounts[6], delegate_amount - 1, btc_amount)
    delegate_validator(operators, 10, accounts[3], delegate_amount - 2, btc_amount)
    delegate_validator(operators, 11, accounts[7], delegate_amount - 2, btc_amount)
    delegate_validator(operators, 12, accounts[4], delegate_amount - 3, btc_amount)
    delegate_validator(operators, [13, 15], accounts[5], delegate_amount - 4, btc_amount)
    delegate_validator(operators, 2, accounts[2], delegate_amount, btc_amount)
    tx = turn_round()
    expect_validator_consensus(consensuses[:9])
    chain_deposit(consensuses[2], deposit_count=3)
    enter_maintenance(operators[2])
    validator_consensus = consensuses[:9]
    chain_deposit(consensuses[9], deposit_count=1)
    chain_deposit(consensuses[2], deposit_count=1)
    event_name = None
    total_reward = block_reward + 100
    validator_actual_reward = total_reward * 4 // 11 + total_reward
    if slash_type == "minor":
        chain.mine(80)
        event_name = 'validatorMisdemeanor'
        account2_reward = TOTAL_REWARD // 2 - 1
        account3_reward = (validator_actual_reward - total_reward) * 90 // 100 // 2 - 1
        account6_reward = validator_actual_reward * 90 // 100 // 2 - 1
    elif slash_type == "felony":
        chain.mine(200)
        event_name = 'validatorFelony'
        validator_consensus = [consensuses[i] for i in [0, 1, 3, 4, 5, 6, 7, 8, 9]]
        account2_reward = 0
        account3_reward = (validator_actual_reward - total_reward) * 90 // 100 // 2 - 1
        account6_reward = (validator_actual_reward * 90 // 100 // 2 - 1) + TOTAL_REWARD
    else:
        tx = exit_maintenance(operators[2])
        assert "validatorMisdemeanor" not in tx.events
        assert "validatorFelony" not in tx.events
        account2_reward = (total_reward * 5 * 90 / 100) // 4
        account3_reward = 0
        account6_reward = TOTAL_REWARD - 2
    if slash_type != "active":
        tx = exit_maintenance(operators[2])
        assert event_name in tx.events
    expect_validator_consensus(validator_consensus)
    tx = turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:8])
    stake_hub_claim_reward(accounts[:8])
    assert trackers[2].delta() == account2_reward
    assert trackers[3].delta() == account3_reward
    assert trackers[6].delta() == account6_reward


def test_bep127_validator_multiple_minor_slash(validator_set, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    for i in range(0, 9):
        delegate_validator(operators, i, accounts[1], delegate_amount - i, btc_amount)
    delegate_validator(operators, 9, accounts[2], delegate_amount + 1, btc_amount)
    delegate_validator(operators, 10, accounts[3], delegate_amount + 2, btc_amount)
    delegate_validator(operators, 11, accounts[4], delegate_amount + 3, btc_amount)
    delegate_validator(operators, 12, accounts[5], delegate_amount + 4, btc_amount)
    delegate_validator(operators, 13, accounts[6], delegate_amount + 5, btc_amount)
    delegate_validator(operators, 14, accounts[7], delegate_amount + 5, btc_amount)

    tx = turn_round()
    expect_validator_consensus([consensuses[i] for i in [14, 13, 12, 11, 10, 9, 0, 1, 2]])
    slash_indicator.setFelonyThreshold(100)
    chain_deposit(consensuses[9], deposit_count=3)
    slash_validator(consensuses[9], slash_type="minor")
    chain_deposit(consensuses[9], deposit_count=3)
    slash_validator(consensuses[9], slash_type="minor")
    chain_deposit(consensuses[9], deposit_count=3)
    slash_validator(consensuses[9], slash_type="minor")
    expect_validator_consensus([consensuses[i] for i in [14, 13, 12, 11, 10, 0, 1, 2, 3]])
    tx = turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:8])
    stake_hub_claim_reward(accounts[:8])
    total_reward = 30100
    assert trackers[2].delta() == 0
    assert trackers[7].delta() == (total_reward * 9 // 11 + total_reward) * 90 // 100 // 2 - 1


@pytest.mark.parametrize("slash_type", ["minor", "felony", "active"])
def test_bep127_validator_exit_maintenance_with_minor_or_felony_slash(validator_set, slash_indicator, slash_type):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount - 1, btc_amount)
    for i, acc in enumerate(accounts[2:8], start=9):
        delegate_validator(operators, i, acc, delegate_amount - (i - 8), btc_amount)
    delegate_validator(operators, 2, accounts[8], delegate_amount, btc_amount)
    turn_round()
    slash_indicator.setFelonyThreshold(6)
    expect_validator_consensus(consensuses[:9])
    slash_validator(consensuses[2], slash_type="minor")
    chain_deposit(consensuses[2], deposit_count=3)
    event_name = 'test'
    actual_reward = 0
    if slash_type == "minor":
        chain.mine(80)
        event_name = 'validatorMisdemeanor'
    elif slash_type == "felony":
        chain.mine(200)
        event_name = 'validatorFelony'
    elif slash_type == "active":
        chain.mine(1)
        actual_reward = TOTAL_REWARD * 3 // 2
    tx = turn_round(chain_get_validator_consensus())
    if slash_type == "active":
        assert 'validatorMisdemeanor' not in tx.events
        assert 'validatorFelony' not in tx.events
    else:
        assert event_name in tx.events
    trackers = get_trackers(accounts[:9])
    stake_hub_claim_reward(accounts[:9])
    assert trackers[8].delta() == actual_reward
    turn_round(chain_get_validator_consensus())


def test_bep127_validator_exit_maintenance_without_slash():
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    for i, acc in enumerate(accounts[2:8], start=9):
        delegate_validator(operators, i, acc, delegate_amount - (i - 8), btc_amount)
    delegate_validator(operators, 2, accounts[8], delegate_amount, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])

    enter_maintenance(operators[2])
    chain_deposit(consensuses[2], deposit_count=3)
    chain.mine(2)
    tx = turn_round(chain_get_validator_consensus())
    assert 'validatorMisdemeanor' not in tx.events
    assert 'validatorFelony' not in tx.events

    trackers = get_trackers(accounts[:9])
    stake_hub_claim_reward(accounts[:9])
    assert trackers[8].delta() == TOTAL_REWARD * 3 // 2
    turn_round(chain_get_validator_consensus())


@pytest.mark.parametrize("is_exit_maintenance", [True, False])
def test_bep127_validator_exit_maintenance_and_get_slashed(is_exit_maintenance):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    for i, acc in enumerate(accounts[2:8], start=9):
        delegate_validator(operators, i, acc, delegate_amount - (i - 8), btc_amount)
    delegate_validator(operators, 2, accounts[8], delegate_amount, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    enter_maintenance(operators[2])
    chain_deposit(consensuses[2], deposit_count=3)
    chain.mine(3)
    actual_reward = TOTAL_REWARD * 3 // 2
    if is_exit_maintenance:
        exit_maintenance(operators[2])
        actual_reward += TOTAL_REWARD // 2
        chain.mine(500)
    tx = turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:9])
    stake_hub_claim_reward(accounts[:9])
    assert trackers[8].delta() == actual_reward
    turn_round(chain_get_validator_consensus())


@pytest.mark.parametrize("is_maintenance", [True, False])
@pytest.mark.parametrize("slash_type", ["minor", "felony"])
def test_maintenance_and_blocking_then_stop_slashed_no_reward(slash_type, is_maintenance, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates()
    delegate_validator(operators, [0, 9], accounts[1], delegate_amount, btc_amount)
    for i, acc in enumerate(accounts[2:8], start=9):
        delegate_validator(operators, i, acc, delegate_amount - (i - 8), btc_amount)
    delegate_validator(operators, 2, accounts[8], delegate_amount, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    slash_indicator.setFelonyThreshold(6)
    if is_maintenance:
        enter_maintenance(operators[2])
    else:
        slash_validator(consensuses[2], slash_type='minor')
    chain_deposit(consensuses[2], deposit_count=3)
    chain.mine(3)
    if slash_type == "minor":
        chain.mine(80)
        event_name = 'validatorMisdemeanor'
    elif slash_type == "felony":
        chain.mine(200)
        event_name = 'validatorFelony'
    tx = turn_round(chain_get_validator_consensus())
    assert event_name in tx.events
    trackers = get_trackers(accounts[:9])
    stake_hub_claim_reward(accounts[:9])
    assert trackers[8].delta() == 0
    turn_round(consensuses)


def test_not_enough_alternate_next_round_add_and_reward(validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=9,
                                                            alternate_count=3,
                                                            candidate_count=15)
    for i in range(14):
        delegate_validator(operators, i, accounts[0], delegate_amount - i, btc_amount)
    delegate_validator(operators, 14, accounts[1], delegate_amount - 14, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:9])
    enter_maintenance(operators[0])
    enter_maintenance(operators[1])
    enter_maintenance(operators[2])
    chain.mine(400)
    chain_get_validator_consensus()
    expect_validator_consensus([consensuses[i] for i in [3, 4, 5, 6, 7, 8, 9, 10, 11]])
    tx = turn_round(chain_get_validator_consensus())
    expect_validator_consensus([consensuses[i] for i in [3, 4, 5, 6, 7, 8, 9, 10, 11]])
    validator_set_list = validator_set.getValidators()
    for i in [consensuses[i] for i in [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]]:
        assert i in validator_set_list
    assert 'validatorFelony' in tx.events
    slash_validator(consensuses[3], slash_type="felony")
    slash_validator(consensuses[4], slash_type="felony")
    slash_validator(consensuses[5], slash_type="felony")
    slash_validator(consensuses[6], slash_type="felony")
    slash_validator(consensuses[7], slash_type="felony")
    expect_validator_consensus([consensuses[i] for i in [8, 9, 10, 11, 12, 13, 14]])
    tx = turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:9])
    stake_hub_claim_reward(accounts[:9])
    assert trackers[1].delta() == TOTAL_REWARD - 2
    turn_round(chain_get_validator_consensus())


def test_validator_enter_maintenance_and_slash_workflow(validator_set, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=3,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(3):
        delegate_validator(operators, i, accounts[i], delegate_amount, btc_amount)
    delegate_validator(operators, 0, accounts[6], delegate_amount - 1, btc_amount)
    delegate_validator(operators, 3, accounts[3], delegate_amount - 1, btc_amount)
    delegate_validator(operators, 4, accounts[4], delegate_amount - 2, btc_amount)
    delegate_validator(operators, 5, accounts[5], delegate_amount - 3, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:3])
    enter_maintenance(operators[0])
    slash_validator(consensuses[0], slash_type="minor")
    for _ in range(2):
        tx = slash_indicator.slash(consensuses[0])
    assert 'validatorFelony' in tx.events
    expect_validator_consensus(consensuses[1:4])
    tx = turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[:7])
    stake_hub_claim_reward(accounts[:7])
    assert trackers[1].delta() > 0
    assert trackers[2].delta() > 0
    assert trackers[4].delta() == 0
    assert trackers[6].delta() == 0
    turn_round(chain_get_validator_consensus())


def test_upgrade_with_validator_minor_and_felony(validator_set, candidate_hub, slash_indicator):
    validator_set.setMaintainSlashPercent(0)
    set_validator_count(validator_count=31, alternate_count=0)
    validator_set = ValidatorSetMock[0]
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    btc_amount = 1000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(40)
    for i in range(36):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
    candidate_hub.unregister({'from': operators[-1]})
    candidate_hub.unregister({'from': operators[-2]})
    candidate_hub.unregister({'from': operators[-3]})
    candidate_hub.unregister({'from': operators[-4]})
    turn_round()
    set_validator_count(validator_count=31, alternate_count=7)
    validator_set.setValidatorCount(0)
    validator_set.setMaintainSlashPercent(10)
    validators = validator_set.getValidators()
    assert validator_set.validatorCount() == 0
    assert validators == consensuses[:31]
    expect_validator_consensus(consensuses[:31])
    with brownie.reverts("can not enter Temporary Maintenance"):
        enter_maintenance(operators[0])
    slash_validator(consensuses[0], slash_type="minor")
    slash_validator(consensuses[30], slash_type="felony")
    expect_validator_consensus(consensuses[:30])
    turn_round(chain_get_validator_consensus())
    assert len(validator_set.getValidators()) == 35
    actual_deposit = consensuses[:30]
    actual_deposit.append(consensuses[31])
    expect_validator_consensus(actual_deposit)
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[50:86])
    stake_hub_claim_reward(accounts[50:86])
    for i in range(len(trackers)):
        if i == 30 or i > 31:
            assert trackers[i].delta() == 0
        else:
            assert trackers[i].delta() > 0
    turn_round(chain_get_validator_consensus())


def test_upgrade_with_no_validator_minor_and_felony(validator_set, candidate_hub, slash_indicator):
    validator_set.setMaintainSlashPercent(0)
    set_validator_count(validator_count=31, alternate_count=0)
    validator_set = ValidatorSetMock[0]
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    btc_amount = 1000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(40)
    for i in range(4, 40):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
    for i in range(4):
        candidate_hub.unregister({'from': operators[i]})
    turn_round()
    set_validator_count(validator_count=31, alternate_count=3)
    validator_set.setValidatorCount(0)
    validator_set.setMaintainSlashPercent(10)
    validators = validator_set.getValidators()
    assert validator_set.validatorCount() == 0
    assert len(validators) == len(consensuses[4:35])
    for i in consensuses[4:35]:
        assert i in validators
    expect_validator_consensus(consensuses[4:35])
    turn_round(chain_get_validator_consensus())
    validators = validator_set.getValidators()
    assert validator_set.validatorCount() == 31
    assert len(validators) == len(consensuses[4:38])
    for i in consensuses[4:38]:
        assert i in validators
    expect_validator_consensus(consensuses[4:35])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[50:90])
    stake_hub_claim_reward(accounts[50:90])
    for i in range(len(trackers)):
        if i > 34 or i < 4:
            assert trackers[i].delta() == 0
        else:
            assert trackers[i].delta() > 0
    turn_round(chain_get_validator_consensus())


def test_new_validator_join_and_unregister(candidate_hub, validator_set):
    validator_count = 5
    alternate_count = 2
    candidate_count = 8
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    set_validator_count(validator_count=validator_count, alternate_count=alternate_count)
    operators, consensuses = add_candidates(candidate_count)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    for i in range(candidate_count):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[58 + i], delegate_amount - i, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:5])
    new_operator = [accounts[70], accounts[71]]
    new_consensus = []
    new_consensus.append(register_candidate(operator=new_operator[0]))
    new_consensus.append(register_candidate(operator=new_operator[1]))
    delegate_validator(new_operator, 0, accounts[72], delegate_amount + 1, btc_amount)
    delegate_validator(new_operator, 0, accounts[73], delegate_amount + 1, btc_amount)
    delegate_validator(new_operator, 1, accounts[74], delegate_amount - 3, btc_amount)
    delegate_validator(new_operator, 1, accounts[75], delegate_amount - 3, btc_amount)
    turn_round(chain_get_validator_consensus())
    new_consensus_list = consensuses[:4]
    new_consensus_list.append(new_consensus[0])
    expect_validator_consensus(new_consensus_list)
    validators = validator_set.getValidators()
    assert new_consensus[0] in validator_set.getValidators()
    assert new_consensus[1] in validator_set.getValidators()
    chain_deposit(new_consensus[0], deposit_count=1)
    expect_validator_consensus(new_consensus_list)
    turn_round(chain_get_validator_consensus())
    tracker = get_tracker(accounts[72])
    stake_hub_claim_reward(accounts[72])
    assert tracker.delta() == TOTAL_REWARD - 1
    candidate_hub.refuseDelegate({'from': new_operator[0]})
    expect_validator_consensus(new_consensus_list)
    turn_round(chain_get_validator_consensus())
    expect_validator_consensus(consensuses[:4] + new_consensus[1:])
    candidate_hub.unregister({'from': new_operator[0]})
    chain_deposit(new_consensus[1], deposit_count=1)
    expect_validator_consensus(consensuses[:4] + new_consensus[1:])
    turn_round(chain_get_validator_consensus())
    tracker1 = get_tracker(accounts[74])
    stake_hub_claim_reward(accounts[72])
    stake_hub_claim_reward(accounts[74])
    assert tracker.delta() == TOTAL_REWARD // 2 - 1
    assert tracker1.delta() == TOTAL_REWARD - 1


def test_major_offense_then_pay_fine_then_normal(candidate_hub, validator_set, slash_indicator):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    candidate_count = 7
    operators, consensuses = setup_validators_and_delegates(validator_count=3, alternate_count=5,
                                                            candidate_count=candidate_count)
    for i in range(candidate_count):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[58 + i], delegate_amount - i, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:3])
    major_offense_operator = operators[0]
    major_offense_consensus = consensuses[0]
    slash_validator(major_offense_consensus, slash_type="felony")
    expect_validator_consensus(consensuses[1:4])
    validators = validator_set.getValidators()
    assert major_offense_consensus not in validators
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[50:50 + candidate_count])
    stake_hub_claim_reward(accounts[50:50 + candidate_count])
    assert trackers[0].delta() == 0
    assert trackers[1].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[3].delta() == TOTAL_REWARD // 2 - 1
    tx = candidate_hub.addMargin({'from': operators[0], 'value': slash_indicator.felonyDeposit() * 2})
    expect_validator_consensus(consensuses[1:4])
    turn_round(chain_get_validator_consensus())
    assert consensuses[0] not in validator_set.getValidators()
    expect_validator_consensus(consensuses[1:4])

    turn_round(chain_get_validator_consensus())
    assert consensuses[0] in validator_set.getValidators()
    expect_validator_consensus(consensuses[0:3])
    stake_hub_claim_reward(accounts[50:50 + candidate_count])
    trackers[0].update_height()
    trackers[1].update_height()
    trackers[2].update_height()
    trackers[3].update_height()
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50:50 + candidate_count])
    assert trackers[0].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[1].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[3].delta() == 0
    turn_round(chain_get_validator_consensus())


def test_alternate_count_greater_than_validators_with_unregistered(candidate_hub, validator_set):
    validator_count = 3
    alternate_count = 5
    candidate_count = 10
    operators, consensuses = setup_validators_and_delegates(validator_count=validator_count,
                                                            alternate_count=alternate_count,
                                                            candidate_count=candidate_count)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000

    for i in range(candidate_count):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[61 + i], delegate_amount - i, btc_amount)
    turn_round()
    refuse_delegate(operators[3])
    expect_validator_consensus(consensuses[:3])
    turn_round(chain_get_validator_consensus())
    candidate_hub.unregister({'from': operators[3]})
    enter_maintenance(operators[4])
    enter_maintenance(operators[0])
    refuse_delegate(operators[0])
    refuse_delegate(operators[4])
    refuse_delegate(operators[5])
    refuse_delegate(operators[6])
    refuse_delegate(operators[7])
    refuse_delegate(operators[8])
    refuse_delegate(operators[9])
    expect_validator_consensus([consensuses[1], consensuses[2], consensuses[5]])
    turn_round(chain_get_validator_consensus())
    candidate_hub.unregister({'from': operators[0]})
    candidate_hub.unregister({'from': operators[4]})
    candidate_hub.unregister({'from': operators[5]})
    candidate_hub.unregister({'from': operators[6]})
    candidate_hub.unregister({'from': operators[7]})
    candidate_hub.unregister({'from': operators[8]})
    candidate_hub.unregister({'from': operators[9]})
    expect_validator_consensus([consensuses[1], consensuses[2]])
    turn_round(chain_get_validator_consensus(), round_count=2)


def test_refused_delegate_cannot_be_alternate(candidate_hub, validator_set):
    validator_count = 3
    alternate_count = 3
    candidate_count = 8
    operators, consensuses = setup_validators_and_delegates(validator_count=validator_count,
                                                            alternate_count=alternate_count,
                                                            candidate_count=candidate_count)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000

    for i in range(candidate_count):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[60 + i], delegate_amount - i, btc_amount)
    turn_round()
    refuse_delegate(operators[0])
    refuse_delegate(operators[3])
    refuse_delegate(operators[5])
    expect_validator_consensus(consensuses[:3])
    turn_round(chain_get_validator_consensus())
    expect_validator_consensus(consensuses[1:3] + consensuses[4:5])
    turn_round(chain_get_validator_consensus())


def test_replenish_and_validator_count_equals_total_validators(validator_set, candidate_hub):
    validator_count = 10
    replenish_count = 5
    total_validators = validator_count + replenish_count

    set_validator_count(validator_count=validator_count, alternate_count=replenish_count)
    operators, consensuses = add_candidates(total_validators)
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000

    for i in range(total_validators):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)

    turn_round()
    validators = validator_set.getValidators()
    assert len(validators) == total_validators
    assert validator_set.validatorCount() == validator_count
    expect_validator_consensus(consensuses[:validator_count])

    enter_maintenance(operators[0])
    chain_deposit(consensuses[0], deposit_count=1)
    expect_validator_consensus(consensuses[1:validator_count + 1])
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[50:50 + total_validators])
    stake_hub_claim_reward(accounts[50:50 + total_validators])
    for i in range(len(trackers)):
        if i > 10:
            assert trackers[i].delta() == 0
        else:
            assert trackers[i].delta() > 0
    turn_round(consensuses)


def test_edit_consensus_address_and_claim_reward(candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)

    for i in range(7):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[57 + i], delegate_amount - i, btc_amount)

    operator = operators[0]
    old_consensus = consensuses[0]
    new_consensus = accounts[90]
    turn_round()
    turn_round(chain_get_validator_consensus())
    trackers = get_trackers(accounts[50:50 + 7])
    stake_hub_claim_reward(accounts[50:50 + 7])
    assert trackers[0].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[1].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    expect_validator_consensus(consensuses[:5])
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50:50 + 7])
    trackers[0].update_height()
    tx = candidate_hub.editConsensusAddress(new_consensus, {'from': operator})
    assert 'ConsensusAddressEdited' in tx.events
    assert tx.events['ConsensusAddressEdited']['newConsensusAddr'] == new_consensus
    validators = validator_set.getValidators()
    assert new_consensus not in validators
    assert old_consensus in chain_get_validator_consensus()
    assert new_consensus not in chain_get_validator_consensus()
    expect_validator_consensus(consensuses[:5])
    chain_deposit(old_consensus, deposit_count=2)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    assert trackers[0].delta() == TOTAL_REWARD + TOTAL_REWARD // 2
    expect_validator_consensus([new_consensus, consensuses[1], consensuses[2], consensuses[3], consensuses[4]])
    chain_deposit(old_consensus, deposit_count=3)
    turn_round()
    stake_hub_claim_reward(accounts[50])
    assert trackers[0].delta() == 0
    chain_deposit(new_consensus, deposit_count=2)
    turn_round()
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[52])
    assert trackers[0].delta() == TOTAL_REWARD - 1
    expect_validator_consensus([new_consensus, consensuses[1], consensuses[2], consensuses[3], consensuses[4]])
    new_consensus1 = accounts[91]
    tx = candidate_hub.editConsensusAddress(new_consensus1, {'from': operators[2]})
    turn_round(chain_get_validator_consensus())
    trackers[0].update_height()
    trackers[2].update_height()
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[52])
    assert trackers[0].delta() == TOTAL_REWARD // 2 - 1
    assert trackers[2].delta() == TOTAL_REWARD // 2 - 1
    expect_validator_consensus([new_consensus, consensuses[1], new_consensus1, consensuses[3], consensuses[4]])
    turn_round(chain_get_validator_consensus())


def test_edit_commission_rate_and_claim_reward(candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(7):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[57 + i], delegate_amount - i, btc_amount)
    agent = accounts[65]
    turn_round()
    expect_validator_consensus(consensuses[:5])
    turn_round(chain_get_validator_consensus())
    new_commission_rate = 400
    candidate_hub.updateAgent(agent, {'from': operators[0]})
    tx = candidate_hub.editCommissionRate(new_commission_rate, {'from': agent})
    assert 'CommissionRateEdited' in tx.events
    chain_deposit(consensuses[0], deposit_count=1)
    expect_validator_consensus(consensuses[:5])
    stake_hub_claim_reward(accounts[50])
    turn_round(chain_get_validator_consensus())
    tracker = get_tracker(accounts[50])
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[51])
    assert tracker.delta() == TOTAL_REWARD - 1
    info = candidate_hub.getCandidate(operators[0])
    assert info['commissionThousandths'] == new_commission_rate
    chain_deposit(consensuses[0], deposit_count=2)
    turn_round(chain_get_validator_consensus())
    tracker1 = get_tracker(accounts[51])
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[51])
    actual_reward = 30100 * 90 // 100 * 60 // 100
    assert tracker.delta() == actual_reward * 3 // 2 - 1
    assert tracker1.delta() == TOTAL_REWARD // 2 - 1
    expect_validator_consensus(consensuses[:5])
    turn_round(chain_get_validator_consensus())


def test_edit_vote_address_and_claim_reward(candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(7):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[57 + i], delegate_amount - i, btc_amount)
    agent = accounts[65]
    turn_round()
    weights = [10, 20, 30, 60, 20]
    expect_validator_consensus(consensuses[:5])
    tx = turn_round(chain_get_validator_consensus(), weights=weights)
    stake_hub_claim_reward(accounts[50])
    vote_reward = 483
    expect_event(tx, "voteRewardTransfer", {
        'operateAddress': operators[0],
        'amount': vote_reward
    })
    new_vote_address = random_vote_address()
    candidate_hub.editVoteAddress(new_vote_address, {'from': operators[0]})
    expect_validator_consensus(consensuses[:5])
    tx = turn_round(chain_get_validator_consensus(), weights=weights)
    expect_event(tx, "voteRewardTransfer", {
        'operateAddress': operators[0],
        'amount': vote_reward
    })
    tracker = get_tracker(accounts[50])
    stake_hub_claim_reward(accounts[50])
    assert tracker.delta() == TOTAL_REWARD // 2 - 1
    turn_round(chain_get_validator_consensus())

def test_edit_fee_address_and_claim_reward(candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(7):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[57 + i], delegate_amount - i, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:5])
    tx = turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    new_fee_address = accounts[90]
    candidate_hub.editFeeAddress(new_fee_address, {'from': operators[0]})
    tx = turn_round(chain_get_validator_consensus())
    expect_event(tx, "voteRewardTransfer", {
        'operateAddress': operators[0],
        'validator': operators[0],
    })
    tracker = get_tracker(accounts[90])
    assert tracker.delta() == 0
    tx = turn_round(chain_get_validator_consensus(), weights=[10, 20, 30, 60, 20])
    vote_fee = 483
    expect_event(tx, "voteRewardTransfer", {
        'operateAddress': operators[0],
        'validator': new_fee_address,
        'amount': vote_fee
    })
    assert tracker.delta() == TOTAL_REWARD + vote_fee - TOTAL_REWARD * 10 // 100
    turn_round(chain_get_validator_consensus())


def test_bep127_refuse_and_redelegate(candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=9, alternate_count=3, candidate_count=15)
    for i in range(15):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[70 + i], delegate_amount - i, btc_amount)
    turn_round()
    trackers = get_trackers(accounts[50:50 + 15])
    refuse_delegate(operators[0])
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    trackers[0].update_height()
    accept_delegate(operators[0])
    expect_validator_consensus(consensuses[1:10])
    turn_round(chain_get_validator_consensus())
    expect_validator_consensus(consensuses[0:9])
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    assert trackers[0].delta() == TOTAL_REWARD // 2 - 1


def test_edit_agent_info_and_claim_reward(candidate_hub, validator_set):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(7):
        delegate_validator(operators, i, accounts[70 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[77 + i], delegate_amount - i, btc_amount)
    turn_round()
    validator_set.setValidatorCount(0)
    candidate_hub.updateAgent(accounts[72], {'from': operators[0]})
    candidate_hub.editFeeAddress(accounts[72], {'from': operators[0]})
    candidate_hub.editVoteAddress(random_vote_address(), {'from': operators[0]})
    candidate_hub.editCommissionRate(550, {'from': operators[0]})
    candidate_hub.editConsensusAddress(accounts[72], {'from': operators[0]})
    stake_hub_claim_reward(accounts[70])
    turn_round(chain_get_validator_consensus(), round_count=2)


def test_maintenance_validator_upgrade_coin_btc_no_effect(validator_set, candidate_hub, slash_indicator):
    validator_set.setMaintainSlashPercent(0)
    set_validator_count(validator_count=31, alternate_count=0)
    validator_set = ValidatorSetMock[0]
    stake_manager.set_lp_rates()
    stake_manager.set_tlp_rates()
    btc_amount = 1000
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    operators, consensuses = add_candidates(40)
    for i in range(0, 40):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[1 + i], delegate_amount - i, btc_amount)
    tx_id0 = delegate_btc_success(operators[1], accounts[91], btc_amount, LOCK_SCRIPT, relay=accounts[91])
    tx_id1 = delegate_btc_success(operators[3], accounts[92], btc_amount, LOCK_SCRIPT, relay=accounts[92])
    candidate_hub.unregister({'from': operators[-1]})
    candidate_hub.unregister({'from': operators[-2]})
    candidate_hub.unregister({'from': operators[-3]})
    turn_round()
    set_validator_count(validator_count=31, alternate_count=3)
    validator_set.setValidatorCount(0)
    validator_set.setMaintainSlashPercent(10)
    validators = validator_set.getValidators()
    assert validator_set.validatorCount() == 0
    transfer_coin_success(operators[0], operators[2], accounts[50], delegate_amount)
    transfer_coin_success(operators[2], operators[0], accounts[52], delegate_amount - 2)
    transfer_btc_success(tx_id0, operators[2], accounts[91])
    delegate_btc_success(operators[4], accounts[93], btc_amount, LOCK_SCRIPT, relay=accounts[93])
    delegate_coin_success(operators[0], accounts[50], delegate_amount)
    turn_round(chain_get_validator_consensus())
    trackers0 = get_tracker(accounts[50])
    trackers1 = get_tracker(accounts[91])
    trackers2 = get_tracker(accounts[92])
    trackers3 = get_tracker(accounts[93])
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[91])
    stake_hub_claim_reward(accounts[92])
    assert trackers0.delta() == TOTAL_REWARD // 2 - 1
    assert trackers1.delta() == 0
    assert trackers2.delta() > 0
    enter_maintenance(operators[2])
    transfer_coin_success(operators[2], operators[0], accounts[50], delegate_amount // 2)
    transfer_btc_success(tx_id0, operators[3], accounts[91])
    undelegate_coin_success(operators[0], accounts[50], delegate_amount // 4)
    undelegate_coin_success(operators[2], accounts[50], delegate_amount // 4)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    stake_hub_claim_reward(accounts[91])
    stake_hub_claim_reward(accounts[92])
    stake_hub_claim_reward(accounts[93])
    assert trackers0.delta() > 0
    assert trackers1.delta() == 0
    assert trackers2.delta() > 0
    assert trackers3.delta() > 0
    turn_round(chain_get_validator_consensus(), round_count=2)


def test_update_consensus_address_block_produce_on_old_and_new(validator_set, candidate_hub):
    delegate_amount = MIN_INIT_DELEGATE_VALUE * 100
    btc_amount = 1000
    operators, consensuses = setup_validators_and_delegates(validator_count=5,
                                                            alternate_count=2,
                                                            candidate_count=7)
    for i in range(7):
        delegate_validator(operators, i, accounts[50 + i], delegate_amount - i, btc_amount)
        delegate_validator(operators, i, accounts[57 + i], delegate_amount - i, btc_amount)
    turn_round()
    expect_validator_consensus(consensuses[:5])
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    new_consensus = accounts[90]
    candidate_hub.editConsensusAddress(new_consensus, {'from': operators[0]})
    chain_deposit(new_consensus, deposit_count=10)
    chain_deposit(consensuses[0], deposit_count=1)
    turn_round(chain_get_validator_consensus())
    tracker = get_tracker(accounts[50])
    stake_hub_claim_reward(accounts[50])
    assert tracker.delta() == TOTAL_REWARD - 1
    chain_deposit(new_consensus, deposit_count=1)
    turn_round(chain_get_validator_consensus())
    stake_hub_claim_reward(accounts[50])
    assert tracker.delta() == TOTAL_REWARD - 1
