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
def foundation(accounts):
    c = accounts[0].deploy(Foundation)
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
    foundation
):
    args = [validator_set.address, slash_indicator.address, system_reward.address,
            btc_light_client.address, relay_hub.address, candidate_hub.address,
            gov_hub.address, pledge_agent.address, burn.address, foundation]

    candidate_hub.updateContractAddr(*args)
    btc_light_client.updateContractAddr(*args)
    gov_hub.updateContractAddr(*args)
    relay_hub.updateContractAddr(*args)
    slash_indicator.updateContractAddr(*args)
    system_reward.updateContractAddr(*args)
    validator_set.updateContractAddr(*args)
    pledge_agent.updateContractAddr(*args)
    burn.updateContractAddr(*args)
    foundation.updateContractAddr(*args)

    system_reward.init()
    candidate_hub.setControlRoundTimeTag(True)
    # used for distribute reward
    # accounts[-2].transfer(validator_set.address, Web3.toWei(100000, 'ether'))


@pytest.fixture(scope="module")
def min_init_delegate_value(pledge_agent):
    return pledge_agent.requiredCoinDeposit()


