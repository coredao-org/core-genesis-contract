// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./lib/BytesLib.sol";
import "./lib/RLPDecode.sol";
import "./interface/IParamSubscriber.sol";

/// This is the smart contract to manage governance votes
contract GovHub is System, IParamSubscriber {
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.RLPItem;

  uint256 public constant PROPOSAL_MAX_OPERATIONS = 1;
  uint256 public constant VOTING_PERIOD = 201600;
  uint256 public constant EXECUTING_PERIOD = 201600;
  bytes public constant INIT_MEMBERS = hex"f86994548e6acce441866674e04ab84587af2d394034c094bb06d463bc143eecc4a0cfa35e0346d5690fa9f694e2fe60f349c6e1a85caad1d22200c289da40dc1294b198db68258f06e79d415a0998be7f9b38ea722694dd173b85f306128f1b10d7d7219059c28c6d6c09";

  uint256 public proposalMaxOperations;
  uint256 public votingPeriod;

  mapping(address => uint256) public members;
  address[] public memberSet;

  mapping(uint256 => Proposal) public proposals;
  mapping(address => uint256) public latestProposalIds;
  uint256 public proposalCount;

  uint256 public executingPeriod;

  event receiveDeposit(address indexed from, uint256 amount);
  event VoteCast(address voter, uint256 proposalId, bool support);
  event ProposalCreated(
    uint256 id,
    address proposer,
    address[] targets,
    uint256[] values,
    string[] signatures,
    bytes[] calldatas,
    uint256 startBlock,
    uint256 endBlock,
    uint256 totalVotes,
    string description
  );
  event ProposalCanceled(uint256 id);
  event ProposalExecuted(uint256 id);
  event ExecuteTransaction(address indexed target, uint256 value, string signature, bytes data);

  event MemberAdded(address indexed member);
  event MemberDeleted(address indexed member);

  struct Proposal {
    uint256 id;
    address proposer;
    address[] targets;
    uint256[] values;
    string[] signatures;
    bytes[] calldatas;
    uint256 startBlock;
    uint256 endBlock;
    uint256 forVotes;
    uint256 againstVotes;
    uint256 totalVotes;
    bool canceled;
    bool executed;
    mapping(address => Receipt) receipts;
  }

  struct Receipt {
    bool hasVoted;
    bool support;
  }

  enum ProposalState {
    Pending,
    Active,
    Canceled,
    Defeated,
    Succeeded,
    Executed,
    Expired
  }

  modifier onlyMember() {
    require(members[msg.sender] != 0, "only member is allowed to call the method");
    _;
  }

  function init() external onlyNotInit {
    proposalMaxOperations = PROPOSAL_MAX_OPERATIONS;
    votingPeriod = VOTING_PERIOD;
    executingPeriod = EXECUTING_PERIOD;
    RLPDecode.RLPItem[] memory items = INIT_MEMBERS.toRLPItem().toList();
    uint256 itemSize = items.length;
    for (uint256 i = 0; i < itemSize; i++) {
      address addr = items[i].toAddress();
      memberSet.push(addr);
      members[addr] = memberSet.length;
    }
    alreadyInit = true;
  }

  /// Make a new proposal
  /// @param targets List of addresses to interact with
  /// @param values List of values (CORE amount) to send
  /// @param signatures List of signatures
  /// @param calldatas List of calldata
  /// @param description Description of the proposal
  /// @return The proposal id
  function propose(
    address[] memory targets,
    uint256[] memory values,
    string[] memory signatures,
    bytes[] memory calldatas,
    string memory description
  ) public onlyInit onlyMember returns (uint256) {
    require(
      targets.length == values.length && targets.length == signatures.length && targets.length == calldatas.length,
      "proposal function information arity mismatch"
    );
    require(targets.length != 0, "must provide actions");
    require(targets.length <= proposalMaxOperations, "too many actions");

    uint256 proposalId = latestProposalIds[msg.sender];
    if (proposalId != 0) {
      ProposalState proposersLatestProposalState = getState(proposalId);
      require(
        proposersLatestProposalState != ProposalState.Active,
        "one live proposal per proposer, found an already active proposal"
      );
      require(
        proposersLatestProposalState != ProposalState.Pending,
        "one live proposal per proposer, found an already pending proposal"
      );
    }

    uint256 startBlock = block.number + 1;
    uint256 endBlock = startBlock + votingPeriod;

    proposalCount++;
    proposalId = proposalCount;
    Proposal storage newProposal = proposals[proposalId];
    newProposal.id = proposalId;
    newProposal.proposer = msg.sender;
    newProposal.targets = targets;
    newProposal.values = values;
    newProposal.signatures = signatures;
    newProposal.calldatas = calldatas;
    newProposal.startBlock = startBlock;
    newProposal.endBlock = endBlock;
    newProposal.forVotes = 0;
    newProposal.againstVotes = 0;
    newProposal.totalVotes = memberSet.length;
    newProposal.canceled = false;
    newProposal.executed = false;

    latestProposalIds[newProposal.proposer] = proposalId;

    emit ProposalCreated(
      proposalId,
      msg.sender,
      targets,
      values,
      signatures,
      calldatas,
      startBlock,
      endBlock,
      memberSet.length,
      description
    );
    return proposalId;
  }

  /// Cast vote on a proposal
  /// @param proposalId The proposal Id
  /// @param support Support or not
  function castVote(uint256 proposalId, bool support) public onlyInit onlyMember {
    require(getState(proposalId) == ProposalState.Active, "voting is closed");
    Proposal storage proposal = proposals[proposalId];
    Receipt storage receipt = proposal.receipts[msg.sender];
    require(!receipt.hasVoted, "voter already voted");
    if (support) {
      proposal.forVotes += 1;
    } else {
      proposal.againstVotes += 1;
    }

    receipt.hasVoted = true;
    receipt.support = support;
    emit VoteCast(msg.sender, proposalId, support);
  }

  /// Cancel the proposal, can only be done by the proposer
  /// @param proposalId The proposal Id
  function cancel(uint256 proposalId) public onlyInit {
    ProposalState state = getState(proposalId);
    require(state == ProposalState.Pending || state == ProposalState.Active, "cannot cancel finished proposal");

    Proposal storage proposal = proposals[proposalId];
    require(msg.sender == proposal.proposer, "only cancel by proposer");

    proposal.canceled = true;
    emit ProposalCanceled(proposalId);
  }

  /// Execute the proposal
  /// @param proposalId The proposal Id
  function execute(uint256 proposalId) public payable onlyInit {
    require(members[msg.sender] != 0, "proposal can only be executed by members");
    Proposal storage proposal = proposals[proposalId];
    ProposalState state = getState(proposalId);
    if (state == ProposalState.Active) {
      require(proposal.forVotes > proposal.againstVotes && proposal.forVotes > proposal.totalVotes / 2, "can only be executed when yes from majority of members");
    } else {
      require(state == ProposalState.Succeeded, "proposal can only be executed if it is succeeded");
    }
    proposal.executed = true;
    uint256 targetSize = proposal.targets.length;
    for (uint256 i = 0; i < targetSize; i++) {
      bytes memory callData;
      if (bytes(proposal.signatures[i]).length == 0) {
        callData = proposal.calldatas[i];
      } else {
        callData = abi.encodePacked(bytes4(keccak256(bytes(proposal.signatures[i]))), proposal.calldatas[i]);
      }

      (bool success, bytes memory returnData) = proposal.targets[i].call{ value: proposal.values[i] }(callData);
      require(success, "Transaction execution reverted.");
      emit ExecuteTransaction(proposal.targets[i], proposal.values[i], proposal.signatures[i], proposal.calldatas[i]);
    }
    emit ProposalExecuted(proposalId);
  }

  /// Check the proposal state
  /// @param proposalId The proposal Id
  /// @return The state of the proposal
  function getState(uint256 proposalId) public view returns (ProposalState) {
    require(proposalCount >= proposalId && proposalId != 0, "state: invalid proposal id");
    Proposal storage proposal = proposals[proposalId];
    if (proposal.executed) {
      return ProposalState.Executed;
    } else if (proposal.canceled) {
      return ProposalState.Canceled;
    } else if (block.number <= proposal.startBlock) {
      return ProposalState.Pending;
    } else if (block.number <= proposal.endBlock) {
      return ProposalState.Active;
    } else if (proposal.forVotes <= proposal.againstVotes || proposal.forVotes <= proposal.totalVotes / 2) {
      return ProposalState.Defeated;
    } else if (block.number > proposal.endBlock + executingPeriod) {
      return ProposalState.Expired;
    } else {
      return ProposalState.Succeeded;
    }
  }

  receive() external payable {
    if (msg.value != 0) {
      emit receiveDeposit(msg.sender, msg.value);
    }
  }

  /// Add a member
  /// @param member The new member address
  function addMember(address member) external onlyInit onlyGov {
    require(members[member] == 0, "member already exists");
    memberSet.push(member);
    members[member] = memberSet.length;
    emit MemberAdded(member);
  }

  /// Remove a member
  /// @param member The address of the member to remove
  function removeMember(address member) external onlyInit onlyGov {
    require(memberSet.length > 5, "at least five members in DAO");
    uint256 index = members[member];
    require(index != 0, "member does not exist");
    if (index != memberSet.length) {
      address addr = memberSet[memberSet.length - 1];
      memberSet[index - 1] = addr;
      members[addr] = index;
    }
    memberSet.pop();
    delete members[member];
    emit MemberDeleted(member);
  }

  /// Get all members
  /// @return List of member addresses
  function getMembers() external view returns (address[] memory) {
    return memberSet;
  }

  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "proposalMaxOperations")) {
      uint256 newProposalMaxOperations = BytesToTypes.bytesToUint256(32, value);
      if (newProposalMaxOperations == 0) {
        revert OutOfBounds(key, newProposalMaxOperations, 1, type(uint256).max);
      }
      proposalMaxOperations = newProposalMaxOperations;
    } else if (Memory.compareStrings(key, "votingPeriod")) {
      uint256 newVotingPeriod = BytesToTypes.bytesToUint256(32, value);
      if (newVotingPeriod < 28800) {
        revert OutOfBounds(key, newVotingPeriod, 28800, type(uint256).max);
      }
      votingPeriod = newVotingPeriod;
    } else if (Memory.compareStrings(key, "executingPeriod")) {
      uint256 newExecutingPeriod = BytesToTypes.bytesToUint256(32, value);
      if (newExecutingPeriod < 28800) {
        revert OutOfBounds(key, newExecutingPeriod, 28800, type(uint256).max);
      }
      executingPeriod = newExecutingPeriod;
    } else {
      revert UnsupportedGovParam(key);
    }
    emit paramChange(key, value);
  }
}
