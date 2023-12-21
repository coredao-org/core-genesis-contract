// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;


abstract contract BaseGenesisContract {

    uint public constant CORE_MAINNET = 1116;
    uint public constant CORE_TESTNET = 1115;
    uint public constant ANVIL_CHAINID = 31337;
    uint public constant GANACHE_CHAINID = 1337;

    // ERC-7201 namespace: keccak256(abi.encode(uint256(keccak256("core.basegenesis.extended.storage")) - 1)) & ~bytes32(uint256(0xff));
    bytes32 private constant _BASE_GENESIS_STORAGE_LOCATION = 0x33c2ebfd19549a55713fbe6d4a665ceab572c1ceaf0de32c6c7bdeabfc64f500;

    struct BaseGenesisExtStorage {
        /// @custom:storage-location erc7201:core.basegenesis.extended.storage
        address deployerAddr;
        bool addressesWereUpdated;
    }

    modifier canUpdateAddresses() {
        require(_useDynamicAddr(), "cannot set addresses");
        require(msg.sender == _ext0().deployerAddr, "not deployer");
        require(!_updateAddressesAlreadyCalled(), "contract addresses already updated");
        _ext0().addressesWereUpdated = true;
        _;
    }

    constructor() {
        _ext0().deployerAddr = _useDynamicAddr() ? msg.sender : address(0);
    }

    function _ext0() private pure returns (BaseGenesisExtStorage storage $) {
        assembly { $.slot := _BASE_GENESIS_STORAGE_LOCATION }
    }

    function _updateAddressesAlreadyCalled() internal virtual view returns (bool) {
        return _ext0().addressesWereUpdated;
    }

    function _useDynamicAddr() internal view returns (bool) {
        return block.chainid != CORE_MAINNET && block.chainid != CORE_TESTNET; // any network which is neither Core mainnet or testnet
    }
}