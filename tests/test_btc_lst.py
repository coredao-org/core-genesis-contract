import brownie
import pytest
from web3 import constants
from .common import *
from .utils import *

BLOCK_REWARD = 0
BTC_VALUE = 2000
ONE_ETHER = Web3.to_wei(1, 'ether')
TX_FEE = 100
public_key = "025615000708918f33f8743b2284558ac9d89e7b8d0df0d692ed48859eea73de93"
redeem_public_key = "023821629dad3e7bad594d183f27bfca34511bedb319aec33faea6f71c2c821fe8"
LOCK_SCRIPT = "0xa91454f0594a167b8226a2f4905e70f272fee9f5360387"
LOCK_TIME = 1736956800
BTC_LST_REWARD = 0
FEE = 1
BTC_REWARD = 0
STAKE_ROUND = 3
utxo_fee = 100


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_relayer_register(relay_hub):
    for account in accounts[:3]:
        relay_hub.setRelayerRegister(account.address, True)


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_light_client, btc_stake, stake_hub, core_agent, btc_lst_stake,
                     gov_hub):
    global BLOCK_REWARD, FEE, BTC_REWARD
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LST_STAKE, BTC_LIB, BTC_LST_REWARD, BTC_LIGHT_CLIENT
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    BLOCK_REWARD = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    total_reward = BLOCK_REWARD // 2
    BTC_REWARD = total_reward * (HardCap.BTC_HARD_CAP * Utils.DENOMINATOR // HardCap.SUM_HARD_CAP) // Utils.DENOMINATOR
    BTC_LST_REWARD = BTC_REWARD * btc_lst_stake.percentage() // Utils.DENOMINATOR
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    BTC_LIGHT_CLIENT = btc_light_client
    BTC_LST_STAKE = btc_lst_stake
    BTC_LIB = get_bitcoin_lib()
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    __set_block_time_stamp(150)
    btc_lst_stake.updateParam('add', LOCK_SCRIPT, {'from': gov_hub.address})


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


@pytest.fixture()
def delegate_btc_lst_tx():
    operator = accounts[5]
    lock_script = get_lock_script(LOCK_TIME, public_key)
    btc_tx, tx_id = get_btc_tx(BTC_VALUE, Utils.CHAIN_ID, operator, accounts[0], lock_data=lock_script)
    tx_id_list = [tx_id]
    return lock_script, btc_tx, tx_id_list


def test_delegate_lst_btc_p2sh_script_success(btc_lst_stake, lst_token, set_candidate, stake_hub, btc_agent):
    lock_script = '0xa91454f0594a167b8226a2f4905e70f272fee9f5360387'
    operators, consensuses = set_candidate
    turn_round()
    tx_id = '0x' + reverse_by_bytes('23a4ee8926da03aa9097caccbb9788787946d369b097e3238b0d1bf347b577bb')
    btc_tx = (
        '01000000016f6187d0c4a17fd74bc61f1f16f15a94f13f22f13e0d4d455dabceebe317368e020000006a47304402206d78735d73a7f01e7b7a0d2a2b2a96e9bd9e14baa32f59eb0802701f7a1b05950220539eff3f30dcf7bd98f322c1d8e77406ff63ad64889b22566cc8fefc3b98c8d401210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff03d007'
        '00000000000017a91454f0594a167b8226a2f4905e70f272fee9f5360387'
        '00000000000000001e6a1c5341542b0204589fb29aac15b9a4b7f17c3385939b007540f4d7910111eec3'
        '00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000')

    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[0]})
    expect_event(tx, 'Transfer', {
        'to': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert tracker.delta() == BTC_LST_REWARD * 3


def test_delegate_lst_btc_p2pkh_script_success(btc_lst_stake, lst_token, gov_hub, set_candidate, stake_hub, btc_agent):
    operators, consensuses = set_candidate
    turn_round()
    lock_script = '0x76a914cdf3d02dd323c14bea0bed94962496c80c09334488ac'
    btc_lst_stake.updateParam('add', lock_script, {'from': gov_hub.address})
    tx_id = '0x' + reverse_by_bytes('27f28cedfa18b1cd8cb05e916986c88afbe34d3a211707e35485fd6b89db4379')
    btc_tx = (
        '0100000001bb77b547f31b0d8b23e397b069d34679788897bbccca9790aa03da2689eea423020000006a47304402205eeecc0a79a2016fb59de8752eaeb282af8ce68771ec27c8778c6aef7c71f6710220497e910cf619695ce966c18ab4c0118cc80907d24a8c0c6275701e56ca0337de01210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff03d007'
        '0000000000001976a914cdf3d02dd323c14bea0bed94962496c80c09334488ac'
        '00000000000000001e6a1c5341542b0204589fb29aac15b9a4b7f17c3385939b007540f4d79101cbe3c3'
        '00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000')

    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[0]})
    expect_event(tx, 'Transfer', {
        'to': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == BTC_LST_REWARD * 3


def test_delegate_lst_btc_p2wpkh_script_success(btc_lst_stake, lst_token, gov_hub, set_candidate, stake_hub, btc_agent):
    operators, consensuses = set_candidate
    turn_round()
    lock_script = '0x0014cdf3d02dd323c14bea0bed94962496c80c093344'
    btc_lst_stake.updateParam('add', lock_script, {'from': gov_hub.address})
    tx_id = '0x' + reverse_by_bytes('63e868b4cae7df3045c73ab65f0052d5a5e119ce4dbb452b5720b58938f91131')
    btc_tx = (
        '01000000017943db896bfd8554e30717213a4de3fb8ac88669915eb08ccdb118faed8cf227020000006a47304402200255151b40013b656c752dd85ab6ea27487e8f5f658cb44b6db231609c3b416c02202a4e3682b64a2d0acae87a526968a7330d6e05f71e5190faae4efbc83a86da2701210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff03d00700'
        '0000000000160014cdf3d02dd323c14bea0bed94962496c80c093344'
        '00000000000000001e6a1c5341542b0204589fb29aac15b9a4b7f17c3385939b007540f4d791018bd9c3'
        '00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000')

    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[0]})
    expect_event(tx, 'Transfer', {
        'to': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'delegated', {
        'txid': tx_id,
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    claim_stake_and_relay_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == BTC_LST_REWARD * 3


def test_p2sh_lock_script_with_p2sh_redeem_script(btc_lst_stake, lst_token, set_candidate):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    redeem_script = lock_script
    script_hash, add_type = BTC_LIB.get_script_hash(redeem_script)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert btc_lst_stake.realtimeAmount() == BTC_VALUE
    tx = btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    expect_event(tx, 'Transfer', {
        'from': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'redeemed', {
        'delegator': accounts[0],
        'utxoFee': utxo_fee,
        'pkscript': redeem_script
    })
    __check__redeem_requests(0, {
        'hash': script_hash,
        'addrType': add_type,
        'delegator': accounts[0],
        'amount': BTC_VALUE - utxo_fee,

    })
    redeem_btc_tx, _ = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE - utxo_fee)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.realtimeAmount() == 0


def test_p2sh_lock_script_with_p2wsh_redeem_script(btc_lst_stake):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    # Lock script is P2SH, redeem script is P2WSH
    redeem_script = '0x0014cdf3d02dd323c14bea0bed94962496c80c093344'
    tx = btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script
    })
    redeem_btc_tx = (
        "01000000019f5233e8114429c6ea8f9f956f34aaed8b813c1320e4b2721c2a84f4fded2048010000006a4730440220452a75c567f47f978b49f23ac12be52e3875e88a509b266f90b0198cd41ccd74022055e9f661bd9cbe7f800627c5251eb73547c300af68216a32f0a6c48a739ec2ca01210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732"
        "fffffffff026c070000000000"
        "00160014cdf3d02dd323c14bea0bed94962496c80c093344"
        "bf61b100000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000")
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_p2sh_lock_script_with_p2pkh_redeem_script(btc_lst_stake):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    # Lock script is P2SH, redeem script is P2PKH
    redeem_script = '0x76a914cdf3d02dd323c14bea0bed94962496c80c09334488ac'
    tx = btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script
    })
    redeem_btc_tx = (
        "0100000001737ee9f181e18183daab7df207a105a0d718a07fcd28a1aa8f3208f83cf2203c010000006b483045022100e1894f3f264c71a70da6bebcf219c04297f83ae336464047647da1e11796a076022051ae3b1d93db4a4bc2e8cca0284b46dffbcc1d175ee5beb6f7ed61382ba764e301210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732"
        "fffffffff026c070000000000"
        "001976a914cdf3d02dd323c14bea0bed94962496c80c09334488ac"
        "8f58b100000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000")
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_btc_transaction_amount_exceeds_redeem_amount(btc_lst_stake, lst_token, set_candidate):
    redeem_amount = BTC_VALUE
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(redeem_amount, lock_script)
    tx = btc_lst_stake.undelegate(btc_tx, 0, [], 0)
    assert 'undelegatedOverflow' in tx.events
    assert 'undelegated' in tx.events


