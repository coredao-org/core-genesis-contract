import secrets

from brownie import *
from .utils import random_address


def register_candidate(consensus=None, fee_address=None, operator=None, commission=500, margin=None) -> str:
    if consensus is None:
        consensus = random_address()
    if not operator:
        operator = accounts[0]
    if fee_address is None:
        fee_address = operator
    if margin is None:
        margin = CandidateHubMock[0].requiredMargin()

    CandidateHubMock[0].register(
        consensus, fee_address, commission,
        {'from': operator, 'value': margin}
    )
    return consensus


def get_candidate(operator=None):
    idx = CandidateHubMock[0].operateMap(operator)
    if idx == 0:
        return None
    return CandidateHubMock[0].candidateSet(idx - 1).dict()


def turn_round(miners: list = None, tx_fee=100, round_count=1):
    if miners is None:
        miners = []

    tx = None

    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[-10]})
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


def register_relayer(relayer_address=None):
    if relayer_address is None:
        relayer_address = accounts[0]
    RelayerHubMock[0].register({'from': relayer_address, 'value': RelayerHubMock[0].requiredDeposit()})


def get_current_round():
    round_tag = CandidateHubMock[0].roundTag()
    return round_tag


def set_last_round_tag(rount_tag):
    CandidateHubMock[0].setRoundTag(rount_tag)
    BitcoinStakeMock[0].setRoundTag(rount_tag)


def stake_hub_claim_reward(account):
    tx = None
    if isinstance(account, list):
        for i in account:
            tx = StakeHubMock[0].claimReward({'from': i})
    else:
        tx = StakeHubMock[0].claimReward({'from': account})
    return tx


def claim_stake_and_relay_reward(account):
    tx0 = stake_hub_claim_reward(account)
    tx1 = claim_relayer_reward(account)
    return tx0


def claim_relayer_reward(account):
    tx = None
    if isinstance(account, list):
        for i in account:
            tx = StakeHubMock[0].claimRelayerReward({'from': i})
    else:
        tx = StakeHubMock[0].claimRelayerReward({'from': account})
    return tx
