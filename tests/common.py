import secrets

from brownie import *
from .utils import random_address, get_public_key_by_idx, public_key2PKHash, get_public_key_by_address


def register_candidate(consensus=None, fee_address=None, operator=None, commission=500, margin=None) -> str:
    """
    :param consensus:
    :param fee_address:
    :param operator:
    :param commission:
    :param margin:
    :return: consensus address
    """
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
    return CandidateHubMock[0].candidateSet(idx-1).dict()


def turn_round(miners: list = None, tx_fee=100, round_count=1):
    if miners is None:
        miners = []

    tx = None

    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[-1]})
        tx = CandidateHubMock[0].turnRound()
        chain.sleep(1)

    return tx


def set_miner_power(round_tag, idx_list, power_list):
    assert len(idx_list) == len(power_list)

    ret_public_key = []
    ret_btc_block_hash = []

    for idx, power in zip(idx_list, power_list):
        if not isinstance(idx, int):
            public_key = get_public_key_by_address(idx)
        else:
            public_key = get_public_key_by_idx(idx)
        ret_public_key.append(public_key)
        pkHash = public_key2PKHash(public_key)
        btc_block_hash = '0x' + secrets.token_hex(32)
        ret_btc_block_hash.append(btc_block_hash)

        BtcLightClientMock[0].setBlock(btc_block_hash, pkHash)
        BtcLightClientMock[0].addMiner(round_tag, pkHash, power)

    if len(ret_public_key) == 1:
        return ret_public_key[0], ret_btc_block_hash[0]
    return ret_public_key, ret_btc_block_hash


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


