import pytest
import brownie
from web3 import Web3
from brownie import accounts
from brownie.network import gas_price
from .utils import expect_event, get_tracker, padding_left, encode_args_with_signature
from .common import register_relayer
from .btc_block_data import btc_block_data


def teardown_module():
    gas_price(False)


@pytest.fixture(scope="module", autouse=True)
def set_up(system_reward, btc_light_client):
    register_relayer()
    # deposit to system reward contract
    accounts[0].transfer(system_reward.address, Web3.toWei(10, 'ether'))
    # set store block header gas price
    global store_block_header_tx_gas_price
    store_block_header_tx_gas_price = btc_light_client.storeBlockGasPrice()
    if store_block_header_tx_gas_price == 0:
        store_block_header_tx_gas_price = btc_light_client.INIT_STORE_BLOCK_GAS_PRICE()
    gas_price(store_block_header_tx_gas_price)


@pytest.fixture(autouse=True)
def isolation():
    pass


@pytest.fixture(scope="function")
def init_gov_address(validator_set, slash_indicator, system_reward, btc_light_client, relay_hub, candidate_hub,
                     gov_hub, pledge_agent, burn, foundation):
    VALIDATOR_CONTRACT_ADDR = validator_set.address
    SLASH_CONTRACT_ADDR = slash_indicator.address
    SYSTEM_REWARD_ADDR = system_reward.address
    LIGHT_CLIENT_ADDR = btc_light_client.address
    RELAYER_HUB_ADDR = relay_hub.address
    CANDIDATE_HUB_ADDR = candidate_hub.address
    GOV_HUB_ADDR = gov_hub.address
    PLEDGE_AGENT_ADDR = pledge_agent.address
    BURN_ADDR = burn.address
    FOUNDATION_ADDR = foundation.address
    btc_light_client.updateContractAddr(
        VALIDATOR_CONTRACT_ADDR,
        SLASH_CONTRACT_ADDR,
        SYSTEM_REWARD_ADDR,
        LIGHT_CLIENT_ADDR,
        RELAYER_HUB_ADDR,
        CANDIDATE_HUB_ADDR,
        accounts[0],
        PLEDGE_AGENT_ADDR,
        BURN_ADDR,
        FOUNDATION_ADDR,
    )


def update_default_block_gasprice(btc_light_client):
    hex_value = padding_left(Web3.toHex(store_block_header_tx_gas_price), 64)
    btc_light_client.updateParam('storeBlockGasPrice', hex_value, {'from': accounts[0]})


def test_store_zero_block(btc_light_client):
    tx = btc_light_client.storeBlockHeader("0x0")
    expect_event(tx, "StoreHeaderFailed", {'returnCode': "10030"})


def test_store_wrong_length_block(btc_light_client):
    tx = btc_light_client.storeBlockHeader(btc_block_data[0][:80])
    expect_event(tx, "StoreHeaderFailed", {"returnCode": "10090"})


def test_store_change_nonce_block(btc_light_client):
    tx = btc_light_client.storeBlockHeader(btc_block_data[0][:80] + '00')
    expect_event(tx, "StoreHeaderFailed", {"returnCode": "10090"})


def test_store_block_success(btc_light_client):
    tx = btc_light_client.storeBlockHeader(btc_block_data[0])
    expect_event(tx, 'StoreHeader', {'height': '717697'})
    tx = btc_light_client.storeBlockHeader(btc_block_data[1])
    expect_event(tx, 'StoreHeader', {'height': '717698'})
    tx = btc_light_client.storeBlockHeader(btc_block_data[2])
    expect_event(tx, 'StoreHeader', {'height': '717699'})

    assert btc_light_client.isHeaderSynced("0x00000000000000000000794d6f4f6ee1c09e69a81469d7456e67be3d724223fb") is True
    assert btc_light_client.getSubmitter("0x00000000000000000000794d6f4f6ee1c09e69a81469d7456e67be3d724223fb") == \
           accounts[0]


def test_get_submitter(btc_light_client):
    assert btc_light_client.getSubmitter("0x00000000000000000000794d6f4f6ee1c09e69a81469d7456e67be3d724223fb") == \
           accounts[0]
    assert btc_light_client.getSubmitter("0x00000000000000000002c1572ed018e38f173f06dd9ab1de99ca4b8e276a65f5") == \
           accounts[0]
    assert btc_light_client.getSubmitter("0x000000000000000000052c338c6d40ee82a9df507dd3597675dcf6fe6a66ea46") == \
           accounts[0]


def test_store_no_previous_block(btc_light_client):
    tx = btc_light_client.storeBlockHeader(btc_block_data[4])
    expect_event(tx, "StoreHeaderFailed", {"returnCode": "10030"})
    tx = btc_light_client.storeBlockHeader(btc_block_data[2000])
    expect_event(tx, "StoreHeaderFailed", {"returnCode": "10030"})


def test_store_duplicate_block(btc_light_client):
    for data in btc_block_data[:3]:
        with brownie.reverts("can't sync duplicated header"):
            btc_light_client.storeBlockHeader(data)


