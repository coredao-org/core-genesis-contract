import brownie
import pytest
from web3 import constants
from .common import *
from .delegate import *
from .utils import *

BTC_VALUE = 2000
TX_FEE = 100
public_key = "025615000708918f33f8743b2284558ac9d89e7b8d0df0d692ed48859eea73de93"
LOCK_SCRIPT = "0xa914cdf3d02dd323c14bea0bed94962496c80c09334487"
REDEEM_SCRIPT = "0xa914047b9ba09367c1b213b5ba2184fba3fababcdc0287"
LOCK_TIME = 1736956800
FEE = 0
TOTAL_REWARD = 0
UTXO_FEE = 100
btc_script = get_btc_script()
btc_delegate = BtcStake()
stake_manager = StakeManager()


@pytest.fixture(scope="module", autouse=True)
def deposit_for_reward(validator_set, gov_hub):
    accounts[-10].transfer(validator_set.address, Web3.to_wei(100000, 'ether'))
    accounts[-10].transfer(gov_hub.address, Web3.to_wei(100000, 'ether'))


@pytest.fixture(scope="module", autouse=True)
def set_relayer_register(relay_hub):
    for account in accounts[:3]:
        relay_hub.setRelayerRegister(account.address, True)


@pytest.fixture(scope="module", autouse=True)
def set_block_reward(validator_set, candidate_hub, btc_agent, btc_light_client, btc_stake, stake_hub, core_agent,
                     btc_lst_stake,
                     gov_hub):
    global FEE, BTC_REWARD, TOTAL_REWARD, GOV_HUB
    global BTC_STAKE, STAKE_HUB, CORE_AGENT, BTC_LST_STAKE, BTC_LIGHT_CLIENT
    FEE = FEE * 100
    block_reward = validator_set.blockReward()
    block_reward_incentive_percent = validator_set.blockRewardIncentivePercent()
    total_block_reward = block_reward + TX_FEE
    actual_block_reward = total_block_reward * ((100 - block_reward_incentive_percent) / 100)
    TOTAL_REWARD = actual_block_reward // 2
    BTC_STAKE = btc_stake
    STAKE_HUB = stake_hub
    CORE_AGENT = core_agent
    BTC_LIGHT_CLIENT = btc_light_client
    BTC_LST_STAKE = btc_lst_stake
    candidate_hub.setControlRoundTimeTag(True)
    # The default staking time is 150 days
    set_block_time_stamp(150, LOCK_TIME)
    btc_lst_stake.updateParam('add', LOCK_SCRIPT, {'from': gov_hub.address})
    btc_agent.setPercentage(Utils.DENOMINATOR // 2)
    GOV_HUB = gov_hub


@pytest.fixture()
def set_candidate():
    operators = []
    consensuses = []
    for operator in accounts[5:8]:
        operators.append(operator)
        consensuses.append(register_candidate(operator=operator))
    return operators, consensuses


def test_btc_lst_init_once_only(btc_lst_stake):
    with brownie.reverts("the contract already init"):
        btc_lst_stake.init()


def test_delegate_lst_btc_p2sh_script_success(btc_lst_stake, lst_token, gov_hub, set_candidate, stake_hub, btc_agent):
    lock_script = '0xa91454f0594a167b8226a2f4905e70f272fee9f5360387'
    btc_lst_stake.updateParam('add', lock_script, {'from': gov_hub.address})
    btc_agent.setPercentage(Utils.DENOMINATOR)
    operators, consensuses = set_candidate
    turn_round()
    tx_id = '0x' + reverse_by_bytes('23a4ee8926da03aa9097caccbb9788787946d369b097e3238b0d1bf347b577bb')
    btc_tx = (
        '01000000016f6187d0c4a17fd74bc61f1f16f15a94f13f22f13e0d4d455dabceebe317368e020000006a47304402206d78735d73a7f01e7b7a0d2a2b2a96e9bd9e14baa32f59eb0802701f7a1b05950220539eff3f30dcf7bd98f322c1d8e77406ff63ad64889b22566cc8fefc3b98c8d401210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff03'
        'd00700000000000017a91454f0594a167b8226a2f4905e70f272fee9f5360387'
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
    btc_tx_map = __get_btc_tx_map(tx_id)
    assert btc_tx_map == [BTC_VALUE, 0, 1]
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 3


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
    stake_hub_claim_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


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
    stake_hub_claim_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


def test_delegate_lst_btc_p2wsh_script_success(btc_lst_stake, lst_token, gov_hub, set_candidate, stake_hub, btc_agent):
    operators, consensuses = set_candidate
    turn_round()
    lock_script = '0x00201dc72212f4defaec092ffe941f4d62f64f139910c4bf60d6a306f43762c4de55'
    btc_lst_stake.updateParam('add', lock_script, {'from': gov_hub.address})
    btc_tx = (
        '01000000011ba59f247e7aaba7d7aa3360e718dcdcc43d83e499573dc64f1e4152ac000436020000006a47304402205540f1066ded451bf2775118d005f5920e4c37387f0a781bd7508bc3fd2853790220010c0670459192484b588655c04305ab305b57c816832ad5c3e9e1cffde7243001210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff02d0070000000000002200201dc72212f4defaec092ffe941f4d62f64f139910c4bf60d6a306f43762c4de55'
        '00000000000000001e6a1c5341542b0204589fb29aac15b9a4b7f17c3385939b007540f4d7910100000000')

    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[0]})
    expect_event(tx, 'Transfer', {
        'to': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'delegated', {
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


def test_delegate_lst_btc_p2tr_script_success(btc_lst_stake, lst_token, gov_hub, set_candidate, stake_hub, btc_agent):
    operators, consensuses = set_candidate
    turn_round()
    lock_script = '0x51201dc72212f4defaec092ffe941f4d62f64f139910c4bf60d6a306f43762c4de55'
    btc_lst_stake.updateParam('add', lock_script, {'from': gov_hub.address})
    btc_tx = (
        '01000000011ba59f247e7aaba7d7aa3360e718dcdcc43d83e499573dc64f1e4152ac000436020000006a47304402205540f1066ded451bf2775118d005f5920e4c37387f0a781bd7508bc3fd2853790220010c0670459192484b588655c04305ab305b57c816832ad5c3e9e1cffde7243001210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732'
        'fffffffff02d007000000000000'
        '2251201dc72212f4defaec092ffe941f4d62f64f139910c4bf60d6a306f43762c4de55'
        '00000000000000001e6a1c5341542b0204589fb29aac15b9a4b7f17c3385939b007540f4d7910100000000')

    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[0]})
    expect_event(tx, 'delegated', {
        'delegator': accounts[0],
        'amount': BTC_VALUE
    })
    turn_round()
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


def test_btc_tx_delegate_lock_script_type_mismatch(btc_lst_stake, lst_token, set_candidate):
    turn_round()
    btc_tx, _ = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    btc_lst_script_p2wsh = __create_btc_lst_staking_script(script_type='p2wsh')
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    # p2wsh lock scirp 
    btc_lst_stake.updateParam('add', btc_lst_script_p2wsh)
    with brownie.reverts("staked value is zero"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, btc_lst_script_p2wsh, {"from": accounts[1]})


def test_duplicate_btc_tx_stake(btc_lst_stake, lst_token, set_candidate):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    assert 'delegated' in tx.events
    with brownie.reverts("btc tx is already delegated."):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_revert_due_to_unconfirmed_btc_tx(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_light_client.setCheckResult(False, 0)
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    with brownie.reverts("btc tx isn't confirmed"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_lock_script_not_found_reverts(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    lock_script = '0xa91454f0594a167b8226a2f4905e70f272fee9f5360383'
    with brownie.reverts("Wallet not found"):
        btc_lst_stake.delegate('0x00', 1, [], 0, lock_script, {"from": accounts[1]})


def test_lock_script_wallet_inactive_reverts(btc_lst_stake, set_candidate):
    stake_manager.add_wallet(REDEEM_SCRIPT)
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('remove', LOCK_SCRIPT)
    with brownie.reverts("wallet inactive"):
        btc_lst_stake.delegate('0x00', 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})


def test_op_return_length_error_causes_failure(btc_lst_stake, lst_token):
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


def test_stake_failed_on_wrong_magic(btc_lst_stake, lst_token, set_candidate):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE, magic='5341542c')
    with brownie.reverts("wrong magic"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_stake_failed_on_wrong_chain_id(btc_lst_stake, lst_token):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE, chain_id=1116)
    with brownie.reverts("wrong chain id"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_failed_stake_with_invalid_version(btc_lst_stake, lst_token):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE, version=1)
    with brownie.reverts("unsupported sat+ version in btc staking"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_btc_lst_stake_address_zero(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    operators, consensuses = set_candidate
    turn_round()
    btc_tx, lock_script = __create_btc_lst_delegate(constants.ADDRESS_ZERO, BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[2]})
    assert 'Transfer' not in tx.events
    assert btc_lst_stake.realtimeAmount() == 0
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(constants.ADDRESS_ZERO)
    assert len(tx.events) == 0


def test_btc_stake_with_zero_amount_fails(btc_lst_stake, lst_token):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], 0)
    with brownie.reverts("staked value is zero"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_stake_without_opreturn_success(btc_lst_stake, lst_token):
    btc_tx = (
        "010000000103ad821b58ab29c462009c53bf427fb121446e27f3c2cc2b11c1070dabb5bea0020000006a473044022041b7d5402a979672ec75021f7ad4d337347a63dc3135a175c02e07ed360f7d5d02207491acdc2d521596b1dcadf554038be17a2630e99b35e2d19f73acd1e5469f7b01210270e4215fbe540cab09ac91c9586eba4fc797537859489f4a23d3e22356f1732"
        "fffffffff026c0700000000000017a914cdf3d02dd323c14bea0bed94962496c80c09334487159b9e"
        "00000000001976a914e1c5ba4d1fef0a3c7806603de565929684f9c2b188ac00000000")
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    tx_id = get_transaction_txid(btc_tx)
    __check_btc_lst_tx_map_info(tx_id, {
        'amount': 1900,
        'outputIndex': 0,
        'blockHeight': 1,
    })


def test_address_mismatch_leads_to_zero_stake_value(btc_lst_stake, lst_token):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    # P2WPKH lock script generated from the public key '023821629dad3e7bad594d183f27bfca34511bedb319aec33faea6f71c2c821fe8'
    error_script = '0x0014047b9ba09367c1b213b5ba2184fba3fababcdc02'
    btc_lst_stake.updateParam('add', error_script)
    with brownie.reverts("staked value is zero"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, error_script, {"from": accounts[1]})


def test_invalid_relay_cannot_be_moved(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    with brownie.reverts("only delegator or relayer can submit the BTC transaction"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[4]})


def test_delegator_successfully_handles_relay(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[4], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[4]})
    assert 'delegated' in tx.events


def test_successful_handling_of_legal_relay(btc_lst_stake, lst_token, set_candidate, btc_light_client):
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[4], BTC_VALUE)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[2]})
    assert 'delegated' in tx.events