def test_undelegate_success_with_zero_utxo_fee(btc_lst_stake, lst_token, set_candidate):
    btc_lst_stake.setUtxoFee(0)
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    tx_id = get_transaction_txid(btc_tx)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE, lock_script)
    assert btc_lst_stake.getRedeemRequestsLength() == 1
    tx = btc_lst_stake.undelegate(btc_tx, 0, [], 0)
    expect_event(tx, 'undelegated', {
        'txid': tx_id,
        'outputIndex': 0,
        'delegator': accounts[0],
        'amount': BTC_VALUE,
        'pkscript': lock_script,
    })
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_failed_undelegate_with_incorrect_redeem_script(btc_lst_stake, lst_token, set_candidate):
    redeem_script = '0xa9143941c1d0eb3cdf633ef9b9c898bf37efe55412cc87'
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    tx = btc_lst_stake.undelegate(btc_tx, 0, [], 0)
    assert 'undelegated' not in tx.events


def test_no_rewards_generated_after_redeem(btc_lst_stake, lst_token, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE, lock_script)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    assert 'claimedReward' not in tx.events


def test_partial_redeem_btc_stake_success(btc_lst_stake, lst_token, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE // 2, lock_script)
    redeem_btc_tx, _ = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE // 2)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    expect_event(tx, 'undelegated', {
        'outputIndex': 0,
        'delegator': accounts[0],
        'amount': BTC_VALUE // 2,
        'pkscript': lock_script,
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == BTC_LST_REWARD * 3 // 2 - FEE
    assert 'claimedReward' in tx.events


@pytest.mark.parametrize("btc_amount", [100, 199, 200, 201])
def test_revert_on_btc_amount_too_small(btc_lst_stake, btc_amount):
    utxo_fee = 100 * 2
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], btc_amount)
    if btc_amount >= utxo_fee:
        tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
        assert 'delegated' in tx.events
    else:

        with brownie.reverts("btc amount is too small"):
            btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_btc_stake_with_zero_amount_fails(btc_lst_stake, lst_token):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], 0)
    with brownie.reverts("staked value is zero"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_stake_failed_on_wrong_chain_id(btc_lst_stake, lst_token):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE, chain_id=1116)
    with brownie.reverts("wrong chain id"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_stake_failed_on_wrong_magic(btc_lst_stake, lst_token, set_candidate):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE, magic='5341542c')
    with brownie.reverts("wrong magic"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_opreturn_length_error_causes_failure(btc_lst_stake, lst_token):
    op_length0 = hex(27).replace('0x', '')
    op_length1 = hex(25).replace('0x', '')
    btc_tx = (
        '01000000016f6187d0c4a17fd74bc61f1f16f15a94f13f22f13e0d4d455dabceebe317368e020000006a47304402206d78735d73a7f01e7b7a0d2a2b2a96e9bd9e14baa32f59eb0802701f7a1b05950220539eff3f30dcf7bd98f322c1d8e77406ff63ad64889b22566cc8fefc3b98c8d401210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff03d007'
        '00000000000017a91454f0594a167b8226a2f4905e70f272fee9f5360387'
        f'0000000000000000{op_length0}6a{op_length1}53410204589fb29aac15b9a4b7f17c3385939b007540f4d791'
        f'11eec300000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000')
    with brownie.reverts("payload length is too small"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})


