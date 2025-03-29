import pytest
from web3 import Web3, constants
import brownie
from brownie import *
from eth_abi import encode
from .utils import expect_event, padding_left, expect_event_not_emitted, encode_args_with_signature, \
    update_system_contract_address
from .common import execute_proposal

origin_members = ["0x9fB29AAc15b9A4B7F17c3385939b007540f4d791", "0x96C42C56fdb78294F96B0cFa33c92bed7D75F96a"]


@pytest.fixture(scope="module", autouse=True)
def set_up():
    pass


def fake_gov():
    update_system_contract_address(GovHubMock[0], gov_hub=accounts[0])


def test_receive_money(gov_hub):
    tx = accounts[0].transfer(gov_hub.address, 1)
    expect_event(tx, 'receiveDeposit', {'from': accounts[0], 'amount': 1})


def test_receive_money_with_zero_value(gov_hub):
    tx = accounts[0].transfer(gov_hub.address, 0)
    expect_event_not_emitted(tx, 'receiveDeposit')


def test_update_param_failed_with_address_which_is_not_gov(gov_hub):
    with brownie.reverts("the msg sender must be governance contract"):
        gov_hub.updateParam("proposalMaxOperations",
                            "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_failed_with_unknown_key(gov_hub):
    fake_gov()
    with brownie.reverts("UnsupportedGovParam: jkxjfi"):
        gov_hub.updateParam("jkxjfi", "0x0000000000000000000000000000000000000000000000000000000000000001")


def test_update_param_failed_about_key_proposalMaxOperations_with_invalid_length(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['proposalMaxOperations'])
    with brownie.reverts(f"{error_msg}"):
        gov_hub.updateParam("proposalMaxOperations", "0x00000000000000000000000000000000000001")


def test_update_param_failed_about_key_proposalMaxOperations_out_of_range(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["proposalMaxOperations", 0, 1, Web3.to_int(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"{error_msg}"):
        gov_hub.updateParam("proposalMaxOperations",
                            "0x0000000000000000000000000000000000000000000000000000000000000000")


def test_update_param_success_about_key_proposalMaxOperations(gov_hub):
    fake_gov()
    tx = gov_hub.updateParam("proposalMaxOperations",
                             "0x0000000000000000000000000000000000000000000000000000000000000001")
    expect_event(tx, "paramChange", {
        "key": "proposalMaxOperations",
        "value": "0x0000000000000000000000000000000000000000000000000000000000000001"
    })
    assert gov_hub.proposalMaxOperations() == 1


def test_update_param_failed_about_key_votingPeriod_with_invalid_length(gov_hub):
    fake_gov()
    error_msg = encode_args_with_signature('MismatchParamLength(string)', ['votingPeriod'])
    with brownie.reverts(f"{error_msg}"):
        gov_hub.updateParam("votingPeriod", "0x00000000000000000000000000000000000001")


def test_update_param_failed_about_key_votingPeriod_out_of_range(gov_hub):
    fake_gov()
    value = "0x0000000000000000000000000000000000000000000000000000000000007079"
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["votingPeriod", Web3.to_int(hexstr=value), 28800, Web3.to_int(hexstr=constants.MAX_INT)]
    )
    with brownie.reverts(f"{error_msg}"):
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
        [encode(['address'], [accounts[6].address])],
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
        [encode(['address'], [accounts[2].address])],
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
        [encode(['address'], [accounts[2].address])],
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
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(new_value), 64))

    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['proposalMaxOperations', padding_value]),
        "update parameter"
    )
    assert gov_hub.proposalMaxOperations() == new_value


def test_update_param_voting_period_through_propose(gov_hub):
    new_value = 28800
    padding_value = padding_left(Web3.to_hex(new_value), 64)
    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['votingPeriod', Web3.to_bytes(hexstr=padding_value)]),
        "update voting period"
    )
    assert gov_hub.votingPeriod() == 28800


def test_cast_vote_failed_with_address_which_is_not_member(gov_hub):
    gov_hub.propose([gov_hub.address], [1], ["123"], ["0x"], "test propose one")
    with brownie.reverts("only member is allowed to call the method"):
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
    with brownie.reverts("can only be executed when yes from majority of members"):
        gov_hub.execute(1)
    chain.mine(gov_hub.votingPeriod())
    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)


@pytest.mark.parametrize("is_completed_early", [True, False])
@pytest.mark.parametrize("vote_count", [
    [2, 1, 3], [3, 0, 3], [3, 0, 4],
    [4, 3, 7], [4, 0, 7], [4, 2, 7]
])
def test_vote_early_completion_success(gov_hub, pledge_agent, vote_count, is_completed_early):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:vote_count[2]])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    start_height = chain.height + 1
    chain.mine(1)
    assert gov_hub.getMembers() == accounts[:vote_count[2]]
    for member in gov_hub.getMembers()[:vote_count[0]]:
        gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[0:vote_count[1]]:
        gov_hub.castVote(1, False, {'from': member})
    if is_completed_early is False:
        chain.mine(gov_hub.votingPeriod() + 10)
    else:
        chain.mine(3)
    assert gov_hub.proposals(1) == [1, accounts[0], start_height, start_height + gov_hub.votingPeriod(), vote_count[0],
                                    vote_count[1], vote_count[2], False, False]
    gov_hub.execute(1)
    assert pledge_agent.btcFactor() == 0


