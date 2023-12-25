import pytest
from web3 import Web3, constants
import brownie
from brownie import *
from eth_abi import encode_abi
from .utils import expect_event, padding_left, expect_event_not_emitted, encode_args_with_signature
from .common import execute_proposal


origin_members = ["0x9fB29AAc15b9A4B7F17c3385939b007540f4d791", "0x96C42C56fdb78294F96B0cFa33c92bed7D75F96a"]


@pytest.fixture(scope="module", autouse=True)
def set_up():
    pass


def fake_gov():
    GovHubMock[0].updateContractAddr(
        ValidatorSetMock[0].address,
        SlashIndicatorMock[0].address,
        SystemRewardMock[0].address,
        BtcLightClientMock[0].address,
        RelayerHubMock[0].address,
        CandidateHubMock[0].address,
        accounts[0],
        PledgeAgentMock[0].address,
        BurnMock[0].address,
        FoundationMock[0].address
    )


def test_receive_money(gov_hub):
    tx = accounts[0].transfer(gov_hub.address, 1)
    expect_event(tx, 'receiveDeposit', {'from': accounts[0], 'amount': 1})


def test_receive_money_with_zero_value(gov_hub):
    tx = accounts[0].transfer(gov_hub.address, 0)
    expect_event_not_emitted(tx, 'receiveDeposit')


