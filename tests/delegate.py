import time

from tests.common import get_current_round
from tests.utils import *
from brownie import *

LOCK_TIME = 1736956800


def set_outputs(*outputs):
    btc_outputs = []
    for output in outputs:
        if len(output) != 2:
            raise 'failed'
        btc_outputs.append(output)
    return btc_outputs


def set_op_return(*op_return):
    btc_op_return = []
    for op in op_return:
        btc_op_return.append(op)
    return btc_op_return


def set_inputs(*inputs):
    btc_inputs = []
    for input in inputs:
        btc_inputs.append(input)
    return btc_inputs


def build_btc_lst_stake_opreturn(delegator, fee=1, version=2, chain_id=1112, magic='5341542b'):
    fee_hex = op2hex(fee)
    version_hex = op2hex(version)
    chain_id_hex = hex(chain_id).replace('x', '')
    delegator = str(delegator)[2:].lower()
    message = magic + version_hex + chain_id_hex + delegator + fee_hex
    message_length = remove_0x(hex(len(message) // 2))
    op_return = remove_0x(hex(Opcode.OP_RETURN))
    if len(message) // 2 > 76:
        op_return += remove_0x(hex(Opcode.OP_PUSHDATA1))
    op_return = op_return + message_length + message
    op_return_length = remove_0x(hex(len(op_return) // 2))
    btc_value = btc_value_2hex(0)
    op_return = btc_value + op_return_length + op_return
    op_return_info = {
        'magic': magic,
        'version': version_hex,
        'chain_id': chain_id_hex,
        'delegator': delegator,
        'fee': fee_hex,
        'value_hex': btc_value,
        'hex_value': op_return,
        'message': message
    }
    return op_return_info


def build_btc_stake_opreturn(agent_address, delegate_address, lock_data, chain_id=1112, core_fee=1,
                             version=1):
    if isinstance(lock_data, int):
        hex_result = value2hex(lock_data)
        lock_time_hex = reverse_by_bytes(hex_result)
        op_return_data = lock_time_hex
    else:
        op_return_data = lock_data
    flag_hex = ''.join(format(ord(c), 'x') for c in 'SAT+').zfill(8)
    version_hex = op2hex(version)
    chain_id_hex = format(int(chain_id), 'x').zfill(4)
    delegate_address_hex = str(delegate_address)[2:].lower()
    agent_address_hex = str(agent_address)[2:]
    core_fee_hex = format(core_fee, 'x').zfill(2)
    message = flag_hex + version_hex + chain_id_hex + delegate_address_hex + agent_address_hex + core_fee_hex + op_return_data
    message_length = remove_0x(hex(len(message) // 2))
    op_return = remove_0x(hex(Opcode.OP_RETURN))
    if len(message) // 2 > 76:
        op_return += remove_0x(hex(Opcode.OP_PUSHDATA1))
    op_return = op_return + message_length + message
    op_return_length = remove_0x(hex(len(op_return) // 2))
    btc_value = btc_value_2hex(0)
    op_return = btc_value + op_return_length + op_return
    opreturn_info = {
        'flag_hex': flag_hex,
        'version_hex': version_hex,
        'chain_id_hex': chain_id_hex,
        'delegate_address_hex': delegate_address_hex,
        'agent_address_hex': agent_address_hex,
        'core_fee_hex': core_fee_hex,
        'op_return_data': op_return_data,
        'hex_value': op_return,
        'message': message
    }
    return opreturn_info


def build_input(txid=None, vout=0, scriptsigsize='6a', scriptsig=None, sequence='ffffffff'):
    if txid is None:
        txid = random_btc_tx_id()
    if scriptsig is None:
        scriptsig = '473044022046e23b8f6b749a15b0571848fe2b86bfbe7e158b23f37fb0335be0a71f48a5dd022076640b2d39659c26224c9e67101b34e1394a38ff08a4bdd88d7503f63e54adc5012103b3e19c8169b81d15ec21f9d0f3ed4b2f18c7c9e1149ce5f7ddebed7732724b9f'
    txid = remove_0x(txid)
    vout = format_number(vout)
    input_info = {
        'txid': txid,
        'vout': vout,
        'scriptsigsize': scriptsigsize,
        'scriptsig': scriptsig,
        'sequence': sequence,
        'hex_value': txid + vout + scriptsigsize + scriptsig + sequence
    }
    return input_info


def build_output(amount, script_pub_key):
    script_pub_key = remove_0x(script_pub_key)
    scriptpubkeysize = value2hex(len(script_pub_key) // 2)
    output_info = {
        'amount': btc_value_2hex(amount),
        'scriptpubkeysize': scriptpubkeysize,
        'scriptpubkey': script_pub_key,
        'hex_value': btc_value_2hex(amount) + scriptpubkeysize + script_pub_key
    }
    return output_info


def generate_btc_transaction_info(btc_tx_info, inputs=None, outputs=None):
    btc_tx_info['version'] = '02000000'
    btc_tx_info['inputcount'] = f'0{len(inputs)}'
    btc_tx_info['inputs'] = []
    # btc_tx_info['outputcount'] = f'0{len(outputs)}'
    output_count = hex(len(outputs)).replace('0x', '')
    if len(output_count) == 1:
        output_count = f'0{output_count}'
    btc_tx_info['outputcount'] = f'{output_count}'
    btc_tx_info['outputs'] = []
    btc_tx_info['inputs'] = []
    outputs_list = btc_tx_info['outputs']
    inputs_list = btc_tx_info['inputs']
    for i in inputs:
        inputs_list.append(i)
    for i in outputs:
        outputs_list.append(i)
    btc_tx_info['locktime'] = '00000000'


def build_btc_transaction(btc_tx_info):
    btc_tx = btc_tx_info['version']
    btc_tx += btc_tx_info['inputcount']
    inputs = btc_tx_info['inputs']
    outputs = btc_tx_info['outputs']
    for input in inputs:
        btc_tx += input['hex_value']
    btc_tx += btc_tx_info['outputcount']
    for output in outputs:
        btc_tx += output['hex_value']
    btc_tx += btc_tx_info['locktime']
    return btc_tx


def build_btc_lst_tx(delegator, amount, pay_address, input_tx_id=None, vout=0, fee=1, version=2,
                     chain_id=1112, magic='5341542b'):
    btc_tx_info = {}
    inputs = [build_input(input_tx_id, vout)]
    amount = int(amount)
    outputs = [build_output(amount, pay_address),
               build_btc_lst_stake_opreturn(delegator, fee, version, chain_id, magic)]
    generate_btc_transaction_info(btc_tx_info, inputs, outputs)
    btc_tx = build_btc_transaction(btc_tx_info)
    return btc_tx


def build_btc_tx(agent, delegator, amount, lock_script, lock_data=1736956800, pay_address_type='p2sh', fee=1,
                 version=1,
                 chain_id=1112):
    pay_address = get_btc_script().k2_btc_pay_address(lock_script, pay_address_type)
    btc_tx_info = {}
    inputs = [build_input()]
    outputs = [build_output(amount, pay_address),
               build_btc_stake_opreturn(agent, delegator, lock_data, chain_id, fee, version)]
    generate_btc_transaction_info(btc_tx_info, inputs, outputs)
    btc_tx = build_btc_transaction(btc_tx_info)
    return btc_tx


def get_transaction_op_return_data(chain_id, agent_address, delegate_address, lock_data, core_fee=1, version=1):
    opreturn = build_btc_stake_opreturn(agent_address, delegate_address, lock_data, chain_id, core_fee, version)
    return opreturn['message']


def get_btc_lst_transaction_op_return_data(delegator, fee, version, chain_id, magic='5341542b'):
    opreturn = build_btc_lst_stake_opreturn(delegator, fee, version, chain_id, magic)
    return opreturn['message']


def get_btc_script():
    return BtcScript()


def set_block_time_stamp(timestamp, stake_lock_time, time_type='day'):
    # the default timestamp is days
    if time_type == 'day':
        timestamp = timestamp * Utils.ROUND_INTERVAL
        time1 = stake_lock_time - timestamp
    else:
        timestamp = timestamp * Utils.MONTH_TIMESTAMP
        time1 = stake_lock_time - timestamp
    BtcLightClientMock[0].setCheckResult(True, time1)


def set_last_round_tag(stake_round, time0=None):
    if time0 is None:
        time0 = LOCK_TIME
    end_round0 = time0 // Utils.ROUND_INTERVAL
    current_round = end_round0 - stake_round - 1
    CandidateHubMock[0].setRoundTag(current_round)
    BitcoinStakeMock[0].setRoundTag(current_round)
    BitcoinLSTStakeMock[0].setInitRound(current_round)
    return end_round0, current_round


# delegate
def delegate_coin_success(candidate, delegator, amount):
    tx = CoreAgentMock[0].delegateCoin(candidate, {'value': amount, 'from': delegator})
    assert 'delegatedCoin' in tx.events
    return tx


def transfer_coin_success(source_agent, target_agent, delegator, amount):
    tx = CoreAgentMock[0].transferCoin(source_agent, target_agent, amount, {'from': delegator})
    assert 'transferredCoin' in tx.events
    return tx


def undelegate_coin_success(candidate, delegator, amount):
    tx = CoreAgentMock[0].undelegateCoin(candidate, amount, {'from': delegator})
    assert 'undelegatedCoin' in tx.events
    return tx


def delegate_btc_success(agent, delegator, btc_amount, lock_script, lock_data=None, relay=None, stake_duration=None,
                         fee=1, script_type='p2sh', lock_time=None):
    if stake_duration is None:
        stake_duration = Utils.MONTH
    if lock_time is None:
        lock_time = LOCK_TIME
    set_block_time_stamp(stake_duration, lock_time)
    if lock_data is None:
        lock_data = lock_script
    btc_tx0 = build_btc_tx(agent, delegator, int(btc_amount), lock_script, lock_data, script_type, fee)
    if relay is None:
        relay = accounts[0]
    tx = BitcoinStakeMock[0].delegate(btc_tx0, 1, [], 0, lock_script, {"from": relay})
    assert 'delegated' in tx.events
    tx_id = get_transaction_txid(btc_tx0)
    return tx_id


def transfer_btc_success(tx_id, target_candidate, delegator):
    tx = BitcoinStakeMock[0].transfer(tx_id, target_candidate, {'from': delegator})
    assert 'transferredBtc' in tx.events
    return tx


def delegate_power_success(candidate, delegator, value=1, stake_round=0):
    stake_round = get_current_round() - 6 + stake_round
    BtcLightClientMock[0].setMiners(stake_round, candidate, [delegator] * value)


def delegate_btc_lst_success(delegator, btc_amount, lock_script, percentage=5000, relay=None):
    BitcoinAgentMock[0].setPercentage(percentage)
    delegator_asset = BitcoinLSTToken[0].balanceOf(delegator)
    btc_tx0 = build_btc_lst_tx(delegator, int(btc_amount), lock_script)
    if relay is None:
        relay = accounts[0]
    tx = BitcoinLSTStakeMock[0].delegate(btc_tx0, 1, [], 0, lock_script, {"from": relay})
    assert 'delegated' in tx.events
    delegator_asset += btc_amount
    assert BitcoinLSTToken[0].balanceOf(delegator) == delegator_asset
    tx_id = get_transaction_txid(btc_tx0)
    return tx_id


def transfer_btc_lst_success(delegator, amount, to):
    from_asset0 = BitcoinLSTToken[0].balanceOf(delegator)
    to_asset = BitcoinLSTToken[0].balanceOf(to)
    BitcoinLSTToken[0].transfer(to, amount, {"from": delegator})
    from_asset = from_asset0 - amount
    to_asset += amount
    if delegator == to:
        to_asset = from_asset0
        from_asset = from_asset0
    assert BitcoinLSTToken[0].balanceOf(delegator) == from_asset
    assert BitcoinLSTToken[0].balanceOf(to) == to_asset


def redeem_btc_lst_success(delegator, amount, pkscript):
    UTXO_FEE = 100
    tx = BitcoinLSTStakeMock[0].redeem(amount, pkscript, {"from": delegator})
    assert tx.events['redeemed']['amount'] == amount - UTXO_FEE
    return tx


# old delegate
def old_delegate_coin_success(candidate, account, amount, old=True):
    if old is True:
        tx = PledgeAgentMock[0].delegateCoinOld(candidate, {'value': amount, 'from': account})
        assert 'delegatedCoinOld' in tx.events
    else:
        tx = PledgeAgentMock[0].delegateCoin(candidate, {'value': amount, 'from': account})
        assert 'delegatedCoin' in tx.events

    return tx


def old_undelegate_coin_success(candidate, account, amount=0, old=True):
    if old is True:
        tx = PledgeAgentMock[0].undelegateCoinOld(candidate, amount, {'from': account})
        assert 'undelegatedCoinOld' in tx.events

    else:
        tx = PledgeAgentMock[0].undelegateCoin(candidate, amount, {'from': account})
        assert 'undelegatedCoin' in tx.events
    return tx


def old_transfer_coin_success(source_agent, target_agent, account, amount=0, old=True):
    if old is True:
        tx = PledgeAgentMock[0].transferCoinOld(source_agent, target_agent, amount, {'from': account})
        assert 'transferredCoinOld' in tx.events
    else:
        tx = PledgeAgentMock[0].transferCoin(source_agent, target_agent, amount, {'from': account})
        assert 'transferredCoin' in tx.events
    return tx


def old_claim_reward_success(candidates, account=None):
    if isinstance(account, list):
        for a in account:
            tx = PledgeAgentMock[0].claimReward(candidates, {'from': a})
    else:
        if account is None:
            account = accounts[0]
        tx = PledgeAgentMock[0].claimReward(candidates, {'from': account})


def old_claim_btc_reward_success(tx_ids, account=None):
    if account is None:
        account = accounts[0]
    tx = PledgeAgentMock[0].claimBtcReward(tx_ids, {'from': account})
    return tx


def old_turn_round(miners: list = None, tx_fee=100, round_count=1):
    if miners is None:
        miners = []
    tx = None
    for _ in range(round_count):
        for miner in miners:
            ValidatorSetMock[0].deposit(miner, {"value": tx_fee, "from": accounts[-10]})
        tx = CandidateHubMock[0].turnRoundOld()
        chain.sleep(1)
    return tx


def old_delegate_btc_success(btc_value, agent, delegator, lock_time=None, tx_id=None, script=None, fee=1):
    if script is None:
        script, _, timestamp = random_btc_lock_script()
        lock_time = timestamp
    if tx_id is None:
        tx_id = random_btc_tx_id()
    PledgeAgentMock[0].delegateBtcMock(tx_id, btc_value, agent, delegator, script, lock_time, fee)
    return tx_id


def old_trannsfer_btc_success(tx_id, agent):
    tx = PledgeAgentMock[0].transferBtcOld(tx_id, agent)
    return tx_id


class BtcScript:
    @staticmethod
    def get_script_hash(script):
        bytes_script = bytes.fromhex(script.replace('0x', ''))
        script_hash, add_type = extract_pk_script_addr(bytes_script)
        hex_string = '0x' + bytes_to_hex_string(script_hash).rjust(64, '0')
        return hex_string, add_type

    @staticmethod
    def k2_btc_pay_address(lock_script, lock_script_type='p2sh'):
        pay_address = None
        if lock_script_type == 'p2sh':
            public_key_hash = public_key_2pkhash(lock_script)
            script_hash = f"{hex(Opcode.OP_HASH160)}14{public_key_hash}{hex(Opcode.OP_EQUAL)}"
            pay_address = '0x' + script_hash.replace('0x', '')
        elif lock_script_type == 'p2wsh':
            redeem_script = sha256(bytes.fromhex(lock_script)).hexdigest()
            script_hash = f"{op2hex(Opcode.OP_0)}{hex(Opcode.OP_DATA_32)}{redeem_script}"
            pay_address = '0x' + script_hash.replace('0x', '')
        return pay_address

    def k2_btc_script(self, lock_public_key, lock_time, scrip_type, lock_script_type='p2sh'):

        hex_result = hex(lock_time)[2:]
        lock_time_hex = reverse_by_bytes(hex_result)
        if scrip_type == 'hash':
            public_hash = public_key_2pkhash(lock_public_key)
            lock_scrip = "04" + lock_time_hex + "b17576a914" + public_hash[2:] + "88ac"
        else:
            lock_scrip = "04" + lock_time_hex + "b17521" + lock_public_key + "ac"
        pay_address = self.k2_btc_pay_address(lock_scrip, lock_script_type)
        return lock_scrip, pay_address

    @staticmethod
    def k2_btc_lst_script(lock_public_key, lock_script_type='p2sh'):
        lock_script = None
        if lock_script_type == AddressType.P2SH:  # 23 bytes
            public_key_hash = public_key_2pkhash(lock_public_key)
            script_hash = f"{hex(Opcode.OP_HASH160)}14{public_key_hash}{hex(Opcode.OP_EQUAL)}"
            lock_script = '0x' + script_hash.replace('0x', '')
        elif lock_script_type == AddressType.P2PKH:  # 25 bytes
            public_key_hash = public_key_2pkhash(lock_public_key)
            script_hash = f"{hex(Opcode.OP_DUP)}{hex(Opcode.OP_HASH160)}{hex(Opcode.OP_DATA_20)}{public_key_hash}{hex(Opcode.OP_EQUALVERIFY)}{hex(Opcode.OP_CHECKSIG)}"
            lock_script = '0x' + script_hash.replace('0x', '')
        elif lock_script_type == AddressType.P2WPKH:  # 25 bytes
            public_key_hash = public_key_2pkhash(lock_public_key)
            script_hash = f"{op2hex(Opcode.OP_0)}{hex(Opcode.OP_DATA_20)}{public_key_hash}"
            lock_script = '0x' + script_hash.replace('0x', '')
        elif lock_script_type == AddressType.P2WSH:  # 34 bytes
            public_key_hash = public_key_2pkhash(lock_public_key)
            redeem_script = sha256(bytes.fromhex(public_key_hash.replace('0x', ''))).hexdigest()
            script_hash = f"{op2hex(Opcode.OP_0)}{hex(Opcode.OP_DATA_32)}{redeem_script}"
            lock_script = '0x' + script_hash.replace('0x', '')
        elif lock_script_type == AddressType.P2TAPROOT:  # 34 bytes
            public_key_hash = public_key_2pkhash(lock_public_key)
            redeem_script = sha256(bytes.fromhex(public_key_hash.replace('0x', ''))).hexdigest()
            script_hash = f"{op2hex(Opcode.OP_1)}{hex(Opcode.OP_DATA_32)}{redeem_script}"
            lock_script = '0x' + script_hash.replace('0x', '')
        return lock_script


class BtcStake:
    def __init__(self):
        self.inputs = []
        self.outputs = []
        self.tx_id = None
        self.btc_tx_info = None

    def get_btc_inputs(self):
        return self.inputs

    def get_btc_tx_id(self):
        return self.tx_id

    def get_btc_outputs(self):
        return self.outputs

    def get_btc_tx_info(self):
        return self.btc_tx_info

    def clear(self):
        self.inputs.clear()
        self.outputs.clear()
        self.btc_tx_info = {}
        self.tx_id = None

    def btc_stake_build_input(self, txid=None, vout=0, scriptsigsize='6a', scriptsig=None, sequence='ffffffff'):
        input_info = build_input(txid, vout, scriptsigsize, scriptsig, sequence)
        self.inputs.append(input_info)
        return input_info

    def btc_stake_build_output(self, amount, script_pub_key):
        output_info = build_output(amount, script_pub_key)
        self.outputs.append(output_info)
        return output_info

    def build_btc(self, inputs, outputs, opreturn):
        self.clear()
        for i in inputs:
            self.btc_stake_build_input(*i)
        if len(self.inputs) == 0:
            self.btc_stake_build_input()
        for output in outputs[:1]:
            self.btc_stake_build_output(*output)
        for op in opreturn:
            self.outputs.append(build_btc_stake_opreturn(*op))
        for output in outputs[1:]:
            self.btc_stake_build_output(*output)
        generate_btc_transaction_info(self.btc_tx_info, self.inputs, self.outputs)
        btc_tx = self.btc_tx_info['version']
        btc_tx += self.btc_tx_info['inputcount']
        inputs = self.btc_tx_info['inputs']
        outputs = self.btc_tx_info['outputs']
        for input in inputs:
            btc_tx += input['hex_value']
        btc_tx += self.btc_tx_info['outputcount']
        for output in outputs:
            btc_tx += output['hex_value']
        btc_tx += self.btc_tx_info['locktime']
        self.tx_id = get_transaction_txid(btc_tx)
        return btc_tx

    def build_btc_lst(self, outputs, inputs=None, opreturn=None):
        if inputs is None:
            inputs = []
        if opreturn is None:
            opreturn = []
        self.clear()
        for i in inputs:
            self.btc_stake_build_input(*i)
        if len(self.inputs) == 0:
            self.btc_stake_build_input()
        for output in outputs[:1]:
            self.btc_stake_build_output(*output)
        for op in opreturn:
            self.outputs.append(build_btc_lst_stake_opreturn(*op))
        for output in outputs[1:]:
            self.btc_stake_build_output(*output)
        generate_btc_transaction_info(self.btc_tx_info, self.inputs, self.outputs)
        btc_tx = self.btc_tx_info['version']
        btc_tx += self.btc_tx_info['inputcount']
        inputs = self.btc_tx_info['inputs']
        outputs = self.btc_tx_info['outputs']
        for input in inputs:
            btc_tx += input['hex_value']
        btc_tx += self.btc_tx_info['outputcount']
        for output in outputs:
            btc_tx += output['hex_value']
        btc_tx += self.btc_tx_info['locktime']
        self.tx_id = get_transaction_txid(btc_tx)
        return btc_tx


def random_btc_lst_lock_script():
    private_key = generate_private_key()
    private_key_hex = get_public_key(private_key)
    script_type = random.choice(
        [AddressType.P2SH, AddressType.P2PKH, AddressType.P2WPKH, AddressType.P2WSH, AddressType.P2TAPROOT])
    script = BtcScript().k2_btc_lst_script(private_key_hex, script_type)
    return script


def random_btc_lock_script():
    private_key = generate_private_key()
    private_key_hex = get_public_key(private_key)
    timestamp = random.randint(int(time.time()), int(time.time()) + 1000000)
    scrip_type = random.choice(['hash', 'key'])
    lock_script_type = random.choice(['p2sh', 'p2wsh'])
    script, pay_address = BtcScript().k2_btc_script(private_key_hex, timestamp, scrip_type, lock_script_type)
    return script, pay_address, timestamp


class StakeManager:
    @staticmethod
    def set_lp_rates(rates=None):
        BitcoinAgentMock[0].popLpRates()
        if rates:
            for r in rates:
                tl = r[0]
                tp = r[1]
                BitcoinAgentMock[0].setLpRates(tl, tp)

    @staticmethod
    def set_tlp_rates(rates=None):
        BitcoinStakeMock[0].popTtlpRates()
        if rates:
            for r in rates:
                tl = r[0]
                tp = r[1]
                BitcoinStakeMock[0].setTlpRates(tl, tp)

    @staticmethod
    def set_is_stake_hub_active(value=False):
        BitcoinAgentMock[0].setIsActive(value)

    @staticmethod
    def set_is_btc_stake_active(value=0):
        BitcoinStakeMock[0].setIsActive(value)

    @staticmethod
    def add_wallet(script):
        update_system_contract_address(BitcoinLSTStakeMock[0], gov_hub=accounts[10])
        BitcoinLSTStakeMock[0].updateParam('add', script, {'from': accounts[10]})
        update_system_contract_address(BitcoinLSTStakeMock[0], gov_hub=GovHubMock[0])

    @staticmethod
    def remove_wallet(script):
        update_system_contract_address(BitcoinLSTStakeMock[0], gov_hub=accounts[10])
        BitcoinLSTStakeMock[0].updateParam('remove', script, {'from': accounts[10]})
        update_system_contract_address(BitcoinLSTStakeMock[0], gov_hub=GovHubMock[0])


class RoundRewardManager:
    @staticmethod
    def mock_core_reward_map(delegator, reward, acc_stake_amount):
        BitcoinAgentMock[0].setCoreRewardMap(delegator, reward, acc_stake_amount)

    @staticmethod
    def mock_btc_lst_reward_map(delegator, reward, delegate_amount):
        BitcoinLSTStakeMock[0].setBtcLstRewardMap(delegator, reward, delegate_amount)

    @staticmethod
    def mock_btc_reward_map(delegator, reward, unclaimed_reward, delegate_amount):
        BitcoinStakeMock[0].setBtcRewardMap(delegator, reward, unclaimed_reward, delegate_amount)

    @staticmethod
    def mock_power_reward_map(delegator, reward, delegate_amount):
        HashPowerAgentMock[0].setPowerRewardMap(delegator, reward, delegate_amount)