def test_btc_transaction_without_op_return_fails(btc_lst_stake, lst_token):
    tx_id = 'a73e2fb3d54fda3186a87740c93bd91c20d7b870769bed714c9bfee3441b6470'
    btc_tx = (
        '01000000013111f93889b520572b45bb4dce19e1a5d552005fb63ac74530dfe7cab468e863020000006a47304402205a987d235d97a40a2f4ead5225e4eccf03290eaae4d1333e55675764db653b2c02207a64ac5ffdefc9cc651af9f18aae98b445878895501739318d7b8f313000168b01210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff02d00700000000000017a91454f0594a167b8226a2f4905e70f272fee9f5360387fbcfc3'
        '00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000')
    with brownie.reverts("no opreturn"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})


def test_failed_stake_with_invalid_version(btc_lst_stake, lst_token):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE, version=1)
    with brownie.reverts("unsupported sat+ version in btc staking"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_duplicate_btc_tx_stake(btc_lst_stake, lst_token, set_candidate):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    assert 'delegated' in tx.events
    with brownie.reverts("btc tx is already delegated."):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_revert_due_to_unconfirmed_btc_tx(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_light_client.setCheckResult(False, 0)
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    with brownie.reverts("btc tx isn't confirmed"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_invalid_relay_cannot_be_moved(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[0], BTC_VALUE)
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[4]})


def test_delegator_successfully_handles_relay(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[4], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[4]})
    assert 'delegated' in tx.events


