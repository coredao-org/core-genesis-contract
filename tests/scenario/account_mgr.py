from brownie import *
import random
from eth_account import Account
from . import constants


class AccountMgr:
    # contract name => address
    __contract_addr_table = {}

    # operator name => address
    __operator_addr_table = {}

    # consensus addr name => address
    __consensus_addr_table = {}

    # fee addr name => address
    __fee_addr_table = {}

    # delegator name => address
    __delegator_addr_table = {}

    # sponsor name => address
    __sponsor_addr_table = {}

    # addr => name
    __addr_to_name_table = {}

    # addr => bool
    __backup_random_addr_table = {}

    __inited = False

    @classmethod
    def __gen_random_addr(cls):
        addr = Account.create(str(random.random())).address
        if cls.__addr_to_name_table.get(addr) is None:
            return addr

        for account, used in cls.__backup_random_addr_table.items():
            if cls.__addr_to_name_table.get(account.address) is not None:
                continue

            if not used:
                cls.__backup_random_addr_table[account.address] = True
                return account.address

        assert False

    @classmethod
    def __add_to_name_table(cls, addr, name):
        if not isinstance(addr, str):
            addr = addr.address

        cls.__addr_to_name_table[addr] = name

    @classmethod
    def init_account_mgr(cls):
        if cls.__inited:
            return

        cls.__inited = True

        ## Divide the 100 addresses in accounts as follows，because these accounts require funding initially
        # accounts[0]~accounts[29] are allocated to the candidate operator
        # accounts[30]~accounts[89] are allocated to the delegator
        # accounts[90]~accounts[94] as backup random addresses
        # accounts[95]~accounts[99] is the sole sponsor address

        # init delegator accounts
        for i in range(constants.DELEGATOR_ADDR_COUNT):
            name = f"U{i}"
            account = accounts[i + constants.DELEGATOR_ADDR_FROM_IDX]
            cls.__delegator_addr_table[name] = account
            cls.__add_to_name_table(account, name)

        # backup random addresses
        for i in range(constants.BACKUP_ADDR_COUNT):
            account = accounts[i + constants.BACKUP_ADDR_FROM_IDX].address
            cls.__backup_random_addr_table[account] = False

        # init sponsors
        for i in range(constants.SPONSOR_ADDR_COUNT):
            name = f"S{i}"
            account = accounts[i + constants.SPONSOR_ADDR_FROM_IDX]
            cls.__sponsor_addr_table[name] = account
            cls.__add_to_name_table(account, name)

        # init contracts
        cls.__contract_addr_table = {
            "ValidatorSet": ValidatorSetMock[0],
            "CandidateHub": CandidateHubMock[0],
            "StakeHub": StakeHubMock[0],
            "CoreAgent": CoreAgentMock[0],
            "HashPowerAgent": HashPowerAgentMock[0],
            "BitcoinAgent": BitcoinAgentMock[0],
            "BitcoinStake": BitcoinStakeMock[0],
            "BitcoinLSTStake": BitcoinLSTStakeMock[0],
            "GovHub": GovHubMock[0],
            "RelayerHub": RelayerHubMock[0],
            "SlashIndicator": SlashIndicatorMock[0],
            "Burn": Burn[0],
            "Foundation": Foundation[0],
            "SystemReward": SystemRewardMock[0]
        }

        for name, addr in cls.__contract_addr_table.items():
            cls.__add_to_name_table(addr, name)

        # init operator addresses, consensus addresses and fee addresses
        for i in range(constants.OPERATOR_ADDR_COUNT):
            operator_name = f"P{i}"
            account = accounts[i + constants.OPERATOR_ADDR_FROM_IDX]
            cls.__operator_addr_table[operator_name] = account
            cls.__add_to_name_table(account, operator_name)

            consensus_addr_name = f"{constants.CONSENSUS_ADDR_NAME_PREFIX}{operator_name}"
            consensus_addr = cls.__gen_random_addr()
            cls.__consensus_addr_table[consensus_addr_name] = consensus_addr
            cls.__add_to_name_table(consensus_addr, consensus_addr_name)

            fee_addr_name = f"{constants.FEE_ADDR_NAME_PREFIX}{operator_name}"
            fee_addr = cls.__gen_random_addr()
            cls.__fee_addr_table[fee_addr_name] = fee_addr
            cls.__add_to_name_table(fee_addr, fee_addr_name)

    @classmethod
    def random_get_sponsor(cls):
        return random.choice(list(cls.__sponsor_addr_table.keys()))

    @classmethod
    def get_contract_addr(cls, name):
        return cls.__contract_addr_table[name]

    @classmethod
    def get_consensus_addr(cls, name):
        consensus_addr_name = f"{constants.CONSENSUS_ADDR_NAME_PREFIX}{name}"
        return cls.__consensus_addr_table[consensus_addr_name]

    @classmethod
    def get_fee_addr(cls, name):
        fee_addr_name = f"{constants.FEE_ADDR_NAME_PREFIX}{name}"
        return cls.__fee_addr_table[fee_addr_name]

    @classmethod
    def get_operator_addr(cls, name):
        return cls.__operator_addr_table[name]

    @classmethod
    def get_delegator_addr(cls, name):
        return cls.__delegator_addr_table[name]

    @classmethod
    def get_sponsor_addr(cls, name):
        return cls.__sponsor_addr_table[name]

    @classmethod
    def get_sponsee_addr(cls, name):
        if cls.__contract_addr_table.get(name) is not None:
            return cls.__contract_addr_table[name]

        if cls.__consensus_addr_table.get(name) is not None:
            return cls.__consensus_addr_table[name]

        if cls.__fee_addr_table.get(name) is not None:
            return cls.__fee_addr_table[name]

        assert False

    @classmethod
    def addr_to_name(cls, addr):
        if not isinstance(addr, str):
            addr = addr.address

        if cls.__addr_to_name_table.get(addr) is None:
            return addr

        return cls.__addr_to_name_table[addr]