@pytest.mark.parametrize("is_completed_early", [True, False])
@pytest.mark.parametrize("vote_count", [0, 1, 2])
def test_vote_early_completion_with_two_voters(gov_hub, pledge_agent, vote_count, is_completed_early):
    assert pledge_agent.btcFactor() == 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine()
    for member in gov_hub.getMembers()[:vote_count]:
        gov_hub.castVote(1, True, {'from': member})
    error_msg = 'can only be executed when yes from majority of members'
    if is_completed_early is False:
        chain.mine(gov_hub.votingPeriod() + 2)
        error_msg = 'proposal can only be executed if it is succeeded'
    if vote_count > 1:
        gov_hub.execute(1)
        assert pledge_agent.btcFactor() == 0
    else:
        with brownie.reverts(error_msg):
            gov_hub.execute(1)


@pytest.mark.parametrize("execute_early", [True, False])
def test_vote_not_completed(gov_hub, pledge_agent, execute_early):
    assert pledge_agent.btcFactor() == 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine()
    for member in gov_hub.getMembers()[:1]:
        gov_hub.castVote(1, True, {'from': member})
    error_msg = 'can only be executed when yes from majority of members'
    if execute_early is False:
        chain.mine(gov_hub.votingPeriod() * 2)
        error_msg = 'proposal can only be executed if it is succeeded'
    with brownie.reverts(error_msg):
        gov_hub.execute(1)
    assert pledge_agent.btcFactor() == 2


def test_governance_mid_change_participants(gov_hub, pledge_agent):
    assert pledge_agent.btcFactor() == 2
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine()
    gov_hub.resetMembers(accounts[:4])
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    gov_hub.execute(1)
    assert pledge_agent.btcFactor() == 0


@pytest.mark.parametrize("execute", [True, False])
def test_execute_multiple_times(gov_hub, pledge_agent, execute):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[:1]:
        gov_hub.castVote(1, False, {'from': member})
    if execute is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    gov_hub.execute(1)
    with brownie.reverts('proposal can only be executed if it is succeeded'):
        gov_hub.execute(1)
    assert pledge_agent.btcFactor() == 0
    chain.mine(gov_hub.votingPeriod() * 2)
    with brownie.reverts('proposal can only be executed if it is succeeded'):
        gov_hub.execute(1)


def test_cancel_proposal_multiple_times(gov_hub, pledge_agent):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[:1]:
        gov_hub.castVote(1, False, {'from': member})
    gov_hub.cancel(1)
    with brownie.reverts('cannot cancel finished proposal'):
        gov_hub.cancel(1)


@pytest.mark.parametrize("is_pre_exec", [True, False])
def test_cancel_proposal_after_execution(gov_hub, pledge_agent, is_pre_exec):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[:1]:
        gov_hub.castVote(1, False, {'from': member})
    if is_pre_exec is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    gov_hub.execute(1)
    with brownie.reverts('cannot cancel finished proposal'):
        gov_hub.cancel(1)


@pytest.mark.parametrize("is_pre_exec", [True, False])
def test_execute_early_then_continue_voting(gov_hub, pledge_agent, is_pre_exec):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:5])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:3]:
        gov_hub.castVote(1, True, {'from': member})
    if is_pre_exec is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    gov_hub.execute(1)
    with brownie.reverts('voting is closed'):
        gov_hub.castVote(1, True, {'from': accounts[4]})


@pytest.mark.parametrize("is_pre_exec", [True, False])
def test_execute_early_then_propose(gov_hub, pledge_agent, is_pre_exec):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:5])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:3]:
        gov_hub.castVote(1, True, {'from': member})
    if is_pre_exec is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    gov_hub.execute(1)
    assert pledge_agent.btcFactor() == 0
    pledge_agent.setBtcFactor(20)
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:3]:
        gov_hub.castVote(2, True, {'from': member})
    if is_pre_exec is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    gov_hub.execute(2)
    assert pledge_agent.btcFactor() == 0


@pytest.mark.parametrize("is_pre_exec", [True, False])
def test_execute_proposal_after_cancellation(gov_hub, pledge_agent, is_pre_exec):
    assert pledge_agent.btcFactor() == 2
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[:1]:
        gov_hub.castVote(1, False, {'from': member})
    gov_hub.cancel(1)
    if is_pre_exec is False:
        chain.mine(gov_hub.votingPeriod() * 2)
    with brownie.reverts("proposal can only be executed if it is succeeded"):
        gov_hub.execute(1)


def test_duplicate_voting(gov_hub, pledge_agent):
    gov_hub.resetMembers(accounts[:5])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
        with brownie.reverts("voter already voted"):
            gov_hub.castVote(1, True, {'from': member})
    reversed_arr = list(reversed(gov_hub.getMembers()))
    for member in reversed_arr[:2]:
        gov_hub.castVote(1, False, {'from': member})
        with brownie.reverts("voter already voted"):
            gov_hub.castVote(1, False, {'from': member})