@pytest.mark.parametrize("btc_amount", [100, 199, 200, 201])
def test_revert_on_btc_amount_too_small(btc_lst_stake, btc_amount):
    utxo_fee = UTXO_FEE * 2
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], btc_amount)
    if btc_amount >= utxo_fee:
        tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
        assert 'delegated' in tx.events
    else:
        with brownie.reverts("btc amount is too small"):
            btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})


def test_multisig_wallet_initiate_staking(btc_lst_stake, stake_hub, set_candidate, lst_token, gov_hub):
    btc_tx_info = {}
    btc_lst_stake.updateParam('add', REDEEM_SCRIPT, {'from': gov_hub.address})
    inputs = [build_input()]
    outputs = [build_output(BTC_VALUE + 1, LOCK_SCRIPT),
               build_btc_lst_stake_opreturn(accounts[0]),
               build_output(BTC_VALUE + 2, LOCK_SCRIPT)]
    generate_btc_transaction_info(btc_tx_info, inputs, outputs)
    btc_tx = build_btc_transaction(btc_tx_info)
    turn_round()
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    assert tx.events['delegated']['amount'] == BTC_VALUE + 2
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE + 2


def test_delegate_includes_existing_rewards(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE, script_type='p2tr')
    btc_lst_stake.updateParam('add', lock_script)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    turn_round(consensuses)
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE // 2)
    btc_lst_reward0, acc_staked_amount = btc_lst_stake.rewardMap(accounts[0])
    assert btc_lst_reward0 == 0
    assert acc_staked_amount == 0
    assert btc_lst_stake.userStakeInfo(accounts[0])[1] == BTC_VALUE
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    # "Staked on all validators"
    assert btc_lst_stake.userStakeInfo(accounts[0])[1] == BTC_VALUE + BTC_VALUE // 2
    btc_lst_reward, acc_staked_amount = btc_lst_stake.rewardMap(accounts[0])
    assert btc_lst_reward == TOTAL_REWARD * 3
    assert btc_lst_stake.realtimeAmount() == BTC_VALUE + BTC_VALUE // 2
    assert acc_staked_amount == BTC_VALUE


def test_multisig_wallet_self_staking_reverts(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, LOCK_SCRIPT, tx_id)
    with brownie.reverts("should not delegate from whitelisted multisig wallets"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round(consensuses)


def test_cross_multisig_wallet_staking(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE, script_type='p2tr')
    btc_lst_stake.updateParam('add', lock_script)
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, lock_script, tx_id)
    with brownie.reverts("should not delegate from whitelisted multisig wallets"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round(consensuses)


def test_multisig_wallet_multi_input_self_staking_reverts(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([random_btc_tx_id()], [tx_id]),
        set_op_return([accounts[0]]))
    with brownie.reverts("should not delegate from whitelisted multisig wallets"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round(consensuses)


def test_staking_with_valid_non_staked_vout_from_same_txid(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, LOCK_SCRIPT, tx_id, vout=1)
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    assert 'delegated' in tx.events
    turn_round(consensuses)


def test_non_staked_utxo_self_staking_by_multisig_wallet(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [BTC_VALUE * 3, LOCK_SCRIPT]))
    btc_lst_stake.delegate(btc_tx, 1, [], 2, LOCK_SCRIPT)
    tx_id = get_transaction_txid(btc_tx)
    turn_round()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 1], [random_btc_tx_id()]),
        set_op_return([accounts[0]]))
    with brownie.reverts("should not delegate from whitelisted multisig wallets"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round(consensuses)


def test_non_staked_utxo_staking_from_multisig_to_another_multisig(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    btc_lst_stake.updateParam('add', lock_script0)
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script1], [BTC_VALUE * 3, lock_script0])
    )
    btc_lst_stake.delegate(btc_tx, 1, [], 2, lock_script0)
    tx_id = get_transaction_txid(btc_tx)
    turn_round()
    btc_tx = btc_delegate.build_btc_lst(set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
                                        set_inputs([tx_id, 1], [random_btc_tx_id()]),
                                        set_op_return([accounts[0]])
                                        )
    with brownie.reverts("should not delegate from whitelisted multisig wallets"):
        btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    turn_round(consensuses)


def test_successful_staking_with_non_staked_utxos_from_different_vouts(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    btc_lst_stake.updateParam('add', lock_script0)
    btc_tx = btc_delegate.build_btc_lst(set_outputs([BTC_VALUE, lock_script1], [BTC_VALUE * 3, lock_script0]))
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 2, lock_script0)
    assert 'delegated' in tx.events
    tx_id = get_transaction_txid(btc_tx)
    turn_round()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([random_btc_tx_id(), 1], [tx_id, 0]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    assert 'Transfer' in tx.events
    turn_round(consensuses)


def test_staking_with_change_vout_after_transaction(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    btc_lst_stake.updateParam('add', lock_script1)
    delegate_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script1], [BTC_VALUE * 3, lock_script0]), [],
        set_op_return([accounts[0]]))
    tx = btc_lst_stake.delegate(delegate_btc_tx0, 1, [], 0, lock_script1, {"from": accounts[1]})
    assert 'delegated' in tx.events
    turn_round()
    delegate_btc_tx1 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([get_transaction_txid(delegate_btc_tx0), 1]),
        set_op_return([accounts[0]]))
    tx = btc_lst_stake.delegate(delegate_btc_tx1, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    assert 'delegated' in tx.events
    turn_round(consensuses)


def test_stake_success_with_multiple_opreturns(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]), [],
        set_op_return([accounts[0]], [accounts[1]])
    )
    tx = btc_lst_stake.delegate(delegate_btc_tx0, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    expect_event(tx, 'delegated', {
        'amount': BTC_VALUE,
    })
    turn_round(consensuses, round_count=2)
    tracker0 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2


def test_stake_success_with_no_validators(btc_lst_stake, stake_hub):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(round_count=3)
    tracker0 = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker0.delta() == 0


def test_delegate_non_zero_valid_stake(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        opreturn=set_op_return([constants.ADDRESS_ZERO])
    )
    tx = btc_lst_stake.delegate(delegate_btc_tx0, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    expect_event(tx, 'delegated', {
        'amount': BTC_VALUE,
    })
    assert 'Transfer' not in tx.events
    turn_round(consensuses, round_count=2)
    tx = stake_hub_claim_reward(constants.ADDRESS_ZERO)
    assert len(tx.events) == 0


def test_multi_output_gas_consumption(btc_lst_stake, stake_hub, set_candidate):
    turn_round()
    output = []
    out_put_count = 168
    gas_limit = 400000000
    for i in range(out_put_count):
        if i < out_put_count - 1:
            output.append([BTC_VALUE, REDEEM_SCRIPT])
        else:
            output.append([BTC_VALUE, LOCK_SCRIPT])
    delegate_btc_tx0 = btc_delegate.build_btc_lst(
        output,
        opreturn=set_op_return([constants.ADDRESS_ZERO])
    )
    tx = btc_lst_stake.delegate(delegate_btc_tx0, 1, [], 0, LOCK_SCRIPT, {"from": accounts[1]})
    assert tx.gas_used < gas_limit


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'redeem', 'transfer'])
def test_paused_state_prevents_operations(btc_lst_stake, lst_token, set_candidate, tests):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - UTXO_FEE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([random_btc_tx_id(), 0])
    )
    btc_lst_stake.updateParam('paused', 1)
    if tests == 'delegate':
        with brownie.reverts("Pausable: paused"):
            delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    elif tests == 'undelegate':
        with brownie.reverts("Pausable: paused"):
            btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    elif tests == 'redeem':
        with brownie.reverts("Pausable: paused"):
            redeem_btc_lst_success(accounts[0], BTC_VALUE, random_btc_lst_lock_script())
    elif tests == 'transfer':
        btc_lst_stake.updateParam('paused', 0)
        delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
        btc_lst_stake.updateParam('paused', 1)
        with brownie.reverts("call lstStake.onTokenTransfer failed."):
            lst_token.transfer(accounts[1], BTC_VALUE, {"from": accounts[0]})


