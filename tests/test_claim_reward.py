import brownie
import pytest
from brownie import *
from .calc_reward import set_delegate, parse_delegation, Discount, set_btc_lst_delegate
from .common import register_candidate, turn_round, get_current_round, stake_hub_claim_reward, set_round_tag, \
    claim_stake_and_relay_reward
from .delegate import *
from .utils import *

MIN_INIT_DELEGATE_VALUE = 0
DELEGATE_VALUE = 0
BLOCK_REWARD = 0
COIN_VALUE = 10000
BTC_VALUE = 200
POWER_VALUE = 20
BTC_LST_VALUE = 600
TX_FEE = 100
FEE = 100
BTC_REWARD = 0
MONTH = 30
YEAR = 360
TOTAL_REWARD = 0
# BTC delegation-related
PUBLIC_KEY = "0223dd766d6e38eaf9c044dcb18d8221fe8c9a5763ca331e93fadc8f55949b8e12"
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
PAY_ADDRESS = "0xa914c0958c8d9357598c5f7a6eea8a807d81683f9bb687"
LOCK_TIME = 1736956800
# BTCLST delegation-related
BTCLST_LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
BTCLST_REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, pledge_agent,
                     btc_lst_stake, gov_hub, hash_power_agent, btc_agent):
    global BLOCK_REWARD, FEE, BTC_REWARD, COIN_REWARD, TOTAL_REWAR, DELEGATE_VALUE, TOTAL_REWARD, HASH_POWER_AGENT, PLEDGE_AGENT
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LIGHT_CLIENT, MIN_INIT_DELEGATE_VALUE, CANDIDATE_HUB, BTC_LST_STAKE
    FEE = FEE * 100
    print('accountssfasf12312', len(accounts))
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    BTC_REWARD = TOTAL_REWARD
    MIN_INIT_DELEGATE_VALUE = pledge_agent.requiredCoinDeposit()
    DELEGATE_VALUE = MIN_INIT_DELEGATE_VALUE * 1000
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    CANDIDATE_HUB = candidate_hub
    BTC_LIGHT_CLIENT = btc_light_client
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    set_block_time_stamp(150, LOCK_TIME)
    tlp_rates, lp_rates = Discount().get_init_discount()
    btc_stake.setInitTlpRates(*tlp_rates)
    btc_agent.setInitLpRates(*lp_rates)
    btc_stake.setIsActive(True)
    btc_agent.setIsActive(True)
    BTC_LST_STAKE = btc_lst_stake
    PLEDGE_AGENT = pledge_agent
    HASH_POWER_AGENT = hash_power_agent
    print('accountssfasf12312', len(accounts))
    btc_lst_stake.updateParam('add', BTCLST_LOCK_SCRIPT, {'from': gov_hub.address})
    print('dsfafsd',gov_hub.address)
    print('accountssfasf12312', len(accounts))

@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


class Delegator:
    def __init__(self, delegator):
        self.btc_delegate = BtcStake()
        self.delegator = delegator
        self.btc_tx_ids = []

    def get_address(self):
        return self.delegator

    def delegate_btc(self, agent, btc_amount, lock_script, lock_data=None, relay=None, stake_duration=None,
                     fee=1,
                     script_type='p2sh', lock_time=None):
        tx_id = delegate_btc_success(agent, self.delegator, btc_amount, lock_script, lock_data, relay, stake_duration,
                                     fee, script_type, lock_time)
        return tx_id

    def transfer_btc(self, tx_id, target_candidate):
        tx = transfer_btc_success(tx_id, target_candidate, self.delegator)
        return tx

    def delegate_btc_lst(self, btc_amount, lock_script, percentage, relay=None):
        delegate_btc_lst_success(self.delegator, btc_amount, lock_script, percentage, relay)

    def redeem_btc_lst(self, amount, pkscript):
        redeem_btc_lst_success(self.delegator, amount, pkscript)

    def transfer_btc_lst(self, amount, to):
        transfer_btc_lst_success(self.delegator, amount, to)

    def delegate_power(self, candidate, value=1, stake_round=0):
        delegate_power_success(candidate, self.delegator, value, stake_round)

    def delegate_coin(self, candidate, amount):
        tx = delegate_coin_success(candidate, self.delegator, amount)
        return tx

    def undelegate_coin(self, candidate, amount):
        undelegate_coin_success(candidate, self.delegator, amount)

    def transfer_coin(self, source_agent, target_agent, amount):
        transfer_coin_success(source_agent, target_agent, self.delegator, amount)

    def claim_reward(self):
        stake_hub_claim_reward(self.delegator)

    def old_delegate_coin(self, candidate, amount=None, old=True):
        old_delegate_coin_success(candidate, self.delegator, amount, old)

    def old_undelegate_coin(self, candidate, amount=None, old=True):
        old_undelegate_coin_success(candidate, self.delegator, amount, old)

    def old_transfer_coin(self, source_agent, target_agent, amount=None, old=True):
        old_transfer_coin_success(source_agent, target_agent, self.delegator, amount, old)

    def old_claim_reward(self, candidates):
        old_claim_reward_success(candidates, self.delegator)

    def old_delegate_btc(self, candidate, amount, lock_time):
        tx_id = old_delegate_btc_success(amount, candidate, self.delegator, lock_time)
        self.btc_tx_ids.append(tx_id)
        return tx_id

    def old_claim_btc_reward(self):
        tx = old_claim_btc_reward_success(self.btc_tx_ids, self.delegator)
        return tx


