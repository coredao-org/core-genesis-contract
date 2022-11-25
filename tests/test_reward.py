import time
import random
from typing import Dict, List, Set
from copy import deepcopy, copy
from collections import defaultdict, Counter
from web3 import Web3
from brownie import accounts
from brownie.network.account import Account
from brownie.network.transaction import TransactionReceipt
from .common import turn_round, register_candidate
from .utils import get_tracker


TX_FEE = int(1e4)


class Status:
    REGISTER = 1 << 0
    UNREGISTER = 1 << 2
    VALIDATOR = 1 << 3
    REFUSED = 1 << 4


class Agent:
    def __init__(self, margin):
        self.coin_delegators: Dict[str, dict] = {}  # delegator => {'coin': 100, 'valid': True}
        self.power_delegators: Dict[str, int] = {}  # delegator => 100
        self.status = Status.REGISTER
        self.total_power = 0
        self.total_coin = 0
        self.score = 0
        self.margin = margin

    def delegate_coin(self, address, value):
        if address not in self.coin_delegators:
            self.coin_delegators[address] = {
                "coin": value,
                "valid": True
            }
        else:
            self.coin_delegators[address]['coin'] += value

    def delegate_power(self, delegator, count):
        assert count > 0
        self.power_delegators[delegator] = count

    def copy(self) -> "Agent":
        agent = Agent(self.margin)
        agent.status = self.status
        agent.total_coin = self.total_coin
        agent.total_power = self.total_power
        agent.score = self.score
        agent.coin_delegators = {k: deepcopy(v) for k, v in self.coin_delegators.items()}
        agent.power_delegators = {k: v for k, v in self.power_delegators.items()}
        return agent


class AgentReward:
    def __init__(self, remain_reward, delegators: Set[str] = None):
        self.remain_reward = remain_reward
        if delegators:
            self.delegators = copy(delegators)
        else:
            self.delegators = set()

    def __repr__(self):
        return f"remain_reward: {self.remain_reward}, delegators: {self.delegators}"

    def __str__(self):
        return self.__repr__()

    def sub_remain_reward(self, value):
        assert self.remain_reward >= value
        self.remain_reward -= value

    def add_delegator(self, delegator):
        self.delegators.add(delegator)

    def remove_delegator(self, delegator):
        self.delegators.remove(delegator)

    def is_empty(self):
        return len(self.delegators) == 0


class Validator:
    def __init__(self, operator, consensus, fee, commission):
        self.operator_address = operator
        self.consensus_address = consensus
        self.fee_address = fee
        self.commission = commission
        self.income = 0


class RoundState:
    def __init__(self):
        self.power_score = 1
        self.coin_score = 1


N = 0


