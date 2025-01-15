pragma solidity 0.8.4;

contract BaseProxy {
    address public impl;
    address public stakeHub;

    constructor(address _impl, address _stakeHub) {impl = _impl;
        stakeHub = _stakeHub;}

    function _getRevertMsg(bytes memory _returnData) internal pure returns (string memory) {
        if (_returnData.length < 68) return 'Transaction reverted silently';
        assembly {
            _returnData := add(_returnData, 0x04)
        }
        return abi.decode(_returnData, (string));
    }

    function _call(bytes memory _payload) virtual internal returns (bool, string memory) {
        (bool success, bytes memory returnData) = impl.call{value: msg.value}(_payload);
        string memory _msg;
        if (!success) _msg = _getRevertMsg(returnData);
        return (success, _msg);
    }
    function _callC(bytes memory _payload) virtual internal returns (bool, string memory) {
        (bool success, bytes memory returnData) = stakeHub.call{value: msg.value}(_payload);
        string memory _msg;
        if (!success) _msg = _getRevertMsg(returnData);
        return (success, _msg);
    }
}