def add_delegators():
    delegators = []
    for account in accounts[:5]:
        delegators.append(Delegator(account))
    return delegators


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


def init_hybrid_score_mock():
    STAKE_HUB.initHybridScoreMock()


def mock_btc_stake_lock_time(timestamp, stake_round=None):
    if stake_round is None:
        stake_round = random.randint(1, 10)
    timestamp = timestamp + (Utils.ROUND_INTERVAL * stake_round)
    end_round = timestamp // Utils.ROUND_INTERVAL
    return timestamp, end_round


class TestInitHardForkDelegate:
    def test_init_hard_fork_delegate0(self, pledge_agent, candidate_hub):
        init_round_tag, timestamp = mock_current_round()
        mock_btc_stake_lock_time(timestamp)
        old_turn_round()
        set_round_tag(init_round_tag)
        delegators = add_delegators()
        operators, consensuses = add_candidates()
        candidate_hub.setValidatorCount(21)
        old_turn_round()
        tx_ids = []
        lock_time, end_round = mock_btc_stake_lock_time(timestamp, 5)
        for index, op in enumerate(operators):
            delegators[0].old_delegate_coin(op, BTC_VALUE + index)
        for index, op in enumerate(operators[0:10]):
            tx_id = delegators[0].old_delegate_btc(op, BTC_VALUE + index, lock_time)
            tx_ids.append(tx_id)
        lock_time, end_round = mock_btc_stake_lock_time(timestamp, 3)
        delegators[0].delegate_coin(operators[0], DELEGATE_VALUE)
        delegators[0].delegate_coin(operators[7], DELEGATE_VALUE)
        for index, op in enumerate(operators[10:12]):
            btc_amount = BTC_VALUE + (index + 10)
            tx_id = delegators[1].old_delegate_btc(op, btc_amount, lock_time)
            tx_ids.append(tx_id)
        delegators[0].old_delegate_coin(operators[8], DELEGATE_VALUE)
        delegators[1].old_delegate_coin(operators[12], DELEGATE_VALUE)
        delegators[2].delegate_power(operators[0], 1)
        old_turn_round(consensuses)
        delegators[2].delegate_power(operators[0], 1)
        old_turn_round(consensuses)
        delegators[2].delegate_power(operators[0], 1)
        old_turn_round(consensuses)
        delegators[0].old_claim_btc_reward()
        delegators[2].old_claim_btc_reward()
        init_hybrid_score_mock()
        turn_round(consensuses)

    def test_account_create(self):
        print('accountssfasf', len(accounts))
        random_address()
        for  index,account in enumerate(accounts):
            print(f'index,account{account}',account.balance())
        print('accounts', len(accounts))


class TestClaimReward:
    @pytest.mark.parametrize("hard_cap", [
        [['coreHardcap', 2000], ['hashHardcap', 9000], ['btcHardcap', 10000]],
        [['coreHardcap', 3000], ['hashHardcap', 3000], ['btcHardcap', 3000]],
        [['coreHardcap', 100000], ['hashHardcap', 50000], ['btcHardcap', 30000]],
    ])
    def test_claim_reward_after_hardcap_update(self, stake_hub, hard_cap, set_candidate):
        update_system_contract_address(stake_hub, gov_hub=accounts[0])
        for h in hard_cap:
            hex_value = padding_left(Web3.to_hex(h[1]), 64)
            stake_hub.updateParam(h[0], hex_value)
        operators, consensuses = set_candidate
        turn_round()
        delegate_coin_success(operators[0], accounts[0], COIN_VALUE)
        delegate_btc_success(operators[1], accounts[1], BTC_VALUE, LOCK_SCRIPT, relay=accounts[1])
        delegate_power_success(operators[2], accounts[2], POWER_VALUE)
        delegate_btc_lst_success(accounts[0], BTC_LST_VALUE, BTCLST_LOCK_SCRIPT)
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
        ], BLOCK_REWARD // 2, btc_lst_stake={
            accounts[0]: set_btc_lst_delegate(BTC_LST_VALUE)},
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
