import pytest
import brownie
import rlp
from web3 import constants
from .delegate import *
from .utils import expect_event, padding_left, update_system_contract_address
from .common import turn_round, get_current_round, register_candidate, set_round_tag

TOTAL_REWARD = None
TX_FEE = 100
# BTC delegation-related
LOCK_SCRIPT = "0480db8767b17576a914574fdd26858c28ede5225a809f747c01fcc1f92a88ac"
LOCK_TIME = 1736956800
stake_manager = StakeManager()
round_reward_manager = RoundRewardManager()


@pytest.fixture(scope="module", autouse=True)
def set_up(btc_stake, stake_hub, btc_agent, core_agent, hash_power_agent, validator_set, gov_hub):
    global BTC_STAKE, STAKE_HUB, BTC_AGENT, CORE_AGENT, HASH_POWER_AGENT, TOTAL_REWARD
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    BTC_AGENT = btc_agent
    CORE_AGENT = core_agent
    HASH_POWER_AGENT = hash_power_agent
    btc_agent.setAssetWeight(1)
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * \
                   ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = BLOCK_REWARD // 2
    set_block_time_stamp(150, LOCK_TIME)


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub, system_reward):
    accounts[99].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))
    accounts[99].transfer(system_reward.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def set_rewards(reward, delegate_amount, unclaimed_reward=0):
    return {
        'reward': reward,
        'delegate_amount': delegate_amount,
        'unclaimed_reward': unclaimed_reward,
    }


def test_btc_agent_init_once_only(btc_agent):
    with brownie.reverts("the contract already init"):
        btc_agent.init()

@pytest.mark.parametrize('lst_btc_amount', [0, 4000])
def test_distribute_reward_success(btc_agent, btc_stake, lst_btc_amount):
    history_reward = 200
    turn_round()
    round_tag = get_current_round()
    candidates = accounts[:3]
    btc_amount = 1000
    rewards = [10000, 20000, 30000]
    set_round_tag(round_tag - 1)
    round_tag += 2
    btc_stake.setRoundTag(round_tag)
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    for c in candidates:
        btc_agent.setCandidateMap(c, lst_btc_amount, btc_amount)
        btc_stake.setCandidateMap(c, btc_amount, btc_amount, [round_tag - 1])
        btc_stake.setAccruedRewardPerBTCMap(c, round_tag - 1, history_reward)
    btc_agent.distributeReward(candidates, rewards, 0)
    for index, c in enumerate(candidates):
        reward = rewards[index]
        assert btc_stake.accruedRewardPerBTCMap(c,
                                                round_tag) == history_reward + reward * Utils.BTC_DECIMAL // btc_amount


def test_validators_and_reward_list_length_mismatch_failed(btc_agent):
    candidates = accounts[:3]
    rewards = [10000, 20000]
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    with brownie.reverts():
        btc_agent.distributeReward(candidates, rewards, 0)


def test_only_stake_hub_can_call_distribute_reward(btc_agent):
    candidates = accounts[:3]
    rewards = [10000, 20000, 30000]
    with brownie.reverts("the msg sender must be stake hub contract"):
        btc_agent.distributeReward(candidates, rewards, 0)


def test_reward_not_zero_with_zero_staked_tokens(btc_agent, btc_stake):
    turn_round()
    round_tag = get_current_round()
    candidates = accounts[:3]
    rewards = [10000, 20000, 30000]
    set_round_tag(round_tag - 1)
    round_tag += 2
    btc_stake.setRoundTag(round_tag)
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    btc_agent.distributeReward(candidates, rewards, 0)
    assert btc_stake.accruedRewardPerBTCMap(
        candidates[0], get_current_round()) == 0


def test_reward_zero_with_staked_tokens(btc_agent, btc_stake):
    candidates = accounts[:3]
    rewards = [0, 0, 0]
    round_tag = get_current_round() + 2
    btc_stake.setRoundTag(round_tag)
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    btc_agent.distributeReward(candidates, rewards, 0)
    for index, c in enumerate(candidates):
        assert btc_stake.accruedRewardPerBTCMap(c, round_tag) == 0


def test_reward_zero_with_nonzero_stake(btc_agent, btc_stake):
    turn_round()
    btc_amount = 2000
    candidates = accounts[:3]
    rewards = [0, 0, 0]
    round_tag = get_current_round() + 2
    btc_stake.setRoundTag(round_tag)
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    for c in candidates:
        btc_agent.setCandidateMap(c, 0, btc_amount)
        btc_stake.setCandidateMap(c, btc_amount, btc_amount, [round_tag - 1])
        btc_stake.setAccruedRewardPerBTCMap(c, round_tag - 1, 100)
    btc_agent.distributeReward(candidates, rewards, 0)
    for index, c in enumerate(candidates):
        assert btc_stake.accruedRewardPerBTCMap(c, round_tag) == 0


def test_get_stake_amounts_success(btc_agent, btc_stake, set_candidate):
    btc_amount = 3000
    operators, consensuses = set_candidate
    turn_round()
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    btc_agent.getStakeAmounts(operators, 0)
    for o in operators:
        btc_stake.setCandidateMap(o, btc_amount, btc_amount, [])
    amounts, total_amount = btc_agent.getStakeAmounts(
        operators, 0).return_value
    assert amounts == [btc_amount, btc_amount, btc_amount]
    assert total_amount == btc_amount * 3


def test_query_address_empty(btc_agent, btc_stake, set_candidate):
    operators = []
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    amounts, total_amount = btc_agent.getStakeAmounts(
        operators, 0).return_value
    assert sum(amounts) == total_amount == 0


def test_query_address_zero(btc_agent, btc_stake, set_candidate):
    operators = ZERO_ADDRESS
    turn_round()
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    amounts, total_amount = btc_agent.getStakeAmounts(
        [operators], 0).return_value
    assert sum(amounts) == total_amount == 0


def test_only_stake_hub_can_call(btc_agent, btc_stake, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    with brownie.reverts("the msg sender must be stake hub contract"):
        btc_agent.getStakeAmounts(operators, 0)


def test_set_new_round_success(btc_agent, btc_stake, set_candidate):
    btc_amount = 3000
    operators, consensuses = set_candidate
    round_tag = 7
    assert btc_stake.roundTag() == round_tag
    turn_round()
    round_tag += 1
    for o in operators:
        btc_stake.setCandidateMap(o, 0, btc_amount, [])
    update_system_contract_address(btc_agent, stake_hub=accounts[0])
    btc_agent.setNewRound(operators, get_current_round())
    for op in operators:
        assert btc_stake.candidateMap(op) == [btc_amount, btc_amount]
    assert btc_stake.roundTag() == round_tag


def test_only_stake_hub_can_call_set_new_round(btc_agent, btc_stake, set_candidate):
    with brownie.reverts("the msg sender must be stake hub contract"):
        btc_agent.setNewRound(accounts[:3], get_current_round())


def test_only_stake_hub_can_call_claim_reward(btc_agent):
    with brownie.reverts("the msg sender must be stake hub contract"):
        btc_agent.claimReward(constants.ADDRESS_ZERO, 1000, 1, False)


def test_get_grades(btc_agent, btc_stake):
    old_grades = [[0, 1000], [2000, 10000]]
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode(old_grades)
    btc_agent.updateParam('grades', grades_encode)
    assert old_grades == btc_agent.getGrades()


# getGrade
def test_get_grade_inactive_no_grades(btc_agent):
    btc_agent.setIsActive(False)
    btc_agent.popLpRates()
    percentage, stake_rate = btc_agent.getGrade(0)
    assert percentage == 10000
    assert stake_rate == 0


def test_get_grade_inactive_with_grades(btc_agent):
    btc_agent.setIsActive(False)
    btc_agent.popLpRates()
    btc_agent.setLpRates(0, 1000)
    btc_agent.setLpRates(3000, 2000)
    asset_weight = btc_agent.assetWeight()
    percentage, stake_rate = btc_agent.getGrade(asset_weight * 10)
    assert percentage == 10000
    assert stake_rate == 0


def test_get_grade_active_empty_grades(btc_agent):
    btc_agent.setIsActive(True)
    btc_agent.popLpRates()
    percentage, stake_rate = btc_agent.getGrade(0)
    assert percentage == 10000
    assert stake_rate == 0


def test_get_grade_active_selects_first_grade_for_low_rate(btc_agent):
    btc_agent.setIsActive(True)
    btc_agent.popLpRates()
    # grades: (stakeRate, percentage)
    btc_agent.setLpRates(0, 1000)
    btc_agent.setLpRates(3000, 2000)
    btc_agent.setLpRates(7000, 4000)
    btc_agent.setLpRates(10000, 10000)
    percentage, stake_rate = btc_agent.getGrade(0)
    assert percentage == 1000
    assert stake_rate == 0


def test_get_grade_active_selects_middle_grade(btc_agent):
    btc_agent.setAssetWeight(1e10)
    btc_agent.setIsActive(True)
    btc_agent.popLpRates()
    btc_agent.setLpRates(0, 1000)
    btc_agent.setLpRates(3000, 2000)
    btc_agent.setLpRates(7000, 4000)
    btc_agent.setLpRates(10000, 10000)
    asset_weight = btc_agent.assetWeight()
    percentage, stake_rate = btc_agent.getGrade(asset_weight * 7000)
    assert percentage == 4000
    assert stake_rate == asset_weight * 7000


def test_get_grade_active_selects_correct_lower_bound(btc_agent):
    btc_agent.setAssetWeight(1e10)
    btc_agent.setIsActive(True)
    btc_agent.popLpRates()
    btc_agent.setLpRates(0, 1000)
    btc_agent.setLpRates(3000, 2000)
    btc_agent.setLpRates(7000, 4000)
    btc_agent.setLpRates(10000, 10000)
    asset_weight = btc_agent.assetWeight()
    # rate between 3000 and 7000 should select grade stakeRate=3000
    btc_amount = 3e8
    coin_amount = 15000e18
    percentage, stake_rate = btc_agent.getGrade(coin_amount / btc_amount)
    assert percentage == 2000
    assert stake_rate == asset_weight * 3000


def test_get_grade_active_selects_highest_grade(btc_agent):
    btc_agent.setAssetWeight(1e10)
    btc_agent.setIsActive(True)
    btc_agent.popLpRates()
    btc_agent.setLpRates(0, 1000)
    btc_agent.setLpRates(3000, 2000)
    btc_agent.setLpRates(7000, 4000)
    btc_agent.setLpRates(10000, 10000)
    btc_agent.setLpRates(12000, 11000)
    asset_weight = btc_agent.assetWeight()
    btc_amount = 1e8
    coin_amount = 12000e18
    percentage, stake_rate = btc_agent.getGrade(coin_amount / btc_amount)
    assert percentage == 11000
    assert stake_rate == asset_weight * 12000

def test_update_param_failed(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    with brownie.reverts("UnsupportedGovParam: error key"):
        btc_agent.updateParam('error key', constants.ADDRESS_ZERO)


def test_only_gov_can_call_update_param(btc_agent):
    with brownie.reverts("the msg sender must be governance contract"):
        btc_agent.updateParam('error key', '0x00')


def test_update_param_allowed_only_after_init_by_gov(btc_agent):
    btc_agent.setAlreadyInit(False)
    with brownie.reverts("the contract not init yet"):
        btc_agent.updateParam('error key', '0x00')


@pytest.mark.parametrize("grades", [
    [[0, 1000], [1000, 10000]],
    [[0, 1200], [2000, 2000], [3000, 10000]],
    [[0, 1000], [2000, 2000], [3000, 4000], [3500, 9000], [4000, 10000]],
    [[0, 1000], [3000, 2000], [12000, 4000], [19000, 9000], [22222, 10000]]
])
def test_update_param_grades_success(btc_agent, grades):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    btc_agent.updateParam('grades', grades_encode)
    for i in range(btc_agent.getGradesLength()):
        grades_value = btc_agent.grades(i)
        assert grades_value == grades[i]


def test_length_error_revert(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode([])
    with brownie.reverts("MismatchParamLength: grades"):
        btc_agent.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grades", [
    [[0, 1000], [1000, 10000]],
    [[0, 1200], [2000, 2000], [3000, 10000]],
    [[0, 1000], [3000, 2000], [12000, 14000], [19000, 19000], [22222, 20000]]
])
def test_duplicate_update_grades(btc_agent, grades):
    old_grades = [[0, 1000], [2000, 10000]]
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode(old_grades)
    btc_agent.updateParam('grades', grades_encode)
    for i in range(btc_agent.getGradesLength()):
        grades_value = btc_agent.grades(i)
        assert grades_value == old_grades[i]
    grades_encode = rlp.encode(grades)
    btc_agent.updateParam('grades', grades_encode)
    for i in range(btc_agent.getGradesLength()):
        grades_value = btc_agent.grades(i)
        assert grades_value == grades[i]


@pytest.mark.parametrize("grades", [
    [[100000001, 1000], [1000, 10000]],
    [[0, 1000], [100000001, 2000], [3000, 10000]],
    [[0, 1000], [2000, 2000], [100000001, 10000]],
    [[0, 1000], [100000001, 2000], [100000001, 10000]],
])
def test_stake_rate_exceeds_maximum(btc_agent, grades):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades)
    with brownie.reverts(f"OutOfBounds: stakeRate, 100000001, 0, 100000000"):
        btc_agent.updateParam('grades', grades_encode)


@pytest.mark.parametrize("percentage", [99999, 1000000, 100000])
def test_final_percentage_below_1_reverts(btc_agent, percentage):
    max_percentage = 1000000
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades = [[0, 1000], [2000, percentage]]
    grades_encode = rlp.encode(grades)
    if percentage > max_percentage:
        with brownie.reverts(f"OutOfBounds: percentage, {grades[-1][-1]}, 0, 1000000"):
            btc_agent.updateParam('grades', grades_encode)
    else:
        btc_agent.updateParam('grades', grades_encode)


def test_non_last_percentage_can_exceed_limit(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades = [[0, 1000], [2000, 11000], [3000, 12000]]
    grades_encode = rlp.encode(grades)
    btc_agent.updateParam('grades', grades_encode)
    for i in range(btc_agent.getGradesLength()):
        grades_value = btc_agent.grades(i)
        assert grades_value == grades[i]


@pytest.mark.parametrize("grades", [
    ['stakeRate', [0, 1000], [2000, 10000], [1000, 12000]],
    ['stakeRate', [0, 1000], [5000, 2000], [4000, 10000]],
    ['stakeRate', [0, 1000], [3000, 9000], [3000, 8000], [4000, 10000]],
    ['percentage', [0, 8000], [3000, 7000], [4000, 10000]],
    ['percentage', [0, 1000], [2000, 7000], [3000, 6000], [4000, 10000]]
])
def test_incorrect_reward_rate_percentage_order_reverts(btc_agent, grades):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode(grades[1:])
    with brownie.reverts(f"{grades[0]} disorder"):
        btc_agent.updateParam('grades', grades_encode)


def test_lowest_stake_rate_must_be_zero(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode([[1000, 2000], [2000, 10000]])
    with brownie.reverts(f"lowest stakeRate must be zero"):
        btc_agent.updateParam('grades', grades_encode)


def test_percentage_cannot_be_zero(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    grades_encode = rlp.encode([[1000, 0]])
    with brownie.reverts(f"lowest stakeRate must be zero"):
        btc_agent.updateParam('grades', grades_encode)


@pytest.mark.parametrize("grade_active", [0, 1])
def test_update_param_grade_active_success(btc_agent, grade_active):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    btc_agent.updateParam('gradeActive', grade_active)
    if grade_active:
        actual_active = True
    else:
        actual_active = False
    assert btc_agent.gradeActive() == actual_active


@pytest.mark.parametrize("grade_active", [2, 3, 4])
def test_update_param_grade_active_failed(btc_agent, grade_active):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: gradeActive, {grade_active}, 0, 1"):
        btc_agent.updateParam('gradeActive', grade_active)


def test_update_param_grade_active_length_failed(btc_agent):
    update_system_contract_address(btc_agent, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(0), 64)
    with brownie.reverts(f"MismatchParamLength: gradeActive"):
        btc_agent.updateParam('gradeActive', hex_value)