@pytest.mark.parametrize("tests", ['delegate', 'undelegate', 'redeem', 'transfer'])
def test_successful_call_after_unpause(btc_lst_stake, lst_token, set_candidate, tests):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - UTXO_FEE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([random_btc_tx_id(), 0])
    )
    btc_lst_stake.updateParam('paused', 1)
    with brownie.reverts("Pausable: paused"):
        delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_lst_stake.updateParam('paused', 0)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    if tests == 'delegate':
        delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    elif tests == 'undelegate':
        with brownie.reverts("input must from stake wallet."):
            btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    elif tests == 'redeem':
        redeem_btc_lst_success(accounts[0], BTC_VALUE, random_btc_lst_lock_script())
    elif tests == 'transfer':
        transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])


def test_stake_with_inactive_wallet_address(btc_lst_stake, lst_token, set_candidate):
    stake_manager.add_wallet(REDEEM_SCRIPT)
    stake_manager.remove_wallet(REDEEM_SCRIPT)
    with brownie.reverts("wallet inactive"):
        delegate_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)


def test_lst_btc_undelegate_success(btc_lst_stake, lst_token, set_candidate):
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_lst_stake.redeem(BTC_VALUE, LOCK_SCRIPT)
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - UTXO_FEE, LOCK_SCRIPT], [BTC_VALUE * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 0])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    tx_id = get_transaction_txid(redeem_btc_tx)
    expect_event(tx, 'undelegated', {
        'txid': tx_id,
        'outputIndex': 0,
        'amount': BTC_VALUE - UTXO_FEE,
        'pkscript': LOCK_SCRIPT,
    })
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.realtimeAmount() == 0


def test_undelegate_success_with_zero_utxo_fee(btc_lst_stake, lst_token, set_candidate):
    btc_lst_stake.setUtxoFee(0)
    btc_tx, lock_script = __create_btc_lst_delegate(accounts[0], BTC_VALUE)
    tx_id = get_transaction_txid(btc_tx)
    btc_lst_stake.delegate(btc_tx, 1, [], 0, lock_script, {"from": accounts[1]})
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE, lock_script)
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, lock_script, tx_id, 0)
    assert btc_lst_stake.getRedeemRequestsLength() == 1
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    expect_event(tx, 'undelegated', {
        'txid': get_transaction_txid(redeem_btc_tx),
        'outputIndex': 0,
        'amount': BTC_VALUE,
        'pkscript': lock_script,
    })
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_revert_on_undelegate_with_unconfirmed_btc_tx(btc_lst_stake, lst_token, btc_light_client, set_candidate):
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_light_client.setCheckResult(False, 0)
    with brownie.reverts("btc tx not confirmed"):
        btc_lst_stake.undelegate(btc_tx, 0, [], 0)


def test_undelegate_no_redeem_record_in_script(btc_lst_stake, lst_token, btc_light_client, set_candidate):
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, REDEEM_SCRIPT, tx_id)
    tx = btc_lst_stake.undelegate(btc_tx, 0, [], 0)
    tx_id = get_transaction_txid(btc_tx)
    expect_event(tx, 'undelegatedOverflow', {
        'txid': tx_id,
        'outputIndex': 0,
        'expectAmount': 0,
        'actualAmount': BTC_VALUE,
        'pkscript': REDEEM_SCRIPT,
    })


def test_btc_transaction_amount_exceeds_redeem_amount(btc_lst_stake, lst_token, set_candidate):
    redeem_amount = BTC_VALUE
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(redeem_amount, LOCK_SCRIPT)
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE, LOCK_SCRIPT, tx_id, 0)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    expect_event(tx, 'undelegatedOverflow', {
        'txid': get_transaction_txid(redeem_btc_tx),
        'outputIndex': 0,
        'expectAmount': BTC_VALUE - UTXO_FEE,
        'actualAmount': BTC_VALUE,
        'pkscript': LOCK_SCRIPT,
    })
    assert 'undelegated' in tx.events
    turn_round()
    assert lst_token.balanceOf(accounts[0]) == 0


def test_undelegate_with_multiple_redeem_info(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    btc_amount2 = BTC_VALUE * 2
    delegate_btc_lst_success(accounts[0], btc_amount0, LOCK_SCRIPT)
    tx_id = delegate_btc_lst_success(accounts[1], btc_amount2 * 5, LOCK_SCRIPT)
    turn_round()
    scripts = []
    last_index = 0
    for t in ['p2sh', 'p2pkh', 'p2wsh', 'p2wpkh']:
        scripts.append(__create_btc_lst_staking_script(script_type=t))
    for index, s in enumerate(scripts):
        account = accounts[1]
        if index == 0:
            account = accounts[index]
        btc_lst_stake.redeem(btc_amount0 + index, s, {'from': account})
        last_index = index
    redeem_tx_value = btc_amount0 - UTXO_FEE
    redeem_btc_tx = build_btc_lst_tx(accounts[0], redeem_tx_value + 1, scripts[1], tx_id)
    assert btc_lst_stake.getRedeemRequestsLength() == 4
    for index, script in enumerate(scripts):
        redeem_map_key = keccak_hash256(script)
        redeem_index = btc_lst_stake.getRedeemMap(redeem_map_key) - 1
        assert redeem_index == index
        _, _, amount = __get_redeem_requests(redeem_index)
        assert amount == redeem_tx_value + index
    btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0, {'from': accounts[2]})
    redeem_index = 2
    assert btc_lst_stake.getRedeemRequestsLength() == 3
    assert btc_lst_stake.getRedeemMap(keccak_hash256(scripts[-1])) == redeem_index
    script_hash, addr_type = btc_script.get_script_hash(scripts[-1])
    __check_redeem_requests(redeem_index - 1, {
        'hash': script_hash,
        'addrType': addr_type,
        'amount': redeem_tx_value + last_index,
    })


def test_undelegate_with_partial_redeem_amount(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    tx_id = delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(btc_amount0 * 2, REDEEM_SCRIPT)
    redeem_tx_value = btc_amount0 - UTXO_FEE
    redeem_btc_tx = build_btc_lst_tx(accounts[0], redeem_tx_value, REDEEM_SCRIPT, tx_id)
    btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0, {'from': accounts[2]})
    script_hash, addr_type = btc_script.get_script_hash(REDEEM_SCRIPT)
    __check_redeem_requests(0, {
        'hash': script_hash,
        'addrType': addr_type,
        'amount': btc_amount0,
    })


def test_failed_undelegate_with_incorrect_redeem_script(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    tx_id = delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(btc_amount0 * 2, REDEEM_SCRIPT)
    redeem_tx_value = btc_amount0 - FEE
    error_redeem_script = btc_script.k2_btc_lst_script(public_key, 'p2wsh')
    redeem_btc_tx = build_btc_lst_tx(accounts[0], redeem_tx_value, error_redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0, {'from': accounts[2]})
    assert 'undelegatedOverflow' in tx.events


def test_undelegate_with_different_wallet_address(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    tx_id0 = delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(btc_amount0 * 2, REDEEM_SCRIPT)
    redeem_tx_value = btc_amount0 - FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([redeem_tx_value, LOCK_SCRIPT], [redeem_tx_value * 3, LOCK_SCRIPT]),
        set_inputs([tx_id0]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    assert 'undelegated' not in tx.events
    tx_id = get_transaction_txid(redeem_btc_tx0)
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": (BTC_VALUE - FEE) * 3,
        "outputIndex": 2,
        "blockHeight": 1
    })


def test_single_tx_can_settle_only_once(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    tx_id = delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(btc_amount0, REDEEM_SCRIPT)
    redeem_tx_value = btc_amount0 - FEE
    redeem_btc_tx0 = build_btc_lst_tx(accounts[0], redeem_tx_value, REDEEM_SCRIPT, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    assert 'undelegated' in tx.events
    btc_lst_stake.redeem(btc_amount0, REDEEM_SCRIPT, {'from': accounts[0]})
    with brownie.reverts("btc tx is already undelegated."):
        btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})


def test_unsuccessful_writeoff_still_counts(btc_lst_stake, lst_token, set_candidate):
    btc_amount0 = BTC_VALUE
    tx_id = delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    redeem_tx_value = btc_amount0 - FEE
    redeem_btc_tx0 = build_btc_lst_tx(accounts[0], redeem_tx_value, REDEEM_SCRIPT, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    assert 'undelegatedOverflow' in tx.events
    btc_lst_stake.redeem(btc_amount0, REDEEM_SCRIPT, {'from': accounts[0]})
    with brownie.reverts("btc tx is already undelegated."):
        btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})


def test_tx_input_not_from_wallet_address(btc_lst_stake, lst_token, set_candidate, gov_hub):
    btc_amount0 = BTC_VALUE
    delegate_btc_lst_success(accounts[0], btc_amount0 * 2, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    redeem_tx_value = btc_amount0 - FEE
    redeem_btc_tx0 = build_btc_lst_tx(accounts[0], redeem_tx_value, LOCK_SCRIPT)
    with brownie.reverts("input must from stake wallet."):
        btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})