class StateMachine:
    def __init__(self, candidate_hub, pledge_agent, validator_set, btc_light_client, slash_indicator, min_init_delegate_value):
        self.candidate_hub = candidate_hub
        self.pledge_agent = pledge_agent
        self.validator_set = validator_set
        self.btc_light_client = btc_light_client
        self.slash_indicator = slash_indicator
        self.min_init_delegate_value = min_init_delegate_value
        self.block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
        self.power_factor = self.pledge_agent.powerFactor()
        self.block_reward = validator_set.blockReward()
        self.candidate_margin = self.candidate_hub.requiredMargin()
        self.unregister_candidate_dues = self.candidate_hub.dues()
        self.misdemeanor_threshold = self.slash_indicator.misdemeanorThreshold()
        self.felony_threshold = self.slash_indicator.felonyThreshold()
        self.felony_deposit = self.slash_indicator.felonyDeposit()

        accounts[-2].transfer(self.validator_set.address, Web3.toWei(100000, 'ether'))

    def setup(self):
        global N
        N += 1
        print(f"Scenario {N}")
        random.seed(time.time_ns())

        """
        delegator address => {agent1: count, agent2: count}
        """
        self.coin_delegators: Dict[str, dict] = {}

        self.agents: Dict[str, Agent] = {}
        self.archive_agents: Dict[str, Agent] = None
        self.trackers = {}
        self.balance_delta = defaultdict(int)
        self.current_validators: [Validator] = []
        self.round_state = RoundState()
        self.delegator_unclaimed_agents_map = defaultdict(set)
        self.miners = []
        self.slash_counter: Dict[str, int] = defaultdict(int)
        self.consensus2operator = {}
        self.agent_reward_records: Dict[str, List[AgentReward]] = defaultdict(list)  # key is agent operator address

        self.candidate_hub.setControlRoundTimeTag(True)
        self.candidate_hub.setRoundTag(7)
        for operator in accounts[-6:-1]:
            self.__add_tracker(operator)
            register_candidate(consensus=operator, fee_address=operator, operator=operator,
                               margin=self.candidate_margin)
            self.__register_candidate(operator)
        turn_round()
        self.__turn_round([], self.pledge_agent.stateMap(self.pledge_agent.roundTag()).dict())
        for consensus in self.validator_set.getValidators():
            validator = self.validator_set.currentValidatorSet(self.validator_set.currentValidatorSetMap(consensus) - 1).dict()
            self.current_validators.append(
                Validator(
                    validator['operateAddress'],
                    validator['consensusAddress'],
                    validator['feeAddress'],
                    validator['commissionThousandths']
                )
            )
            self.consensus2operator[validator['consensusAddress']] = validator['operateAddress']
            print(f"\t{validator['operateAddress']}")

    def initialize(self):
        print(f"{'@' * 47} initialize start {'@' * 47}")
        # choice 10 miners
        miners = random.sample(accounts[1:-1], 10)
        for miner in miners:
            print(f"miner: {miner}")
        self.miners.extend(miners)
        print(f"{'@' * 48} initialize end {'@' * 48}")

    def rule_register_candidate(self):
        operator = random.choice(accounts[:-1])
        agent = self.agents.get(operator)
        if agent and agent.status != Status.UNREGISTER:
            return
        print(f"register candidate {operator}")
        self.__add_tracker(operator)
        register_candidate(consensus=operator, fee_address=operator, operator=operator, margin=self.candidate_margin)
        self.__register_candidate(operator)

    # def rule_unregister_candidate(self):
    #     self.__unregister_candidate()

    def rule_delegate_coin(self):
        candidates = self.candidate_hub.getCanDelegateCandidates()
        if not candidates:
            return
        agent = random.choice(candidates)
        delegator = random.choice(accounts[:-1])
        self.__add_tracker(delegator)
        value = self.min_init_delegate_value

        print(f"[DELEGATE COIN] >>> {delegator} delegate to {agent} {value}")
        tx: TransactionReceipt = self.pledge_agent.delegateCoin(agent, {"value": value, "from": delegator})
        self.__delegate_coin(delegator.address, agent, value)

        self.__parse_event(tx)

    def rule_undelegate_coin(self):
        if not self.coin_delegators:
            return
        delegator = random.choice(list(self.coin_delegators.keys()))
        if not self.coin_delegators[delegator]:
            return
        agent = random.choice(list(self.coin_delegators[delegator].keys()))
        print(f"[UNDELEGATE COIN] >>> delegator = {delegator}, agent = {agent}, coin = {self.coin_delegators[delegator][agent]}")
        tx: TransactionReceipt = self.pledge_agent.undelegateCoin(agent, {'from': delegator})
        self.__parse_event(tx)
        self.__cancel_delegate_coin(delegator, agent)

    def rule_transfer_coin(self):
        if not self.coin_delegators:
            return
        delegator = random.choice(list(self.coin_delegators.keys()))
        if not self.coin_delegators[delegator]:
            return
        source = random.choice(list(self.coin_delegators[delegator].keys()))

        candidates = list(self.candidate_hub.getCanDelegateCandidates())
        if source in candidates:
            candidates.remove(source)
        if not candidates:
            return
        target = random.choice(candidates)

        amount = self.coin_delegators[delegator][source]
        print(f"[TRANSFER COIN] >>> {delegator} transfer from {source} to {target} value {amount}")
        tx: TransactionReceipt = self.pledge_agent.transferCoin(source, target, {'from': delegator})
        self.__parse_event(tx)
        self.__transfer_coin(delegator, source, target, amount)

    def rule_delegate_power(self):
        candidates = list(self.candidate_hub.getCanDelegateCandidates())
        candidates.append("0x0000000000000000000000000000000000001234")
        agent = random.choice(candidates)
        blocks = random.randint(10, 144//4)
        miners_weight = [random.randint(0, 5) for _ in self.miners]
        miners = random.choices(self.miners, weights=miners_weight, k=blocks)
        self.btc_light_client.setMiners(self.candidate_hub.roundTag() - 6, agent, miners)
        self.__delegate_power(agent, miners)
        print(f"[DELEGATE POWER] >>> Agent({agent}) has power({len(miners)}):")
        for miner, count in Counter(miners).items():
            print(f"\t{miner}: {count}")
        self.__log_agents_power_info()

    def rule_refuse_delegate(self):
        candidates = self.candidate_hub.getCanDelegateCandidates()
        if len(candidates) < 2:
            return
        candidate = random.choice(candidates)
        print(f"{candidate} refuse delegate")
        self.candidate_hub.refuseDelegate({'from': candidate})
        self.__refuse_delegate(candidate)

    def rule_accept_delegate(self):
        candidates = self.candidate_hub.getRefusedCandidates()
        if not candidates:
            return
        candidate = random.choice(candidates)
        print(f"{candidate} accept delegate")
        self.candidate_hub.acceptDelegate({'from': candidate})
        self.__accept_delegate(candidate)

    def rule_add_margin(self):
        for operator, agent in self.agents.items():
            if agent.margin < self.candidate_margin:
                add_value = random.randint(1, int((self.candidate_margin - agent.margin) * 2.5))
                print(f"Add margin: {operator} => {add_value}")
                self.candidate_hub.addMargin({
                    'from': operator,
                    'value': add_value
                })
                self.__add_margin(operator, add_value)

    def rule_turn_round(self):
        _round = self.candidate_hub.roundTag()
        self.deposit()
        print(f"{'>' * 46} turn round {_round + 1} start {'<' * 46}")
        valid_candidates = self.candidate_hub.getCanDelegateCandidates()
        tx: TransactionReceipt = turn_round()
        print("events in turn round transaction: --------------")
        self.__parse_event(tx)
        round_state = self.pledge_agent.stateMap(self.pledge_agent.roundTag()).dict()
        print(f"Round State(read from contract): power => {round_state['power']}, coin => {round_state['coin']}")
        self.__log_agents_power_info()
        self.__turn_round(valid_candidates, round_state)
        # update current validators
        self.current_validators.clear()
        print(f"{'-' * 46} current validators {'-' * 46}")
        for consensus in self.validator_set.getValidators():
            validator = self.validator_set.currentValidatorSet(self.validator_set.currentValidatorSetMap(consensus) - 1).dict()
            self.current_validators.append(
                Validator(
                    validator['operateAddress'],
                    validator['consensusAddress'],
                    validator['feeAddress'],
                    validator['commissionThousandths']
                )
            )
            self.consensus2operator[validator['consensusAddress']] = validator['operateAddress']
            print(f"\t{validator['operateAddress']}(commission: {validator['commissionThousandths']})")
        print(f"{'>' * 47} turn round {_round + 1} end {'<' * 47}")

    def teardown(self):
        print(f"{'@' * 51} teardown {'@' * 51}")
        # claim reward
        for delegator in self.delegator_unclaimed_agents_map:
            print(f"claim coin reward: delegator: {delegator}, agents: {self.delegator_unclaimed_agents_map[delegator]}")
            tx: TransactionReceipt = self.pledge_agent.claimReward(list(self.delegator_unclaimed_agents_map[delegator]), {'from': delegator})
            self.__parse_event(tx)
            for agent in self.delegator_unclaimed_agents_map[delegator]:
                self.__collect_coin_reward(agent, delegator)

        # compare balance changed
        for address in self.trackers:
            print(f"check balance: {address} -> {self.balance_delta[address]}")
            assert self.trackers[address].delta() == self.balance_delta[address]

    def teardown_final(self):
        global N
        print(f"complete {N} testcase")

    def slash(self, consensus):
        validator = self.validator_set.getValidatorByConsensus(consensus).dict()
        print(f"Slash {validator['operateAddress']}")
        indicator = self.slash_indicator.indicators(consensus).dict()
        print(f"Indicator info(from contract): {indicator}")
        tx: TransactionReceipt = self.slash_indicator.slash(consensus)
        if "validatorFelony" in tx.events:
            for item in tx.events['validatorFelony']:
                print(f"\tvalidatorFelony >>> {item}")
        if "validatorMisdemeanor" in tx.events:
            for item in tx.events['validatorMisdemeanor']:
                print(f"\tvalidatorMisdemeanor >>> {item}")
        self.__slash(validator)

    def deposit(self):
        consensus_list = list(self.validator_set.getValidators())
        block_order = consensus_list + consensus_list
        random.shuffle(block_order)

        for consensus in block_order:
            tx: TransactionReceipt = self.validator_set.deposit(consensus, {"value": TX_FEE, "from": accounts[-1]})
            print(f"Deposit: {self.consensus2operator[consensus]}")
            print(f"\tEvents: {tx.events}")
            self.__deposit(consensus, TX_FEE)
            if random.randint(1, 3) == 1:
                self.slash(consensus)

    def __turn_round(self, valid_candidates: list, round_state_in_contract):
        # distributeReward
        for validator in self.current_validators:
            incentive_value = validator.income * self.block_reward_incentive_percent // 100
            validator.income -= incentive_value
            if validator.income > 0:
                agent = self.archive_agents[validator.operator_address]
                commission = validator.commission
                if agent.score == 0:
                    commission = 1000
                validator_reward = validator.income * commission // 1000
                delegators_reward = validator.income - validator_reward
                agent_reward_record = AgentReward(delegators_reward)
                self.balance_delta[validator.fee_address] += validator_reward
                print(f"agent[{validator.operator_address}] get {validator_reward}(commission: {commission})")

                if delegators_reward == 0:
                    continue
                print(f"distribute reward: agent({validator.operator_address}), {delegators_reward}")

                total_cancel_delegate_coin = 0
                for delegator, item in agent.coin_delegators.items():
                    if item['valid']:
                        reward = delegators_reward * item['coin'] * self.round_state.power_score // agent.score
                        self.delegator_unclaimed_agents_map[delegator].add(validator.operator_address)
                        self.balance_delta[delegator] += reward
                        print(f"\t[Coin] {delegator}({item['coin']}) + {reward}")
                        _reward, _ = self.pledge_agent.claimReward.call([validator.operator_address], {'from': delegator})
                        print(f"\t\t[Coin] call claim reward: {_reward}")
                        agent_reward_record.add_delegator(delegator)
                        agent_reward_record.sub_remain_reward(reward)
                    else:
                        total_cancel_delegate_coin += item['coin']
                total_cancel_delegate_coin_reward = delegators_reward * total_cancel_delegate_coin * self.round_state.power_score // agent.score
                agent_reward_record.sub_remain_reward(total_cancel_delegate_coin_reward)

                for delegator, power_value in agent.power_delegators.items():
                    self.delegator_unclaimed_agents_map[delegator]
                    reward_each_power = self.power_factor * self.round_state.coin_score // 10000 * delegators_reward // agent.score
                    reward = reward_each_power * power_value
                    self.balance_delta[delegator] += reward
                    print(f"\t[Power] {delegator}(power: {power_value}) + {reward} --- rewardMap: {self.pledge_agent.rewardMap(delegator)}")
                    agent_reward_record.sub_remain_reward(reward)
                validator.income = 0

                self.agent_reward_records[validator.operator_address].append(agent_reward_record)

        # calc round state
        self.round_state.coin_score = self.round_state.power_score = 1

        agent: Agent
        for operator, agent in self.agents.items():
            if operator not in valid_candidates:
                continue
            total_coin = 0
            total_power = sum(agent.power_delegators.values())
            for delegator in agent.coin_delegators:
                total_coin += agent.coin_delegators[delegator]['coin']
            agent.total_coin = total_coin
            agent.total_power = total_power
            self.round_state.coin_score += total_coin
            self.round_state.power_score += total_power

        print(f"round state(local): power => {self.round_state.power_score}, coin => {self.round_state.coin_score}")
        assert self.round_state.power_score == round_state_in_contract['power']
        assert self.round_state.coin_score == round_state_in_contract['coin']

        for operator, agent in self.agents.items():
            if operator not in valid_candidates:
                continue
            agent.score = self.power_factor // 10000 * agent.total_power * self.round_state.coin_score + \
                             agent.total_coin * self.round_state.power_score
            print(f"agent info({operator}): power=>{agent.total_power}, coin=>{agent.total_coin}, score=>{agent.score}")

        self.archive_agents = dict()
        for operator in self.agents:
            self.archive_agents[operator] = self.agents[operator].copy()

        # clear power delegate data
        for agent in self.agents.values():
            agent.total_power = 0
            agent.power_delegators = dict()

        # decrease slash count
        for consensus in self.slash_counter:
            if self.slash_counter[consensus] > 0:
                self.slash_counter[consensus] -= self.felony_threshold // self.slash_indicator.DECREASE_RATE()

    def __delegate_coin(self, delegator, agent, amount, update_balance=True):
        self.agents[agent].delegate_coin(delegator, amount)
        if agent in self.delegator_unclaimed_agents_map[delegator]:
            self.delegator_unclaimed_agents_map[delegator].remove(agent)
        if update_balance:
            self.balance_delta[delegator] -= amount

        if delegator not in self.coin_delegators:
            self.coin_delegators[delegator] = {agent: amount}
        else:
            if agent not in self.coin_delegators[delegator]:
                self.coin_delegators[delegator][agent] = amount
            else:
                self.coin_delegators[delegator][agent] += amount

        self.__collect_coin_reward(agent, delegator)

    def __cancel_delegate_coin(self, delegator: str, agent: str, update_balance=True):
        delegate_info = self.agents[agent].coin_delegators.pop(delegator)
        if agent in self.archive_agents and delegator in self.archive_agents[agent].coin_delegators:
            self.archive_agents[agent].coin_delegators[delegator]['valid'] = False
        if agent in self.delegator_unclaimed_agents_map[delegator]:
            self.delegator_unclaimed_agents_map[delegator].remove(agent)
        if update_balance:
            self.balance_delta[delegator] += delegate_info['coin']

        self.coin_delegators[delegator].pop(agent)
        if not self.coin_delegators[delegator]:
            self.coin_delegators.pop(delegator)

        self.__collect_coin_reward(agent, delegator)

    def __transfer_coin(self, delegator, source, target, amount):
        self.__cancel_delegate_coin(delegator, source, update_balance=False)
        self.__delegate_coin(delegator, target, amount, update_balance=False)

    def __delegate_power(self, agent_address: str, miners: list):
        if agent_address not in self.agents:
            return
        agent = self.agents[agent_address]
        agent.total_power = 0
        agent.power_delegators = dict()
        for miner, count in Counter(miners).items():
            agent.delegate_power(miner, count)
            self.__add_tracker(miner)
        agent.total_power = len(miners)

    def __register_candidate(self, operator):
        if operator in self.agents:
            self.agents[operator].status = Status.REGISTER
        else:
            self.agents[operator] = Agent(self.candidate_margin)
        self.balance_delta[operator] -= self.candidate_margin

    def __unregister_candidate(self, operator):
        agent = self.agents[operator]
        if len(agent.coin_delegators.keys()) > 0 or len(agent.power_delegators.keys()) > 0:
            agent.status = Status.UNREGISTER
        else:
            self.agents.pop(operator)
        self.balance_delta[operator] += agent.margin - self.unregister_candidate_dues

    def __refuse_delegate(self, operator: str):
        agent = self.agents[operator]
        agent.status |= Status.REFUSED

    def __accept_delegate(self, operator: str):
        agent = self.agents[operator]
        agent.status &= ~Status.REFUSED

    def __deposit(self, consensus, tx_fee):
        for validator in self.current_validators:
            if validator.consensus_address == consensus:
                validator.income += tx_fee + self.block_reward
                print(f"\t[LOCAL] {validator.operator_address} income: {validator.income}")
                break

    def __collect_coin_reward(self, agent: str, delegator: str):
        if isinstance(agent, Account):
            agent = agent.address
        if isinstance(delegator, Account):
            delegator = delegator.address
        for agent_reward in self.agent_reward_records[agent]:
            if delegator not in agent_reward.delegators:
                continue
            agent_reward.remove_delegator(delegator)
            if agent_reward.is_empty() and agent_reward.remain_reward > 0:
                self.balance_delta[delegator] += agent_reward.remain_reward
                print(f"\t[Dust] Delegator({delegator}) + {agent_reward.remain_reward} from Agent({agent})")
        self.agent_reward_records[agent] = [item for item in self.agent_reward_records[agent] if not item.is_empty()]

    def __add_tracker(self, address):
        if address not in self.trackers:
            self.trackers[address] = get_tracker(address)

    @staticmethod
    def __parse_event(tx: TransactionReceipt):
        events = ['directTransfer', 'claimedReward', 'roundReward']

        for event_name in events:
            if event_name in tx.events:
                for event in tx.events[event_name]:
                    print(f"\t{event_name} >>> {event}")

    def __log_agents_power_info(self):
        print("current agents power info >>>>>>>>>>>>>>>>")
        for address, agent in self.agents.items():
            print(f"{address} total power is {agent.total_power}")
            print(agent.power_delegators)
        print("<" * 42)

    def __slash(self, _validator: dict):
        consensus = _validator['consensusAddress']
        self.slash_counter[consensus] += 1
        if self.slash_counter[consensus] % self.felony_threshold == 0:
            self.slash_counter[consensus] = 0
            # felony
            income = 0
            for validator in self.current_validators:
                if validator.consensus_address == consensus:
                    income = validator.income
                    validator.income = 0
                    if len(self.current_validators) == 1:
                        return
                    else:
                        self.current_validators.remove(validator)
                        break

            average_distribute = income // len(self.current_validators)
            if average_distribute > 0:
                for validator in self.current_validators:
                    validator.income += average_distribute
                    print(f"\t{validator.operator_address} share felony punish amount {average_distribute}")
            # deduct margin
            self.agents[_validator['operateAddress']].margin -= self.felony_deposit
        elif self.slash_counter[consensus] % self.misdemeanor_threshold == 0:
            # misdemeanor
            income = 0
            for validator in self.current_validators:
                if validator.consensus_address == consensus:
                    income = validator.income
                    validator.income = 0

            rest = len(self.current_validators) - 1
            if rest == 0:
                return
            average_distribute = income // rest
            if average_distribute > 0:
                for validator in self.current_validators:
                    if validator.consensus_address == consensus:
                        continue
                    validator.income += average_distribute
                    print(f"\t{validator.operator_address} share misdemeanor punish amount {average_distribute}")

    def __add_margin(self, operator, add_value):
        self.agents[operator].margin += add_value
        self.balance_delta[operator] -= add_value


def test_stateful(state_machine, candidate_hub, pledge_agent, validator_set, btc_light_client, slash_indicator, min_init_delegate_value):
    state_machine(
        StateMachine,
        candidate_hub,
        pledge_agent,
        validator_set,
        btc_light_client,
        slash_indicator,
        min_init_delegate_value,
        settings={"max_examples": 250, "stateful_step_count": 50}
    )