def test_cannot_propose_new_without_executing_existing_proposal(gov_hub, pledge_agent):
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    with brownie.reverts("one live proposal per proposer, found an already active proposal"):
        gov_hub.propose(
            [pledge_agent.address],
            [0],
            ["updateParam(string,bytes)"],
            [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
            ['pledgeAgent clearDeprecatedMembers']
        )


def test_voting_allowed_after_majority_reached(gov_hub, pledge_agent):
    gov_hub.resetMembers(accounts[:5])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:3]:
        gov_hub.castVote(1, True, {'from': member})
    gov_hub.castVote(1, False, {'from': gov_hub.getMembers()[-1]})
    gov_hub.castVote(1, False, {'from': gov_hub.getMembers()[-2]})
    gov_hub.execute(1)


def test_only_members_can_execute(gov_hub, pledge_agent):
    gov_hub.resetMembers(accounts[:3])
    padding_value = Web3.to_bytes(hexstr=padding_left(Web3.to_hex(10), 64))
    gov_hub.propose(
        [pledge_agent.address],
        [0],
        ["updateParam(string,bytes)"],
        [encode(['string', 'bytes'], ['clearDeprecatedMembers', padding_value])],
        ['pledgeAgent clearDeprecatedMembers']
    )
    chain.mine(1)
    for member in gov_hub.getMembers()[:2]:
        gov_hub.castVote(1, True, {'from': member})
    with brownie.reverts("only member is allowed to call the method"):
        gov_hub.castVote(1, True, {'from': accounts[5]})
    with brownie.reverts("proposal can only be executed by members"):
        gov_hub.execute(1, {'from': accounts[5]})


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
    padding_value = padding_left(Web3.to_hex(new_value), 64)
    execute_proposal(
        gov_hub.address, 0,
        "updateParam(string,bytes)",
        encode(['string', 'bytes'], ['proposalMaxOperations', Web3.to_bytes(hexstr=padding_value)]),
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


def test_only_gov_can_execute(gov_hub):
    value = padding_left(Web3.to_hex(100), 64)
    with brownie.reverts(f"the msg sender must be governance contract"):
        gov_hub.updateParam("proposalMaxOperations", value)


@pytest.mark.parametrize("new_proposalMaxOperations", [1, 2, 5000, 6000, 1000000, 10000000])
def test_update_proposal_max_operations_success(gov_hub, new_proposalMaxOperations):
    value = padding_left(Web3.to_hex(new_proposalMaxOperations), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    gov_hub.updateParam("proposalMaxOperations", value)
    assert gov_hub.proposalMaxOperations() == value


def test_proposal_max_operations_zero(gov_hub):
    value = padding_left(Web3.to_hex(0), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(f"OutOfBounds: proposalMaxOperations, 0, 1, {uint256_max}"):
        gov_hub.updateParam("proposalMaxOperations", value)


@pytest.mark.parametrize("votingPeriod", [28800, 28801, 28802, 100000, 800000000])
def test_update_voting_period_success(gov_hub, votingPeriod):
    value = padding_left(Web3.to_hex(votingPeriod), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    gov_hub.updateParam("votingPeriod", value)
    assert gov_hub.votingPeriod() == value


@pytest.mark.parametrize("votingPeriod", [0, 1, 1000, 28800 - 2, 28800 - 1])
def test_voting_period_out_of_range(gov_hub, votingPeriod):
    value = padding_left(Web3.to_hex(votingPeriod), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(f"OutOfBounds: votingPeriod, {votingPeriod}, 28800, {uint256_max}"):
        gov_hub.updateParam("votingPeriod", value)


@pytest.mark.parametrize("executingPeriod", [28800, 28801, 28802, 100000, 800000000])
def test_update_executing_period_success(gov_hub, executingPeriod):
    value = padding_left(Web3.to_hex(executingPeriod), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    gov_hub.updateParam("executingPeriod", value)
    assert gov_hub.executingPeriod() == value


@pytest.mark.parametrize("executingPeriod", [0, 1, 1000, 28800 - 2, 28800 - 1])
def test_executing_period_out_of_range(gov_hub, executingPeriod):
    value = padding_left(Web3.to_hex(executingPeriod), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    uint256_max = 2 ** 256 - 1
    with brownie.reverts(f"OutOfBounds: executingPeriod, {executingPeriod}, 28800, {uint256_max}"):
        gov_hub.updateParam("executingPeriod", value)


def test_invalid_key(gov_hub):
    value = padding_left(Web3.to_hex(100000), 64)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    with brownie.reverts(f"UnsupportedGovParam: key_error"):
        gov_hub.updateParam("key_error", value)


def test_value_length_error(gov_hub):
    value = padding_left(Web3.to_hex(100000), 66)
    update_system_contract_address(gov_hub, gov_hub=accounts[0])
    with brownie.reverts(f"MismatchParamLength: executingPeriod"):
        gov_hub.updateParam("executingPeriod", value)


def __add_member(c, member_address):
    execute_proposal(
        c.address,
        0,
        "addMember(address)",
        encode(['address'], [member_address]),
        "add new member"
    )