def test_stake_and_undelegate_with_multiple_vouts(btc_lst_stake, lst_token, set_candidate):
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = get_transaction_txid(btc_tx)

    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    undelegate_amount = BTC_VALUE - FEE
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([undelegate_amount, lock_script0], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 2]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    assert 'undelegated' in tx.events
    tx_id = get_transaction_txid(redeem_btc_tx0)
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": 0,
        "outputIndex": 0,
        "blockHeight": 1
    })


def test_outpoint_index_not_equal_to_stake_vout_index(btc_lst_stake, lst_token, set_candidate):
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    undelegate_amount = BTC_VALUE - FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([undelegate_amount, lock_script0], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 0]),
        set_op_return([accounts[0]])
    )
    with brownie.reverts("input must from stake wallet."):
        btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})


def test_undelegate_with_multiple_inputs_success(btc_lst_stake, lst_token, set_candidate):
    lock_script0 = __create_btc_lst_staking_script('p2pkh')
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    undelegate_amount = BTC_VALUE - FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([undelegate_amount, lock_script0], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 0], [tx_id, 2]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    tx_id = get_transaction_txid(redeem_btc_tx0)
    assert 'undelegated' in tx.events
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": 0,
        "outputIndex": 0,
        "blockHeight": 1
    })


def test_input_tx_id_incorrect(btc_lst_stake, lst_token, set_candidate):
    lock_script0 = __create_btc_lst_staking_script('p2wpkh')
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    undelegate_amount = BTC_VALUE - FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([undelegate_amount, lock_script0], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([random_btc_tx_id(), 2], [tx_id, 2]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    tx_id = get_transaction_txid(redeem_btc_tx0)
    expect_event(tx, 'undelegated', {
        'amount': undelegate_amount * 3
    })
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": 0,
        "outputIndex": 0,
        "blockHeight": 1
    })


def test_single_tx_settles_multiple_redeems(btc_lst_stake, lst_token, set_candidate):
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE * 2, REDEEM_SCRIPT)
    redeem_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    undelegate_amount = BTC_VALUE - UTXO_FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 0], [tx_id, 2]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    tx_id = get_transaction_txid(redeem_btc_tx0)
    assert 'undelegated' in tx.events
    expect_event(tx, 'undelegatedOverflow',
                 {
                     'outputIndex': 0,
                     'expectAmount': BTC_VALUE - UTXO_FEE,
                     'actualAmount': BTC_VALUE,
                 })
    expect_event(tx, 'undelegatedOverflow', {
        'outputIndex': 2,
        'expectAmount': BTC_VALUE * 2 - UTXO_FEE,
        'actualAmount': (BTC_VALUE - UTXO_FEE) * 3
    }, idx=1)
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": 0,
        "outputIndex": 0,
        "blockHeight": 1
    })


def test_vout_with_two_wallet_addresses(btc_lst_stake, lst_token, set_candidate, gov_hub):
    btc_lst_stake.updateParam('add', REDEEM_SCRIPT, {'from': gov_hub.address})
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    undelegate_amount = BTC_VALUE - FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id, 2]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    tx_id = get_transaction_txid(redeem_btc_tx0)
    assert 'undelegated' not in tx.events
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": (BTC_VALUE - FEE) * 3,
        "outputIndex": 2,
        "blockHeight": 1
    })


def test_redeem_with_two_inputs_for_two_transactions(btc_lst_stake, lst_token, set_candidate, gov_hub):
    btc_lst_stake.updateParam('add', REDEEM_SCRIPT, {'from': gov_hub.address})
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id0 = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id1 = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE * 2, REDEEM_SCRIPT)
    redeem_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    undelegate_amount = BTC_VALUE - UTXO_FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [undelegate_amount * 3, REDEEM_SCRIPT]),
        set_inputs([tx_id0, 2], [tx_id1, 1]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    expect_event(tx, 'undelegatedOverflow',
                 {
                     'outputIndex': 0,
                     'expectAmount': BTC_VALUE - UTXO_FEE,
                     'actualAmount': BTC_VALUE,
                 })
    expect_event(tx, 'undelegatedOverflow', {
        'outputIndex': 2,
        'expectAmount': BTC_VALUE * 2 - UTXO_FEE,
        'actualAmount': (BTC_VALUE - UTXO_FEE) * 3
    }, idx=1)
    tx_id = get_transaction_txid(redeem_btc_tx0)
    __check_btc_lst_tx_map_info(tx_id, {
        "amount": 0,
        "outputIndex": 0,
        "blockHeight": 1
    })


def test_undelegate_with_change_address_utxo(btc_lst_stake, lst_token, set_candidate, gov_hub):
    btc_lst_stake.updateParam('add', REDEEM_SCRIPT, {'from': gov_hub.address})
    lock_script0 = random_btc_lst_lock_script()
    btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, lock_script0], [BTC_VALUE * 3, LOCK_SCRIPT]),
        [],
        set_op_return([accounts[0]])
    )
    tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.delegate(btc_tx, 1, [], 0, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    undelegate_amount = BTC_VALUE - UTXO_FEE
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [undelegate_amount * 3, LOCK_SCRIPT]),
        set_inputs([tx_id, 2])
    )
    redeem_tx_id = btc_delegate.get_btc_tx_id()
    btc_lst_stake.undelegate(redeem_btc_tx0, 2, [], 0, {'from': accounts[2]})
    __check_btc_lst_tx_map_info(redeem_tx_id, {
        "amount": (BTC_VALUE - UTXO_FEE) * 3,
        "outputIndex": 1,
        "blockHeight": 2
    })
    redeem_btc_lst_success(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT)
    redeem_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT]),
        set_inputs([redeem_tx_id, 1])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx0, 1, [], 0, {'from': accounts[2]})
    expect_event(tx, 'undelegatedOverflow', {
        'outputIndex': 0,
        'expectAmount': BTC_VALUE - UTXO_FEE - BTC_VALUE // 2,
        'actualAmount': BTC_VALUE
    })


def test_undelegate_non_staked_utxo(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    address0 = random_btc_lst_lock_script()
    transfer_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE + 1, address0], [BTC_VALUE + 2, LOCK_SCRIPT])
    )
    tx_id = get_transaction_txid(transfer_btc_tx)
    btc_lst_stake.delegate(transfer_btc_tx, 1, [], 2, LOCK_SCRIPT)
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round()
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [BTC_VALUE * 3, address0]),
        set_inputs([tx_id, 1]),
        set_op_return([accounts[0]]))
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 1, [], 0, {'from': accounts[2]})
    expect_event(tx, 'undelegated', {
        'outputIndex': 0,
        'amount': BTC_VALUE,
        'pkscript': REDEEM_SCRIPT,
    })
    turn_round(consensuses)


def test_undelegate_non_staked_utxo_different_vouts(btc_lst_stake, stake_hub, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    address0 = random_btc_lst_lock_script()
    transfer_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE + 1, LOCK_SCRIPT], [BTC_VALUE + 2, address0]),
        opreturn=set_op_return([constants.ADDRESS_ZERO])
    )
    tx_id = get_transaction_txid(transfer_btc_tx)
    btc_lst_stake.delegate(transfer_btc_tx, 1, [], 2, LOCK_SCRIPT)
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round()
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [BTC_VALUE * 3, address0]),
        set_inputs([tx_id, 0]),
        set_op_return([accounts[0]])
    )
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 1, [], 0, {'from': accounts[2]})
    assert 'undelegated' in tx.events
    turn_round(consensuses)


def test_multiple_inputs_with_non_staked_utxo_undelegate(btc_lst_stake, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    address0 = random_btc_lst_lock_script()
    transfer_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE + 1, address0], [BTC_VALUE + 2, LOCK_SCRIPT])
    )
    tx_id = get_transaction_txid(transfer_btc_tx)
    btc_lst_stake.delegate(transfer_btc_tx, 1, [], 2, LOCK_SCRIPT)
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round()
    redeem_btc_tx = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [BTC_VALUE * 3, address0]),
        set_inputs([random_btc_tx_id(), 1], [tx_id, 1]),
        set_op_return([accounts[0]]))
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 1, [], 0, {'from': accounts[2]})
    assert 'undelegated' in tx.events
    turn_round(consensuses)


def test_handle_tx_out_success(btc_lst_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script0 = random_btc_lst_lock_script()
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - 1, lock_script0], [BTC_VALUE, LOCK_SCRIPT])
    )
    transfer_btc_tx1 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - 1, LOCK_SCRIPT], [BTC_VALUE, lock_script0])
    )
    tx_id0 = get_transaction_txid(transfer_btc_tx0)
    tx_id1 = get_transaction_txid(transfer_btc_tx1)
    btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)
    btc_lst_stake.delegate(transfer_btc_tx1, 2, [], 4, LOCK_SCRIPT)
    __check_btc_lst_tx_map_info(tx_id0, {
        'amount': BTC_VALUE,
        'outputIndex': 1,
        'blockHeight': 1, })
    __check_btc_lst_tx_map_info(tx_id1, {
        'amount': BTC_VALUE - 1,
        'outputIndex': 0,
        'blockHeight': 2,
    })
    turn_round(consensuses)


