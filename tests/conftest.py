import pytest
from eth_abi import encode
from brownie import *
from web3 import Web3


@pytest.fixture(scope="session", autouse=True)
def is_development() -> bool:
    return network.show_active() == "development"


@pytest.fixture(scope="module", autouse=True)
def shared_setup(module_isolation):
    pass


@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(scope="session")
def library_set_up(accounts):
    accounts[0].deploy(BytesLib)
    accounts[0].deploy(BytesToTypes)
    accounts[0].deploy(Memory)
    accounts[0].deploy(RLPDecode)
    accounts[0].deploy(RLPEncode)
    accounts[0].deploy(SafeMath)


@pytest.fixture(scope="module")
def candidate_hub(accounts):
    c = accounts[0].deploy(CandidateHubMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def btc_light_client(accounts):
    c = accounts[0].deploy(BtcLightClientMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def gov_hub(accounts):
    c = accounts[0].deploy(GovHubMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def relay_hub(accounts):
    c = accounts[0].deploy(RelayerHubMock)
    c.init()
    if is_development:
        c.developmentInit()

    return c


@pytest.fixture(scope="module")
def slash_indicator(accounts):
    c = accounts[0].deploy(SlashIndicatorMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def system_reward(accounts):
    return accounts[0].deploy(SystemRewardMock)


@pytest.fixture(scope="module")
def validator_set(accounts):
    c = accounts[0].deploy(ValidatorSetMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def pledge_agent(accounts):
    accounts[0].deploy(BitcoinHelper)
    accounts[0].deploy(TypedMemView)
    accounts[0].deploy(SafeCast)
    c = accounts[0].deploy(PledgeAgentMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def burn(accounts):
    c = accounts[0].deploy(Burn)
    c.init()
    return c


@pytest.fixture(scope="module")
def core_agent(accounts):
    c = accounts[0].deploy(CoreAgentMock)
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def foundation(accounts):
    c = accounts[0].deploy(Foundation)
    return c


@pytest.fixture(scope="module")
def stake_hub(accounts):
    c = accounts[0].deploy(StakeHubMock)
    return c


@pytest.fixture(scope="module")
def btc_stake(accounts):
    c = accounts[0].deploy(BitcoinStakeMock)
    return c


@pytest.fixture(scope="module")
def btc_agent(accounts):
    c = accounts[0].deploy(BitcoinAgentMock)
    c.init()
    return c


@pytest.fixture(scope="module")
def btc_lst_stake(accounts):
    c = accounts[0].deploy(BitcoinLSTStakeMock)
    return c


@pytest.fixture(scope="module")
def lst_token(accounts):
    c = accounts[0].deploy(BitcoinLSTToken)
    c.init()
    return c


@pytest.fixture(scope="module")
def hash_power_agent(accounts):
    c = accounts[0].deploy(HashPowerAgentMock)
    c.init()
    return c


# test contract
@pytest.fixture(scope="module")
def test_lib_memory(accounts):
    c = accounts[0].deploy(TestLibMemory)
    return c


@pytest.fixture(scope="module", autouse=True)
def set_system_contract_address(
        candidate_hub,
        btc_light_client,
        gov_hub,
        relay_hub,
        slash_indicator,
        system_reward,
        validator_set,
        pledge_agent,
        burn,
        foundation,
        stake_hub,
        btc_stake,
        btc_agent,
        btc_lst_stake,
        core_agent,
        hash_power_agent,
        lst_token
):
    contracts = [
        validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub, gov_hub,
        pledge_agent, burn, foundation, stake_hub, btc_stake, btc_agent, btc_lst_stake, core_agent, hash_power_agent,
        lst_token
    ]
    args = encode(['address'] * len(contracts), [c.address for c in contracts])

    for c in contracts:
        getattr(c, "updateContractAddr")(args)

    candidate_hub.setControlRoundTimeTag(True)
    accounts[-21].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))
    # init after set system contract
    system_reward.init()
    btc_stake.init()
    btc_lst_stake.init()
    stake_hub.init()
    if is_development:
        btc_stake.developmentInit()
        btc_lst_stake.developmentInit()
        stake_hub.developmentInit()


@pytest.fixture(scope="module")
def min_init_delegate_value(pledge_agent):
    return pledge_agent.requiredCoinDeposit()