def test_distribute_relayer_reward(btc_light_client, system_reward):
    chain_tip = btc_light_client.getChainTip()
    idx = btc_light_client.getHeight(chain_tip) - btc_light_client.INIT_CHAIN_HEIGHT()
    count_in_round = btc_light_client.countInRound()
    before_reward = btc_light_client.relayerRewardVault(accounts[0])

    while True:
        btc_light_client.storeBlockHeader(btc_block_data[idx])
        idx += 1
        count_in_round = btc_light_client.countInRound()
        if count_in_round == 0:
            # already distributed reward
            break

    after_reward = btc_light_client.relayerRewardVault(accounts[0])
    assert after_reward > before_reward

    if after_reward > brownie.web3.eth.get_balance(system_reward.address):
        after_reward = brownie.web3.eth.get_balance(system_reward.address)

    tracker = get_tracker(accounts[0])
    # claim reward
    tx = btc_light_client.claimRelayerReward(accounts[0], {'from': accounts[1]})
    assert tracker.delta(False) == after_reward
    expect_event(tx, "rewardTo", {"to": accounts[0], "amount": after_reward})


def test_get_prev_hash(btc_light_client):
    prev_hash = "0x0"
    btc_light_client.setBlock('0x1', '0x0', accounts[0].address, accounts[0].address)
    assert btc_light_client.getPrevHash('0x1') == prev_hash


def test_get_candidate(btc_light_client):
    candidate = accounts[1].address
    btc_light_client.setBlock('0x1', '0x0', accounts[0].address, candidate)
    assert btc_light_client.getCandidate('0x1') == candidate


def test_get_reward_address(btc_light_client):
    reward_address = accounts[1].address
    btc_light_client.setBlock('0x1', '0x0', reward_address, accounts[0].address)
    assert btc_light_client.getRewardAddress('0x1') == reward_address


def test_get_score(btc_light_client):
    btc_light_client.setBlock('0x1', '0x0', accounts[1].address, accounts[0].address)
    assert btc_light_client.getScore('0x1') == btc_light_client.MOCK_SCORE()


def test_get_height(btc_light_client):
    btc_light_client.setBlock('0x1', '0x0', accounts[1].address, accounts[0].address)
    assert btc_light_client.getHeight('0x1') == btc_light_client.mockBlockHeight()


def test_get_adjustment_index(btc_light_client):
    btc_light_client.setBlock('0x1', '0x0', accounts[1].address, accounts[0].address)
    assert btc_light_client.getAdjustmentIndex('0x1') == btc_light_client.MOCK_ADJUSTMENT()


def test_get_round_powers(btc_light_client):
    btc_light_client.setMiners(1, accounts[0], accounts[2:3])
    btc_light_client.setMiners(1, accounts[1], accounts[3:5])
    round_powers = btc_light_client.getRoundPowers(1, accounts[:2])
    assert round_powers == [1, 2]


def test_get_round_miners(btc_light_client):
    miners = accounts[1:3]
    btc_light_client.setMiners(1, accounts[0], miners)
    result = btc_light_client.getRoundMiners(1, accounts[0])
    assert len(result) == 2
    for miner in result:
        assert miner in miners


def test_get_round_candidates(btc_light_client):
    candidates = accounts[:2]
    btc_light_client.setCandidates(1, candidates)
    result = btc_light_client.getRoundCandidates(1)
    assert len(result) == 2
    for c in candidates:
        assert c in result


def test_store_btc_block_gasprice_limit_failed(btc_light_client):
    gas_price(store_block_header_tx_gas_price // 2)
    block_data = btc_block_data[-2]
    with brownie.reverts("must use limited gasprice"):
        btc_light_client.storeBlockHeader(block_data)
    gas_price(store_block_header_tx_gas_price)
    tx = btc_light_client.storeBlockHeader(block_data)
    assert btc_light_client.storeBlockGasPrice() == store_block_header_tx_gas_price == tx.gas_price


@pytest.mark.parametrize("gasprice", [1, 10, 101, 1000, 10000,10000.1, 1000000000,10000000000000000000])
def test_update_param_store_block_gasprice_success(btc_light_client, gasprice, init_gov_address):
    gasprice = Web3.toWei(gasprice, 'gwei')
    hex_value = padding_left(Web3.toHex(gasprice), 64)
    tx = btc_light_client.updateParam('storeBlockGasPrice', hex_value, {'from': accounts[0]})
    expect_event(tx, 'paramChange', {'key': 'storeBlockGasPrice', 'value': hex_value})
    assert btc_light_client.storeBlockGasPrice() == gasprice
    update_default_block_gasprice(btc_light_client)


@pytest.mark.parametrize("gasprice", [0.1, 0.99,0.5])
def test_update_param_store_block_gasprice_failed(btc_light_client, gasprice, init_gov_address):
    gasprice = Web3.toWei(gasprice, 'gwei')
    uint256_max = 2 ** 256 - 1
    hex_value = padding_left(Web3.toHex(gasprice), 64)
    error_msg = encode_args_with_signature(
        "OutOfBounds(string,uint256,uint256,uint256)",
        ["storeBlockGasPrice", gasprice, int(1e9), uint256_max]
    )
    with brownie.reverts(f"typed error: {error_msg}"):
        btc_light_client.updateParam('storeBlockGasPrice', hex_value, {'from': accounts[0]})
    update_default_block_gasprice(btc_light_client)