def test_revert_when_tx_lacks_wallet_script(btc_lst_stake, set_candidate):
    operators, consensuses = set_candidate
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - 1, lock_script1], [BTC_VALUE, lock_script0]))
    get_transaction_txid(transfer_btc_tx0)
    with brownie.reverts("staked value is zero"):
        btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)
    turn_round(consensuses)


def test_revert_when_handle_tx_out_with_non_wallet_script(btc_lst_stake, set_candidate):
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE - 1, lock_script1], [BTC_VALUE, lock_script0]))
    with brownie.reverts("Wallet not found"):
        btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, lock_script0)


def test_transfer_to_two_wallet_addresses(btc_lst_stake, set_candidate):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    lock_script0 = random_btc_lst_lock_script()
    lock_script1 = random_btc_lst_lock_script()
    btc_lst_stake.updateParam('add', lock_script0)
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 2, lock_script0], [BTC_VALUE * 3, lock_script1])
    )
    tx_id = get_transaction_txid(transfer_btc_tx0)
    btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)
    __check_btc_lst_tx_map_info(tx_id, {
        'amount': BTC_VALUE,
        'outputIndex': 0
    })
    with brownie.reverts("btc tx is already delegated."):
        btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, lock_script0)


def test_vout_pair_with_identical_script(btc_lst_stake, set_candidate):
    operators, consensuses = set_candidate
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, LOCK_SCRIPT], [BTC_VALUE * 2, LOCK_SCRIPT], [BTC_VALUE * 3, LOCK_SCRIPT])
    )
    tx_id = get_transaction_txid(transfer_btc_tx0)
    btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)
    __check_btc_lst_tx_map_info(tx_id, {
        'amount': BTC_VALUE * 3,
        'outputIndex': 2
    })
    turn_round(consensuses)


def test_handle_tx_out_unconfirmed_transaction_revert(btc_lst_stake, btc_light_client, set_candidate):
    transfer_btc_tx0 = btc_delegate.build_btc_lst(set_outputs([BTC_VALUE, LOCK_SCRIPT]))
    btc_light_client.setCheckResult(False, 0)
    with brownie.reverts("btc tx isn't confirmed"):
        btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)


@pytest.mark.parametrize("btc_amount", [1, 100, 1200, 13000, 1e8, 10e8])
def test_stake_no_opreturn_different_amount(btc_lst_stake, set_candidate, btc_amount):
    operators, consensuses = set_candidate
    transfer_btc_tx0 = btc_delegate.build_btc_lst(
        set_outputs([BTC_VALUE, REDEEM_SCRIPT], [BTC_VALUE * 2, REDEEM_SCRIPT], [int(btc_amount), LOCK_SCRIPT])
    )
    tx_id = get_transaction_txid(transfer_btc_tx0)
    btc_lst_stake.delegate(transfer_btc_tx0, 1, [], 3, LOCK_SCRIPT)
    __check_btc_lst_tx_map_info(tx_id, {
        'amount': int(btc_amount),
        'outputIndex': 2
    })
    turn_round(consensuses)


def test_distribute_reward_success(btc_lst_stake, btc_agent):
    validators = accounts[:3]
    reward_list = [1000, 20000, 30000]
    stake_amount = 10000
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    round_tag = get_current_round()
    btc_lst_stake.setStakedAmount(stake_amount)
    btc_lst_stake.distributeReward(validators, reward_list)
    sum_reward = sum(reward_list)
    accured_reward = btc_lst_stake.getAccuredRewardPerBTCMap(round_tag)
    round_reward = sum_reward * Utils.BTC_DECIMAL // stake_amount
    assert accured_reward == round_reward
    btc_lst_stake.setRoundTag(round_tag + 1)
    btc_lst_stake.distributeReward(validators, reward_list)
    accured_reward = btc_lst_stake.getAccuredRewardPerBTCMap(round_tag + 1)
    assert accured_reward == round_reward * 2


def test_distribute_reward_with_no_stakes(btc_lst_stake, btc_agent):
    validators = accounts[:3]
    reward_list = [1000, 20000, 30000]
    history_amount = 5000
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    round_tag = get_current_round()
    btc_lst_stake.setAccuredRewardPerBTCMap(6, history_amount)
    btc_lst_stake.distributeReward(validators, reward_list)
    accured_reward = btc_lst_stake.getAccuredRewardPerBTCMap(round_tag)
    assert accured_reward == history_amount


def test_distribute_reward_only_btc_agent_can_call(btc_lst_stake, btc_agent):
    validators = accounts[:3]
    reward_list = [1000, 20000, 30000]
    with brownie.reverts("the msg sender must be bitcoin agent contract"):
        btc_lst_stake.distributeReward(validators, reward_list)


def test_get_btc_lst_stake_amounts_success(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    lst_amount = 6000
    operators, consensuses = set_candidate
    turn_round()
    btc_lst_stake.setRealtimeAmount(lst_amount)
    amounts = btc_lst_stake.getStakeAmounts(operators)
    lst_validator_amount = lst_amount // 3
    assert amounts == [lst_validator_amount, lst_validator_amount, lst_validator_amount]


def test_no_validators_on_stake_amount_query(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    lst_amount = 6000
    turn_round()
    btc_lst_stake.setRealtimeAmount(lst_amount)
    amounts = btc_lst_stake.getStakeAmounts([])
    assert amounts == ()


def test_inactive_validators_query_stake_amount(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    lst_amount = 6000
    operators, consensuses = set_candidate
    operators.append(accounts[0])
    operators.append(accounts[1])
    turn_round()
    btc_lst_stake.setRealtimeAmount(lst_amount)
    amounts = btc_lst_stake.getStakeAmounts(operators)
    lst_validator_amount = lst_amount // 3
    assert amounts == [lst_validator_amount, lst_validator_amount, lst_validator_amount, 0, 0]
    amounts = btc_lst_stake.getStakeAmounts(accounts[:3])
    assert amounts == [0, 0, 0]


def test_set_btc_lst_new_round_success(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    staked_amount = 2200
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    btc_lst_stake.setRealtimeAmount(staked_amount)
    round_tag = 10
    btc_lst_stake.setNewRound([], round_tag)
    assert btc_lst_stake.stakedAmount() == staked_amount
    assert btc_lst_stake.roundTag() == round_tag


def test_set_new_round_only_btc_agent_can_call(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    round_tag = 10
    with brownie.reverts("the msg sender must be bitcoin agent contract"):
        btc_lst_stake.setNewRound([], round_tag)


def test_btc_lst_claim_reward_success(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    return_value = btc_lst_stake.claimReward(accounts[0]).return_value
    claimed_reward = TOTAL_REWARD * 3
    unclaimed_reward = 0
    assert return_value == [claimed_reward, unclaimed_reward, BTC_VALUE]
    assert btc_lst_stake.rewardMap(accounts[0]) == [0, 0]


def test_lst_claim_reward_only_btc_agent_can_call(btc_agent, btc_stake, btc_lst_stake, set_candidate):
    with brownie.reverts("the msg sender must be bitcoin agent contract"):
        btc_lst_stake.claimReward(accounts[0])


@pytest.mark.parametrize('round_count', [0, 1])
@pytest.mark.parametrize("tests", [
    [6000, 'delegate', 'transfer', 'claim'],
    [2000, 'transfer', 'transfer', 'claim'],
    [2000, 'transfer', 'redeem', 'delegate'],
    [6000, 'delegate', 'redeem', 'claim'],
    [4000, 'delegate', 'redeem', 'transfer', 'claim'],
    [2000, 'redeem', 'redeem', 'delegate'],
])
def test_get_btc_lst_acc_stake_amount_success(btc_lst_stake, btc_agent, set_candidate, round_count, tests):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    for i in tests:
        if i == 'delegate':
            delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
        elif i == 'transfer':
            transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
        elif i == 'redeem':
            redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
        elif i == 'claim':
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=round_count)
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_lst_stake.claimReward(accounts[0]).return_value
    expect_stake_amount = tests[0]
    if round_count == 0:
        expect_stake_amount = 0
    assert acc_staked_amount == expect_stake_amount


@pytest.mark.parametrize("tests", [
    [12000, 'delegate', 'transfer', 'claim'],
    [14000, 'delegate', 'delegate', 'transfer'],
    [0, 'transfer', 'transfer', 'redeem'],
    [8000, 'delegate', 'redeem', 'transfer', 'claim'],
    [6000, 'redeem', 'redeem', 'delegate'],
])
def test_multi_round_btc_lst_acc_amount(btc_lst_stake, btc_agent, set_candidate, tests):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE * 2, LOCK_SCRIPT)
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    for i in tests:
        if i == 'delegate':
            delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
        elif i == 'transfer':
            transfer_btc_lst_success(accounts[0], BTC_VALUE, accounts[1])
        elif i == 'redeem':
            redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
        elif i == 'claim':
            stake_hub_claim_reward(accounts[0])
    turn_round(consensuses, round_count=2)
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_lst_stake.claimReward(accounts[0]).return_value
    expect_stake_amount = tests[0]
    assert acc_staked_amount == expect_stake_amount


def test_check_acc_stake_amount_after_btc_lst_redeem(btc_lst_stake, btc_agent, set_candidate):
    operators, consensuses = set_candidate
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    redeem_btc_lst_success(accounts[0], BTC_VALUE, REDEEM_SCRIPT)
    turn_round(consensuses, round_count=3)
    update_system_contract_address(btc_lst_stake, btc_agent=accounts[0])
    reward, reward_unclaimed, acc_staked_amount = btc_lst_stake.claimReward(accounts[0]).return_value
    assert acc_staked_amount == 0


def test_p2sh_lock_script_with_p2sh_redeem_script(btc_lst_stake, lst_token, set_candidate):
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    assert lst_token.balanceOf(accounts[0]) == BTC_VALUE
    assert btc_lst_stake.realtimeAmount() == BTC_VALUE
    redeem_script = __create_btc_lst_staking_script(script_type='p2sh')
    tx = btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    expect_event(tx, 'Transfer', {
        'from': accounts[0],
        'value': BTC_VALUE
    })
    expect_event(tx, 'redeemed', {
        'delegator': accounts[0],
        'utxoFee': UTXO_FEE,
        'amount': BTC_VALUE - UTXO_FEE,
        'pkscript': redeem_script
    })
    script_hash, addr_type = btc_script.get_script_hash(redeem_script)
    __check_redeem_requests(0, {
        'hash': script_hash,
        'addrType': addr_type,
        'amount': BTC_VALUE - UTXO_FEE,

    })
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE - UTXO_FEE, redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.realtimeAmount() == 0


def test_p2tr_lock_script_with_p2wsh_redeem_script(btc_lst_stake, lst_token):
    delegate_lock_script = __create_btc_lst_staking_script(script_type='p2tr')
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('add', delegate_lock_script)
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, delegate_lock_script)
    turn_round()
    # Lock script is P2TR, redeem script is P2WSH
    redeem_script = __create_btc_lst_staking_script(script_type='p2wsh')
    tx = btc_lst_stake.redeem(BTC_VALUE, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script
    })
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE - FEE, redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_p2sh_lock_script_with_p2tr_redeem_script(btc_lst_stake, lst_token):
    delegate_lock_script = __create_btc_lst_staking_script(script_type='p2sh')
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('add', delegate_lock_script)
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, delegate_lock_script)
    turn_round()
    # Lock script is P2SH, redeem script is P2TR
    redeem_script = __create_btc_lst_staking_script(script_type='p2tr')
    tx = redeem_btc_lst_success(accounts[0], BTC_VALUE, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script
    })
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE - FEE, redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.getRedeemRequestsLength() == 0
    assert btc_lst_stake.realtimeAmount() == 0


