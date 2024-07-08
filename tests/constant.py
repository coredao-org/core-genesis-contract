class Opcode:
    OP_DUP = 0x76
    OP_HASH160 = 0xa9
    OP_EQUALVERIFY = 0x88
    OP_CHECKSIG = 0xac
    OP_DATA_20 = 0x14
    OP_DATA_32 = 0x20
    OP_0 = 0x00
    OP_1 = 0x51
    OP_EQUAL = 0x87


class AddressType:
    TYPE_P2PKH = 1
    TYPE_P2SH = 2
    TYPE_P2WPKH = 3
    TYPE_P2WSH = 4
    TYPE_P2TAPROOT = 5
    TYPE_UNKNOWN = 0


class Utils:
    DENOMINATOR = 10000
    CHAIN_ID = 1112
    ROUND_INTERVAL = 86400
    MONTH_TIMESTAMP = 2592000
    # calculate the BTC porter fee
    CORE_DECIMAL = 100
    # accuredRewardMap the record is a reward of 1000000 cores per round
    CORE_STAKE_DECIMAL = 1000000
    BTC_DECIMAL = 100000000


class HardCap:
    CORE_HARD_CAP = 6000
    POWER_HARD_CAP = 2000
    BTC_HARD_CAP = 4000
    SUM_HARD_CAP = CORE_HARD_CAP + POWER_HARD_CAP + BTC_HARD_CAP
