import pytest
from web3 import Web3
from brownie import *


@pytest.fixture(scope="session", autouse=True)
def is_development() -> bool:
    return network.show_active() == "development" 


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
def deployed_registry(accounts):
    c = accounts[0].deploy(Registry)
    return c


@pytest.fixture(scope="module")
def candidate_hub(accounts, deployed_registry):
    roundInterval = 100
    validatorCount = 0
    c = accounts[0].deploy(CandidateHubMock, deployed_registry, roundInterval, validatorCount) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def btc_light_client(accounts, deployed_registry):
    consensusState = '' 
    chainHeight = 1 
    roundInterval = 1
    c = accounts[0].deploy(BtcLightClientMock, deployed_registry, consensusState, chainHeight, roundInterval) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def gov_hub(accounts, deployed_registry):
    votingPeriod = 1000
    executingPeriod = 1000 
    membersBytes = ''
    c = accounts[0].deploy(GovHubMock, deployed_registry, votingPeriod, executingPeriod, membersBytes) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def relay_hub(accounts, deployed_registry):
    c = accounts[0].deploy(RelayerHubMock, deployed_registry) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def slash_indicator(accounts, deployed_registry):
    chainID = 1
    c = accounts[0].deploy(SlashIndicatorMock, deployed_registry, chainID) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def system_reward(accounts, deployed_registry):
    c = accounts[0].deploy(SystemRewardMock, deployed_registry) 
    c.init()
    return c


@pytest.fixture(scope="module")
def validator_set(accounts, deployed_registry):
    c = accounts[0].deploy(ValidatorSetMock, deployed_registry) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def pledge_agent(accounts, deployed_registry):
    powerBlockFactor = 1
    c = accounts[0].deploy(PledgeAgentMock, deployed_registry, powerBlockFactor) 
    c.init()
    if is_development:
        c.developmentInit()
    return c


@pytest.fixture(scope="module")
def burn(accounts, deployed_registry):
    c = accounts[0].deploy(Burn, deployed_registry) 
    c.init()
    return c


@pytest.fixture(scope="module")
def foundation(accounts, deployed_registry):
    c = accounts[0].deploy(Foundation, deployed_registry) 
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
    deployed_registry
):
    deployed_registry.setAll([burn, 
                              btc_light_client, 
                              slash_indicator, 
                              system_reward, 
                              candidate_hub, 
                              pledge_agent, 
                              validator_set, 
                              relay_hub, 
                              foundation, 
                              gov_hub.address]); 


@pytest.fixture(scope="module")
def min_init_delegate_value(pledge_agent):
    return pledge_agent.requiredCoinDeposit()