def test_p2pkh_lock_script_with_p2wpkh_redeem_script(btc_lst_stake, lst_token):
    delegate_script = __create_btc_lst_staking_script(script_type='p2pkh')
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('add', delegate_script)
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, delegate_script)
    turn_round()
    # Lock script is P2PKH, redeem script is P2WPKH
    redeem_script = __create_btc_lst_staking_script(script_type='p2wpkh')
    tx = redeem_btc_lst_success(accounts[0], BTC_VALUE, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script
    })
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE - FEE, redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.getRedeemRequestsLength() == 0


def test_p2wsh_lock_script_with_p2pkh_redeem_script(btc_lst_stake, lst_token):
    delegate_script = __create_btc_lst_staking_script(script_type='p2wsh')
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('add', delegate_script)
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, delegate_script)
    turn_round()
    # Lock script is P2WSH, redeem script is P2PKH
    redeem_script = __create_btc_lst_staking_script(script_type='p2pkh')
    tx = btc_lst_stake.redeem(0, redeem_script)
    expect_event(tx, 'redeemed', {
        'pkscript': redeem_script,
        'amount': BTC_VALUE - UTXO_FEE
    })
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE - UTXO_FEE, redeem_script, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    assert 'undelegated' in tx.events
    assert lst_token.balanceOf(accounts[0]) == 0
    assert btc_lst_stake.getRedeemRequestsLength() == 0


@pytest.mark.parametrize("redeem_script", [
    pytest.param('0xa924047b9ba09367c1b213b5ba2184fba3fababcdc0287', id="p2sh format error"),
    pytest.param('0x76a914047b9ba09367c1b213b5ba2184fba3fababcdc0288aa', id="p2pkh format error"),
    pytest.param('0x0013047b9ba09367c1b213b5ba2184fba3fababcdc02', id="p2wpkh format error"),
    pytest.param('0x00223d1b55fe81a7ca9718d8c909876b74550782a5a748f49b6c2e519de73342cb16', id="p2wsh format error"),
    pytest.param('0x51303d1b55fe81a7ca9718d8c909876b74550782a5a748f49b6c2e519de73342cb16', id="p2tr format error")])
def test_redeem_failed_due_to_invalid_pkscript(btc_lst_stake, lst_token, set_candidate, redeem_script):
    with brownie.reverts("invalid pkscript"):
        btc_lst_stake.redeem(BTC_VALUE, redeem_script)


@pytest.mark.parametrize("redeem_amount", [100, 199, 200, 201])
def test_revert_on_redeem_amount_too_small(btc_lst_stake, lst_token, redeem_amount, set_candidate):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    if redeem_amount < UTXO_FEE * 2:
        with brownie.reverts("The redeem amount is too small"):
            btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
    else:
        tx = btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events


def test_revert_on_redeem_amount_exceeding_stake(btc_lst_stake, lst_token, set_candidate):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    with brownie.reverts("Not enough btc token"):
        btc_lst_stake.redeem(BTC_VALUE + 1, REDEEM_SCRIPT)


def test_default_full_redeem_when_amount_is_zero(btc_lst_stake, lst_token, set_candidate):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    tx = btc_lst_stake.redeem(0, REDEEM_SCRIPT)
    assert tx.events['Transfer']['value'] == BTC_VALUE


def test_multiple_redeems_with_same_pkscript(btc_lst_stake, lst_token, set_candidate):
    delegate_amount = BTC_VALUE * 5
    delegate_btc_lst_success(accounts[0], delegate_amount, LOCK_SCRIPT)
    turn_round()
    assert btc_lst_stake.userStakeInfo(accounts[0])[1] == delegate_amount
    btc_lst_stake.redeem(BTC_VALUE, REDEEM_SCRIPT)
    redeem_amount = BTC_VALUE - UTXO_FEE
    assert btc_lst_stake.getRedeemMap(keccak_hash256(REDEEM_SCRIPT)) == 1
    script_hash, addr_type = btc_script.get_script_hash(REDEEM_SCRIPT)
    __check_redeem_requests(0, {
        'hash': script_hash,
        'addrType': addr_type,
        'amount': redeem_amount
    })
    btc_lst_stake.redeem(BTC_VALUE * 2, REDEEM_SCRIPT)
    __check_redeem_requests(0, {
        'hash': script_hash,
        'addrType': addr_type,
        'amount': redeem_amount + BTC_VALUE * 2 - UTXO_FEE
    })
    realtime_amount = delegate_amount - BTC_VALUE * 3
    assert btc_lst_stake.userStakeInfo(accounts[0])[1] == realtime_amount
    assert btc_lst_stake.userStakeInfo(accounts[0])[2] == realtime_amount
    tx = btc_lst_stake.redeem(BTC_VALUE, REDEEM_SCRIPT)
    assert tx.events['Transfer']['value'] == BTC_VALUE


