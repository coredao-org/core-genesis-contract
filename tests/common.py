from brownie import *
from .utils import random_address, random_vote_address


def register_candidate(consensus=None, fee_address=None, operator=None, commission=500, margin=None,
                       vote_address=None) -> str:
    if consensus is None:
        consensus = random_address()
    if not operator:
        operator = accounts[0]
    if fee_address is None:
        fee_address = operator
    if margin is None:
        margin = CandidateHubMock[0].requiredMargin()
    if vote_address is None:
        vote_address = random_vote_address()
    tx = CandidateHubMock[0].register(
        consensus, fee_address, commission, vote_address,
        {'from': operator, 'value': margin}
    )
    return consensus


def get_candidate(operator=None):
    idx = CandidateHubMock[0].operateMap(operator)
    if idx == 0:
        return None
    return CandidateHubMock[0].candidateSet(idx - 1).dict()


def chain_deposit(miners, tx_fee=100, deposit_count=1):
    if isinstance(miners, list):
        for miner in miners:
            for _ in range(deposit_count):
                tx = ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[99]})
    else:
        for _ in range(deposit_count):
            tx = ValidatorSetMock[0].deposit(miners, {"value": tx_fee, "from": accounts[99]})


def chain_vote(miners, weights):
    ValidatorSetMock[0].vote(miners, weights, {"from": accounts[99]})


def chain_get_validator_consensus():
    consensus, vote_addresses = ValidatorSetMock[0].getValidatorsAndVoteAddresses()
    return consensus


def turn_round(miners: list = None, tx_fee=100, round_count=1, weights=None):
    if miners is None:
        miners = []
    if weights is None:
        weights = [10] * len(miners)
    tx = None

    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[99]})
        ValidatorSetMock[0].vote(miners, weights, {"from": accounts[99]})
        tx = CandidateHubMock[0].turnRound()
        chain.sleep(1)
    return tx


def execute_proposal(target, value, signature, calldata, msg):
    tx = GovHubMock[0].propose([target], [value], [signature], [calldata], [msg])
    proposal_id = tx.events['ProposalCreated'][0]['id']
    chain.mine(1)
    for member in GovHubMock[0].getMembers():
        GovHubMock[0].castVote(proposal_id, True, {'from': member})
    chain.mine(GovHubMock[0].votingPeriod())
    GovHubMock[0].execute(proposal_id)
    return proposal_id


def expect_validator_consensus(consensuses):
    assert len(chain_get_validator_consensus()) == len(consensuses)
    for consensus in chain_get_validator_consensus():
        assert consensus in consensuses


def register_relayer(relayer_address=None):
    if relayer_address is None:
        relayer_address = accounts[0]
    RelayerHubMock[0].register({'from': relayer_address, 'value': RelayerHubMock[0].requiredDeposit()})


def get_current_round():
    round_tag = CandidateHubMock[0].roundTag()
    return round_tag


def set_round_tag(round_tag):
    CandidateHubMock[0].setRoundTag(round_tag)
    BitcoinStakeMock[0].setRoundTag(round_tag)
    CoreAgentMock[0].setRoundTag(round_tag)
    PledgeAgentMock[0].setRoundTag(round_tag)


def stake_hub_claim_reward(account):
    tx = None
    if isinstance(account, list):
        for i in account:
            tx = StakeHubMock[0].claimReward({'from': i})

    else:
        tx = StakeHubMock[0].claimReward({'from': account})
    return tx


def claim_stake_and_relay_reward(account):
    tx0 = None
    if isinstance(account, list):
        for a in account:
            tx0 = stake_hub_claim_reward(a)
    else:
        tx0 = stake_hub_claim_reward(account)
    return tx0


def slash_validator(consensus, slash_type='felony'):
    tx = None
    slash_indicator = SlashIndicatorMock[0]
    if slash_type == 'felony':
        slash_threshold = slash_indicator.felonyThreshold()
        for _ in range(slash_threshold):
            tx = slash_indicator.slash(consensus)
        assert 'validatorFelony' in tx.events
    elif slash_type == 'minor':
        slash_threshold = slash_indicator.misdemeanorThreshold()
        for _ in range(slash_threshold):
            tx = slash_indicator.slash(consensus)
        assert 'validatorMisdemeanor' in tx.events
    return tx


def refuse_delegate(operator):
    tx = CandidateHubMock[0].refuseDelegate({'from': operator})
    return tx


def accept_delegate(operator):
    tx = CandidateHubMock[0].acceptDelegate({'from': operator})
    return tx


def enter_maintenance(operator):
    tx = ValidatorSetMock[0].enterMaintenance({'from': operator})
    assert 'validatorEnterMaintenance' in tx.events
    return tx


def exit_maintenance(operator):
    tx = ValidatorSetMock[0].exitMaintenance({'from': operator})
    assert 'validatorExitMaintenance' in tx.events
    return tx