def test_update_param_failed_with_address_which_is_not_gov(gov_hub):
    with brownie.reverts("the msg sender must be governance contract"):
        gov_hub.updateParam("proposalMaxOperations", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_failed_with_unknown_key(gov_hub):
    fake_gov()
    with brownie.reverts("unknown param"):
        gov_hub.updateParam("jkxjfi", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_failed_about_key_proposalMaxOperations_with_invalid_length(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['proposalMaxOperations'])
    with brownie.reverts(f"typed error: {error_msg}"):
        gov_hub.updateParam("proposalMaxOperations", "0x00000000000000000000000000000000000001")


def test_update_param_failed_about_key_proposalMaxOperations_out_of_range(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["proposalMaxOperations", 0, 1, Web3.toInt(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"typed error: {error_msg}"):
        gov_hub.updateParam("proposalMaxOperations", "0x0000000000000000000000000000000000000000000000000000000000000000")


def test_update_param_success_about_key_proposalMaxOperations(gov_hub):
    fake_gov()
    tx = gov_hub.updateParam("proposalMaxOperations", "0x0000000000000000000000000000000000000000000000000000000000000001")
    expect_event(tx, "paramChange", {
        "key": "proposalMaxOperations",
        "value": "0x0000000000000000000000000000000000000000000000000000000000000001"
    })
    assert gov_hub.proposalMaxOperations() == 1


def test_update_param_failed_about_key_votingPeriod_with_invalid_length(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['votingPeriod'])
    with brownie.reverts(f"typed error: {error_msg}"):
        gov_hub.updateParam("votingPeriod", "0x00000000000000000000000000000000000001")


def test_update_param_failed_about_key_votingPeriod_out_of_range(gov_hub):
    fake_gov()
    value = "0x0000000000000000000000000000000000000000000000000000000000007079"
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["votingPeriod", Web3.toInt(hexstr=value), 28800, Web3.toInt(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"typed error: {error_msg}"):
        gov_hub.updateParam('votingPeriod', value)


def test_update_param_success_about_key_votingPeriod(gov_hub):
    fake_gov()
    tx = gov_hub.updateParam("votingPeriod", "0x0000000000000000000000000000000000000000000000000000000000007080")
    expect_event(tx, 'paramChange', {
        "key": "votingPeriod",
        "value": "0x0000000000000000000000000000000000000000000000000000000000007080"
    })
    assert gov_hub.votingPeriod() == 28800


def test_get_member_success(gov_hub):
    assert gov_hub.getMembers() == origin_members


def test_remove_member_failed_with_address_which_is_not_gov(gov_hub):
    with brownie.reverts("the msg sender must be governance contract"):
        gov_hub.removeMember(origin_members[0])


def test_remove_member_failed_with_nonexistent_member(gov_hub):
    gov_hub.resetMembers(accounts[:6])
    fake_gov()
    with brownie.reverts("member does not exist"):
        gov_hub.removeMember(accounts[6])


def test_remove_member_failed_due_to_minimum_numbers(gov_hub):
    fake_gov()
    with brownie.reverts("at least five members in DAO"):
        gov_hub.removeMember(accounts[0])


def test_remove_member_success(gov_hub):
    gov_hub.resetMembers(accounts[:7])
    fake_gov()
    tx = gov_hub.removeMember(accounts[6])
    expect_event(tx, "MemberDeleted", {'member': accounts[6]})


def test_add_member_failed_with_address_which_is_not_gov(gov_hub):
    with brownie.reverts("the msg sender must be governance contract"):
        gov_hub.addMember(accounts[2])


def test_propose_failed_with_invalid_length(gov_hub):
    with brownie.reverts("proposal function information arity mismatch"):
        gov_hub.propose([gov_hub.address], [1, 2], ["1", "2", "3"], ["0x", "0x"], "")


def test_propose_failed_with_empty_targets(gov_hub):
    with brownie.reverts("must provide actions"):
        gov_hub.propose([], [], [], [], "")


def test_propose_failed_with_targets_which_is_more_than_proposalMaxOperations(gov_hub):
    proposalMaxOperations = gov_hub.proposalMaxOperations()
    targets = []
    values = []
    signatures = []
    calldatas = []

    for i in range(proposalMaxOperations + 1):
        targets.append(gov_hub.address)
        values.append(i)
        signatures.append(i)
        calldatas.append("0x")

    with brownie.reverts("too many actions"):
        gov_hub.propose(targets, values, signatures, calldatas, "")


def test_create_propose_success(gov_hub):
    tx = gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose")
    expect_event(tx, "ProposalCreated")


def test_propose_failed_with_member_which_already_has_pending_proposal(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    with brownie.reverts("one live proposal per proposer, found an already pending proposal"):
        gov_hub.propose([gov_hub.address], [1], ["234"], ["0x"], "test propose two")


def test_propose_failed_with_member_which_already_has_active_proposal(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    with brownie.reverts("one live proposal per proposer, found an already active proposal"):
        gov_hub.propose([gov_hub.address], [1], ["234"], ["0x"], "test propose two")


def test_remove_member_success_through_propose(gov_hub):
    gov_hub.resetMembers(accounts[:7])
    gov_hub.propose(
        [gov_hub.address],
        [0],
        ["removeMember(address)"],
        [encode_abi(['address'], [accounts[6].address])],
        "remove member"
    )
    propose_id = gov_hub.latestProposalIds(accounts[0])
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(propose_id, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    state = gov_hub.getState(propose_id)
    assert state == 4

    # execute
    tx = gov_hub.execute(propose_id)
    expect_event(tx, "ProposalExecuted")
    expect_event(tx, 'MemberDeleted', {'member': accounts[6]})

    assert gov_hub.members(accounts[6]) == 0


def test_add_duplicate_member_through_propose(gov_hub):
    __add_member(gov_hub, accounts[2].address)
    gov_hub.propose(
        [gov_hub.address],
        [0],
        ["addMember(address)"],
        [encode_abi(['address'], [accounts[2].address])],
        "add new member"
    )
    propose_id = gov_hub.latestProposalIds(accounts[0])
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(propose_id, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    state = gov_hub.getState(propose_id)
    assert state == 4

    # execute
    with brownie.reverts("Transaction execution reverted."):
        gov_hub.execute(propose_id)


def test_add_member_through_propose(gov_hub):
    gov_hub.propose(
        [gov_hub.address],
        [0],
        ["addMember(address)"],
        [encode_abi(['address'], [accounts[2].address])],
        "add new member"
    )
    propose_id = gov_hub.latestProposalIds(accounts[0])
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(propose_id, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    state = gov_hub.getState(propose_id)
    assert state == 4

    # execute
    tx = gov_hub.execute(propose_id)
    expect_event(tx, "ProposalExecuted")
    expect_event(tx, "MemberAdded", {'member': accounts[2]})
    assert gov_hub.members(accounts[2]) > 0


def test_update_param_through_propose(gov_hub):
    current_proposalMaxOperations = gov_hub.proposalMaxOperations()
    new_value = current_proposalMaxOperations + 1
    padding_value = Web3.toBytes(hexstr=padding_left(Web3.toHex(new_value), 64))

    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['proposalMaxOperations', padding_value]),
        "update parameter"
    )
    assert gov_hub.proposalMaxOperations() == new_value


def test_update_param_voting_period_through_propose(gov_hub):
    new_value = 28800
    padding_value = padding_left(Web3.toHex(new_value), 64)
    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['votingPeriod', Web3.toBytes(hexstr=padding_value)]),
        "update voting period"
    )
    assert gov_hub.votingPeriod() == 28800


def test_cast_vote_failed_with_address_which_is_not_member(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    with brownie.reverts("Test: only member is allowed to call the method"):
        gov_hub.castVote(1, True, {'from': accounts[3]})


def test_cast_vote_failed_with_invalid_proposal_id(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    with brownie.reverts("state: invalid proposal id"):
        gov_hub.castVote(2, True)


def test_cast_vote_failed_with_inactive_proposal(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(2 + gov_hub.votingPeriod())
    with brownie.reverts("voting is closed"):
        gov_hub.castVote(1, True)


def test_cast_vote_success(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    tx = gov_hub.castVote(1, True)
    expect_event(tx, "VoteCast", {
        "voter": accounts[0],
        "proposalId": 1,
        "support": True
    })
    tx = gov_hub.castVote(1, False, {'from': accounts[1]})
    expect_event(tx, "VoteCast", {
        "voter": accounts[1],
        "proposalId": 1,
        "support": False
    })
    proposal = gov_hub.proposals(1).dict()
    assert proposal['forVotes'] == 1
    assert proposal['againstVotes'] == 1


def test_cast_vote_failed_with_voting_twice(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    gov_hub.castVote(1, True)
    with brownie.reverts("voter already voted"):
        gov_hub.castVote(1, False)


def test_cancel_proposal_failed_with_invalid_proposal_id(gov_hub):
    with brownie.reverts("state: invalid proposal id"):
        gov_hub.cancel(1)


def test_cancel_proposal_failed_which_is_finished(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1 + gov_hub.votingPeriod())
    with brownie.reverts("cannot cancel finished proposal"):
        gov_hub.cancel(1)


def test_cancel_proposal_failed_with_sender_is_not_proposer(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    with brownie.reverts("only cancel by proposer"):
        gov_hub.cancel(1, {'from': accounts[3]})


def test_cancel_success(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    proposal_id = gov_hub.latestProposalIds(accounts[0])
    tx = gov_hub.cancel(proposal_id)
    expect_event(tx, "ProposalCanceled", {'id': proposal_id})
    assert gov_hub.getState(proposal_id) == 2


def test_defeated_proposal(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    proposal_id = gov_hub.latestProposalIds(accounts[0])
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(proposal_id, False, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    assert gov_hub.getState(proposal_id) == 3


def test_execute_proposal_failed_with_invalid_proposal_id(gov_hub):
    with brownie.reverts("state: invalid proposal id"):
        gov_hub.execute(1)


def test_execute_proposal_failed_with_is_not_in_success_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")

    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)
    chain.mine(1)
    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)
    chain.mine(gov_hub.votingPeriod())
    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)


def test_execute_proposal_failed_with_is_defeated_state_with_members_voted(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    gov_hub.castVote(1, True)
    chain.mine(gov_hub.votingPeriod())
    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)


def test_execute_proposal_failed_with_execute_exception(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(1, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    with brownie.reverts("Transaction execution reverted."):
        gov_hub.execute(1)


def test_execute_proposal_success(gov_hub):
    current_proposalMaxOperations = gov_hub.proposalMaxOperations()
    new_value = current_proposalMaxOperations + 1
    padding_value = padding_left(Web3.toHex(new_value), 64)
    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode_abi(['string', 'bytes'], ['proposalMaxOperations', Web3.toBytes(hexstr=padding_value)]),
        "update param"
    )
    assert gov_hub.proposalMaxOperations() == new_value


def test_get_proposal_state_failed_with_invalid_proposal_id(gov_hub):
    with brownie.reverts("state: invalid proposal id"):
        gov_hub.getState(0)


def test_get_canceled_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    gov_hub.cancel(1)
    assert gov_hub.getState(1) == 2


def test_get_pending_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    assert gov_hub.getState(1) == 0


def test_get_active_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(2)
    assert gov_hub.getState(1) == 1


def test_get_defeated_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(2 + gov_hub.votingPeriod())
    assert gov_hub.getState(1) == 3


def test_get_success_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(1, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    assert gov_hub.getState(1) == 4


def test_get_executed_proposal_state(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    chain.mine(1)
    for member in gov_hub.getMembers():
        gov_hub.castVote(1, True, {'from': member})
    chain.mine(gov_hub.votingPeriod())
    with brownie.reverts():
        gov_hub.execute(1)
    assert gov_hub.getState(1) == 4


def __add_member(c, member_address):
    execute_proposal(
        c.address,
        0,
        "addMember(address)",
        encode_abi(['address'], [member_address]),
        "add new member"
    )