def test_no_rewards_generated_after_redeem(btc_lst_stake, lst_token, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(0, REDEEM_SCRIPT)
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    tx = stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == 0
    assert 'claimedReward' not in tx.events


def test_partial_redeem_btc_stake_success(btc_lst_stake, lst_token, set_candidate):
    operators, consensuses = set_candidate
    turn_round()
    tx_id = delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    turn_round()
    btc_lst_stake.redeem(BTC_VALUE // 2, REDEEM_SCRIPT)
    redeem_btc_tx = build_btc_lst_tx(accounts[0], BTC_VALUE // 2, REDEEM_SCRIPT, tx_id)
    tx = btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    expect_event(tx, 'undelegated', {
        'outputIndex': 0,
        'amount': BTC_VALUE // 2,
        'pkscript': REDEEM_SCRIPT,
    })
    turn_round(consensuses)
    tracker = get_tracker(accounts[0])
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 3 // 4 - FEE
    turn_round(consensuses)
    stake_hub_claim_reward(accounts[0])
    assert tracker.delta() == TOTAL_REWARD * 3 // 2


def test_redeem_without_pledge_reverts(btc_lst_stake, lst_token, set_candidate):
    delegate_btc_lst_success(accounts[1], BTC_VALUE, LOCK_SCRIPT)
    with brownie.reverts("Not enough btc token"):
        btc_lst_stake.redeem(BTC_VALUE // 2, REDEEM_SCRIPT)


@pytest.mark.parametrize("redeem_value", [0, 1, -1])
def test_btc_redeem_exceeds_single_limit(btc_lst_stake, lst_token, set_candidate, redeem_value):
    utxo_fee = 100
    btc_value = 15e8
    redeem_amount = 10e8
    delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    if redeem_value > 0:
        with brownie.reverts("The cumulative burn amount has reached the upper limit"):
            btc_lst_stake.redeem(redeem_amount + utxo_fee + redeem_value, REDEEM_SCRIPT)
    else:
        tx = btc_lst_stake.redeem(redeem_amount + utxo_fee + redeem_value, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events


def test_btc_redeem_in_multiple_parts(btc_lst_stake, lst_token, set_candidate):
    btc_value = 15e8
    redeem_amount = 2e8
    delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    for i in range(5):
        tx = btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events
    with brownie.reverts("The cumulative burn amount has reached the upper limit"):
        btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)


@pytest.mark.parametrize("redeem_value", [9e8, 10e8, 11e8, 14e8])
def test_redeem_exceeds_after_multiple_stakes(btc_lst_stake, lst_token, set_candidate, redeem_value):
    btc_value = 3e8
    for i in range(5):
        delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    if redeem_value > 10e8:
        with brownie.reverts("The cumulative burn amount has reached the upper limit"):
            btc_lst_stake.redeem(redeem_value, REDEEM_SCRIPT)
    else:
        tx = btc_lst_stake.redeem(redeem_value, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events


def test_exceed_redeem_after_multiple_stakes_and_redeems(btc_lst_stake, lst_token, set_candidate):
    btc_value = 3e8
    redeem_amount = 2e8
    for i in range(5):
        delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    for i in range(5):
        tx = btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events
    with brownie.reverts("The cumulative burn amount has reached the upper limit"):
        btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)


@pytest.mark.parametrize("part", [True, False])
def test_recalculate_total_redeem_amount_after_undelegate(btc_lst_stake, part):
    btc_value = 5e8
    redeem_amount = 2e8
    uxto_fee = 100
    tx_id = None
    for i in range(5):
        tx_id = delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    for i in range(5):
        tx = btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events

    redeemed = int(redeem_amount * 5) - (uxto_fee * 5)
    __check_redeem_requests(0, {
        'amount': redeemed
    })
    if part:
        redeem_btc_tx = build_btc_lst_tx(accounts[0], int(redeem_amount), REDEEM_SCRIPT, tx_id, 0)
        redeemed -= redeem_amount
        btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
        __check_redeem_requests(0, {
            'amount': redeemed
        })
    else:
        redeem_btc_tx = build_btc_lst_tx(accounts[0], int(redeem_amount * 5), REDEEM_SCRIPT, tx_id, 0)
        btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
        assert btc_lst_stake.getRedeemRequestsLength() == 0
    btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
    if part:
        with brownie.reverts("The cumulative burn amount has reached the upper limit"):
            btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
    else:
        tx = btc_lst_stake.redeem(redeem_amount, REDEEM_SCRIPT)
        assert 'redeemed' in tx.events
        with brownie.reverts("The cumulative burn amount has reached the upper limit"):
            btc_lst_stake.redeem(9e8, REDEEM_SCRIPT)


def test_full_clear_after_undelegate(btc_lst_stake):
    btc_value = 20e8
    redeem_amount0 = 2e8
    redeem_amount1 = 10e8
    tx_id = delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    btc_lst_stake.redeem(redeem_amount0, REDEEM_SCRIPT)
    with brownie.reverts("The cumulative burn amount has reached the upper limit"):
        btc_lst_stake.redeem(redeem_amount1, REDEEM_SCRIPT)
    redeem_btc_tx = build_btc_lst_tx(accounts[0], redeem_amount0, REDEEM_SCRIPT, tx_id, 0)
    btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    tx = btc_lst_stake.redeem(redeem_amount1, REDEEM_SCRIPT)
    assert 'redeemed' in tx.events


@pytest.mark.parametrize("burn_btc_limit", [1000, 1e6, 20e8, 100e8])
def test_redeem_after_modifying_btc_limit(btc_lst_stake, burn_btc_limit):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(burn_btc_limit)), 64)
    btc_lst_stake.updateParam('burnBTCLimit', hex_value)
    btc_value = 210e8
    tx_id = delegate_btc_lst_success(accounts[0], btc_value, LOCK_SCRIPT)
    btc_lst_stake.redeem(burn_btc_limit + UTXO_FEE, REDEEM_SCRIPT)
    with brownie.reverts("The cumulative burn amount has reached the upper limit"):
        btc_lst_stake.redeem(burn_btc_limit, REDEEM_SCRIPT)
    redeem_btc_tx = build_btc_lst_tx(accounts[0], btc_value, REDEEM_SCRIPT, tx_id, 0)
    btc_lst_stake.undelegate(redeem_btc_tx, 0, [], 0)
    tx = btc_lst_stake.redeem(burn_btc_limit + UTXO_FEE, REDEEM_SCRIPT)
    assert 'redeemed' in tx.events


def test_on_token_transfer_success(btc_agent, btc_lst_stake, lst_token, set_candidate):
    btc_amount = BTC_VALUE * 2
    operators, consensuses = set_candidate
    turn_round()
    delegate_btc_lst_success(accounts[0], btc_amount, LOCK_SCRIPT, percentage=Utils.DENOMINATOR)
    turn_round()
    turn_round(consensuses)
    update_system_contract_address(btc_lst_stake, lst_token=accounts[0])
    btc_lst_stake.onTokenTransfer(accounts[0], accounts[1], btc_amount // 2)
    __check_user_stake_info(accounts[0], {
        'realtimeAmount': BTC_VALUE,
        'stakedAmount': BTC_VALUE
    })
    __check_user_stake_info(accounts[1], {
        'realtimeAmount': BTC_VALUE,
        'stakedAmount': 0
    })
    tracker0 = get_tracker(accounts[0])
    tracker1 = get_tracker(accounts[1])
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == TOTAL_REWARD * 3 - FEE
    assert tracker1.delta() == 0
    turn_round(consensuses)
    __check_user_stake_info(accounts[1], {
        'realtimeAmount': BTC_VALUE,
        'stakedAmount': 0
    })
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    assert tracker1.delta() == 0
    turn_round(consensuses)
    __check_user_stake_info(accounts[1], {
        'realtimeAmount': BTC_VALUE,
        'stakedAmount': BTC_VALUE
    })
    stake_hub_claim_reward(accounts[0])
    stake_hub_claim_reward(accounts[1])
    assert tracker0.delta() == TOTAL_REWARD * 3 // 2
    assert tracker1.delta() == TOTAL_REWARD * 3 // 2


def test_only_lst_token_can_call_on_token_transfer(btc_lst_stake, lst_token, set_candidate):
    with brownie.reverts("only btc lst token can call this function"):
        btc_lst_stake.onTokenTransfer(accounts[0], accounts[1], BTC_VALUE)


def test_revert_on_lst_token_transfer_with_zero_from_address(btc_lst_stake, lst_token, set_candidate):
    update_system_contract_address(btc_lst_stake, lst_token=accounts[0])
    with brownie.reverts("invalid sender"):
        btc_lst_stake.onTokenTransfer(constants.ADDRESS_ZERO, accounts[1], BTC_VALUE)


def test_revert_on_lst_token_transfer_with_zero_to_address(btc_lst_stake, lst_token, set_candidate):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    update_system_contract_address(btc_lst_stake, lst_token=accounts[0])
    with brownie.reverts("invalid receiver"):
        btc_lst_stake.onTokenTransfer(accounts[0], constants.ADDRESS_ZERO, BTC_VALUE)


def test_lst_token_transfer_amount_exceeds_balance(btc_lst_stake, lst_token, set_candidate):
    delegate_btc_lst_success(accounts[0], BTC_VALUE, LOCK_SCRIPT)
    update_system_contract_address(btc_lst_stake, lst_token=accounts[0])
    with brownie.reverts("Insufficient balance"):
        btc_lst_stake.onTokenTransfer(accounts[0], constants.ADDRESS_ZERO, BTC_VALUE + 1)


def test_get_wallets_success(btc_lst_stake):
    stake_manager.add_wallet(REDEEM_SCRIPT)
    hash1, type1 = BtcScript.get_script_hash(LOCK_SCRIPT)
    hash2, type2 = BtcScript.get_script_hash(REDEEM_SCRIPT)
    assert btc_lst_stake.getWallets() == [[hash1, type1, 1], [hash2, type2, 1]]


@pytest.mark.parametrize("script", ['p2sh', 'p2pkh', 'p2wpkh', 'p2wsh', 'p2tr'])
def test_add_wallet_success(btc_lst_stake, script):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    script = __create_btc_lst_staking_script(script)
    btc_lst_stake.updateParam('add', script)
    wallet_index = btc_lst_stake.getWalletMap(keccak_hash256(script))
    wallets = btc_lst_stake.wallets(wallet_index - 1)
    assert wallets[0] == btc_script.get_script_hash(script)[0]
    assert wallets[1] == btc_script.get_script_hash(script)[1]
    assert wallets[2] == 1


def test_duplicate_add_wallet_calls(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    script_info = btc_script.get_script_hash(LOCK_SCRIPT)
    assert btc_lst_stake.wallets(0) == [script_info[0], script_info[1], 1]
    tx = btc_lst_stake.updateParam('add', LOCK_SCRIPT)
    expect_event(tx, 'addedWallet', {
        '_hash': script_info[0],
        '_type': script_info[1]
    })
    assert btc_lst_stake.wallets(0) == [script_info[0], script_info[1], 1]


@pytest.mark.parametrize("script", [
    pytest.param('0xa924047b9ba09367c1b213b5ba2184fba3fababcdc0287', id="p2sh format error"),
    pytest.param('0x76a914047b9ba09367c1b213b5ba2184fba3fababcdc0288aa', id="p2pkh format error"),
    pytest.param('0x0013047b9ba09367c1b213b5ba2184fba3fababcdc02', id="p2wpkh format error"),
    pytest.param('0x00223d1b55fe81a7ca9718d8c909876b74550782a5a748f49b6c2e519de73342cb16', id="p2wsh format error"),
    pytest.param('0x51303d1b55fe81a7ca9718d8c909876b74550782a5a748f49b6c2e519de73342cb16', id="p2tr format error")])
def test_revert_on_invalid_btc_wallet(btc_lst_stake, script):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    with brownie.reverts("Invalid BTC wallet"):
        btc_lst_stake.updateParam('add', script)


def test_re_add_deleted_btc_wallet(btc_lst_stake):
    stake_manager.add_wallet(REDEEM_SCRIPT)
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('remove', LOCK_SCRIPT)
    wallets = btc_lst_stake.wallets(0)
    assert wallets[2] == 2
    btc_lst_stake.updateParam('add', LOCK_SCRIPT)
    wallets = btc_lst_stake.wallets(0)
    assert wallets[2] == 1
    btc_lst_stake.updateParam('remove', REDEEM_SCRIPT)
    wallets = btc_lst_stake.wallets(1)
    assert wallets[2] == 2
    btc_lst_stake.updateParam('add', REDEEM_SCRIPT)
    wallets = btc_lst_stake.wallets(1)
    assert wallets[2] == 1


@pytest.mark.parametrize("script", ['p2sh', 'p2pkh', 'p2wpkh', 'p2wsh', 'p2tr'])
def test_remove_wallet(btc_lst_stake, script):
    if script == 'p2sh':
        stake_manager.add_wallet(REDEEM_SCRIPT)
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    stake_script = __create_btc_lst_staking_script(script)
    btc_lst_stake.updateParam('add', stake_script)
    wallet_index = btc_lst_stake.getWalletMap(keccak_hash256(stake_script))
    actual_wallet_index = 2
    if script == 'p2sh':
        actual_wallet_index = 1
    assert wallet_index == actual_wallet_index
    wallets = btc_lst_stake.wallets(wallet_index - 1)
    assert wallets[2] == 1
    tx = btc_lst_stake.updateParam('remove', stake_script)
    wallets = btc_lst_stake.wallets(wallet_index - 1)
    assert wallets[2] == 2
    script_info = btc_script.get_script_hash(stake_script)
    expect_event(tx, 'removedWallet', {
        '_hash': script_info[0],
        '_type': script_info[1]
    })


def test_revert_on_deleting_unadded_btc_wallet(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    stake_script = __create_btc_lst_staking_script('p2tr')
    with brownie.reverts("Wallet not found"):
        btc_lst_stake.updateParam('remove', stake_script)


def test_keep_at_least_one_valid_multisig_address(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    with brownie.reverts("Wallet empty"):
        btc_lst_stake.updateParam('remove', LOCK_SCRIPT)
    stake_manager.add_wallet(REDEEM_SCRIPT)
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('remove', REDEEM_SCRIPT)
    with brownie.reverts("Wallet empty"):
        btc_lst_stake.updateParam('remove', LOCK_SCRIPT)
    btc_lst_script = random_btc_lst_lock_script()
    stake_manager.add_wallet(btc_lst_script)
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    tx = btc_lst_stake.updateParam('remove', LOCK_SCRIPT)
    assert 'removedWallet' in tx.events


def test_duplicate_stake_address_remove_and_add(btc_lst_stake):
    stake_manager.add_wallet(REDEEM_SCRIPT)
    wallet_index = btc_lst_stake.getWalletMap(keccak_hash256(REDEEM_SCRIPT))
    actual_wallet_index = 2
    assert wallet_index == actual_wallet_index
    wallets = btc_lst_stake.wallets(actual_wallet_index - 1)
    script_hash, script_type = BtcScript.get_script_hash(REDEEM_SCRIPT)
    assert wallets == [script_hash, script_type, 1]
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    btc_lst_stake.updateParam('remove', REDEEM_SCRIPT)
    wallets = btc_lst_stake.wallets(actual_wallet_index - 1)
    assert wallets == [script_hash, script_type, 2]
    stake_manager.add_wallet(REDEEM_SCRIPT)
    assert wallet_index == actual_wallet_index
    wallets = btc_lst_stake.wallets(actual_wallet_index - 1)
    assert wallets == [script_hash, script_type, 1]
    btc_lst_script = random_btc_lst_lock_script()
    stake_manager.add_wallet(btc_lst_script)
    script_hash, script_type = BtcScript.get_script_hash(btc_lst_script)
    wallet_index = btc_lst_stake.getWalletMap(keccak_hash256(btc_lst_script))
    assert wallet_index == 3
    wallets = btc_lst_stake.wallets(wallet_index - 1)
    assert wallets == [script_hash, script_type, 1]


@pytest.mark.parametrize("paused", [0, 1])
def test_update_paused_success(btc_lst_stake, paused):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    if paused:
        btc_lst_stake.updateParam('paused', 1)
        paused_ = True
    else:
        btc_lst_stake.updateParam('paused', 1)
        btc_lst_stake.updateParam('paused', 0)
        paused_ = False
    assert btc_lst_stake.paused() is paused_


def test_update_paused_length_error(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(1), 64)
    with brownie.reverts("MismatchParamLength: paused"):
        btc_lst_stake.updateParam('paused', hex_value)


@pytest.mark.parametrize("paused", [2, 3, 4])
def test_update_paused_range_error(btc_lst_stake, paused):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    with brownie.reverts(f"OutOfBounds: paused, {paused}, 0, 1"):
        btc_lst_stake.updateParam('paused', paused)


@pytest.mark.parametrize("burn_btc_limit", [1e5, 2e8, 10e8, 100e8])
def test_update_burn_btc_limit_success(btc_lst_stake, burn_btc_limit):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(burn_btc_limit)), 64)
    btc_lst_stake.updateParam('burnBTCLimit', hex_value)
    assert btc_lst_stake.burnBTCLimit() == int(burn_btc_limit)


def test_update_burn_btc_limit_param_length_error(btc_lst_stake):
    burn_btc_limit = 10e8
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(burn_btc_limit)), 62)
    with brownie.reverts("MismatchParamLength: burnBTCLimit"):
        btc_lst_stake.updateParam('burnBTCLimit', hex_value)


@pytest.mark.parametrize("utxo_fee", [1e4, 1e5, 1e8, 1e10, 1e12])
def test_update_utxo_fee_success(btc_lst_stake, utxo_fee):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(utxo_fee)), 16)
    btc_lst_stake.updateParam('utxoFee', hex_value)
    assert btc_lst_stake.utxoFee() == utxo_fee