def test_successful_handling_of_legal_relay(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(accounts[4], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[2]})
    assert 'delegated' in tx.events


def test_stake_error_with_address_zero(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __get_lock_scrip_and_lst_btc_tx(constants.ADDRESS_ZERO, BTC_VALUE)
    with brownie.reverts("ERC20: mint to the zero address"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[2]})


def __get_lock_scrip_and_lst_btc_tx(delegator, amount, script_public_key=None, script_type='P2SH', fee=1, version=2,
                                    chain_id=1112, magic='5341542b'):
    hard_tx = "01000000016f6187d0c4a17fd74bc61f1f16f15a94f13f22f13e0d4d455dabceebe317368e020000006a473044022011e1b2f120d4318433b2e41f8d536f33e323d609fad8d0ddcf98de5010382b480220314b1f7c49dfb638572b08ef2b2f4ed7940233ca29d8b2bdd9be3ff06169b7d701210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732"
    fee_hex = hex(fee).replace('x', '')
    version_hex = hex(version).replace('x', '')
    chain_id_hex = hex(chain_id).replace('x', '')
    amount_hex = reverse_by_bytes(hex(amount)[2:]).ljust(6, '0')
    op_return = magic + version_hex + chain_id_hex + str(delegator)[2:].lower() + fee_hex
    if script_public_key is None:
        script_public_key = public_key
    btc_txs = {"025615000708918f33f8743b2284558ac9d89e7b8d0df0d692ed48859eea73de93": {
        'P2SH': {'lock_scrip': '0xa91454f0594a167b8226a2f4905e70f272fee9f5360387',
                 'pay_address': '2MzzLg89yvATGtFJxZJEiYZK88QHYM9hBXQ',
                 'btc_tx': f'{hard_tx}'
                           f'fffffffff03{amount_hex}000000000017a91454f0594a167b8226a2f4905e70f272fee9f5360387'
                           f'00000000000000001e6a1c{op_return}'
                           '11eec2'
                           '00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000',
                 'btc_amount': 2000}}}
    btc_tx = btc_txs[script_public_key][script_type]['btc_tx']
    lock_scrip = btc_txs[script_public_key][script_type]['lock_scrip']
    return btc_tx, lock_scrip


def __get_redeem_requests(index):
    redeem_request = BTC_LST_STAKE.redeemRequests(index)
    return redeem_request


def __check__redeem_requests(redeem_index, result: dict):
    redeem_request = BTC_LST_STAKE.redeemRequests(redeem_index)
    for i in result:
        assert redeem_request[i] == result[i]


def __set_block_time_stamp(timestamp, lock_time1=None, time_type='day'):
    if lock_time1 is None:
        lock_time1 = LOCK_TIME
    # the default timestamp is days
    if time_type == 'day':
        timestamp = timestamp * 86400
        time1 = lock_time1 - timestamp
    else:
        timestamp = timestamp * 2592000
        time1 = lock_time1 - timestamp
    BTC_LIGHT_CLIENT.setCheckResult(True, time1)
