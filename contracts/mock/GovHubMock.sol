pragma solidity 0.8.4;

import "../GovHub.sol";

contract GovHubMock is GovHub {
    uint256 private constant MOCK_VOTING_PERIOD = 201600;
    uint256 private constant MOCK_EXECUTING_PERIOD = 201600;
    bytes private constant MOCK_INIT_MEMBERS = hex"f86994548e6acce441866674e04ab84587af2d394034c094bb06d463bc143eecc4a0cfa35e0346d5690fa9f694e2fe60f349c6e1a85caad1d22200c289da40dc1294b198db68258f06e79d415a0998be7f9b38ea722694dd173b85f306128f1b10d7d7219059c28c6d6c09";

    function developmentInit() external {
        votingPeriod = 20;
        address[2] memory initMembers = [
            address(0x9fB29AAc15b9A4B7F17c3385939b007540f4d791),
            address(0x96C42C56fdb78294F96B0cFa33c92bed7D75F96a)
        ];
        delete memberSet;
        for (uint256 i = 0; i < initMembers.length; i++) {
            memberSet.push(initMembers[i]);
            members[initMembers[i]] = memberSet.length;
        }
    }

    function resetMembers(address[] calldata newMembers) external {
        delete memberSet;
        for (uint256 i = 0; i < newMembers.length; i++) {
            memberSet.push(newMembers[i]);
            members[newMembers[i]] = memberSet.length;
        }
    }

    function _votingPeriod() internal override view returns (uint256) {
        return MOCK_VOTING_PERIOD;
    }

    function _executingPeriod() internal override view returns (uint256) {
        return MOCK_EXECUTING_PERIOD;
    }

    function _initMembers() internal override view returns (bytes memory) {
        return MOCK_INIT_MEMBERS;
    }

    function _updateAddressesAlreadyCalled() internal override view returns (bool) {
        return false;
    }

    function _isValidMember() internal override view returns (bool) {
        return true;
    }

    function _testModeAddressesWereSet() internal override view returns (bool) {
        return false;
    }

    function _gasPriceIsZero() internal override view returns (bool) {
        return true;
    }
}