def test_utxo_fee_length_incorrect(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(1e8)), 32)
    with brownie.reverts("MismatchParamLength: utxoFee"):
        btc_lst_stake.updateParam('utxoFee', hex_value)


def test_utxo_fee_too_low(btc_lst_stake):
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    hex_value = padding_left(Web3.to_hex(int(1e2)), 16)
    with brownie.reverts("OutOfBounds: utxoFee, 100, 1000, 18446744073709551615"):
        btc_lst_stake.updateParam('utxoFee', hex_value)


def test_governance_param_not_exist(btc_lst_stake):
    test_value = 10e8
    update_system_contract_address(btc_lst_stake, gov_hub=accounts[0])
    with brownie.reverts("UnsupportedGovParam: test"):
        btc_lst_stake.updateParam('test', int(test_value))


def test_update_param_only_callable_by_gov_hub(btc_lst_stake):
    hex_value = padding_left(Web3.to_hex(0), 64)
    with brownie.reverts("the msg sender must be governance contract"):
        btc_lst_stake.updateParam('burnBTCLimit', hex_value)


def __create_btc_lst_staking_script(script_type='p2sh', script_public_key=None):
    if script_public_key is None:
        script_public_key = public_key
    lock_scrip = btc_script.k2_btc_lst_script(script_public_key, script_type)
    return lock_scrip


def __create_btc_lst_delegate(delegator, amount, script_public_key=None, script_type='p2sh', fee=1, version=2,
                              chain_id=1112, magic='5341542b', input_tx_id=None, vout=0):
    pay_address = __create_btc_lst_staking_script(script_type, script_public_key)
    btc_tx = build_btc_lst_tx(delegator, amount, pay_address, input_tx_id, vout, fee, version, chain_id, magic)
    return btc_tx, pay_address


def __get_redeem_requests(index):
    redeem_request = BTC_LST_STAKE.redeemRequests(index)
    return redeem_request


def __get_btc_tx_map(tx_id):
    bt = BTC_LST_STAKE.btcTxMap(tx_id)
    return bt


def __check_user_stake_info(delegator, result: dict):
    user_info = BTC_LST_STAKE.userStakeInfo(delegator)
    for r in result:
        assert result[r] == user_info[r]


def __check_redeem_requests(redeem_index, result: dict):
    redeem_request = BTC_LST_STAKE.redeemRequests(redeem_index)
    for i in result:
        assert redeem_request[i] == result[i]


def __get_btc_lst_tx_map_info(tx_id):
    data = BTC_LST_STAKE.btcTxMap(tx_id)
    return data


def __check_btc_lst_tx_map_info(tx_id, result: dict):
    data = __get_btc_lst_tx_map_info(tx_id)
    for i in result:
        assert data[i] == result[i]
