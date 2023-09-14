pragma solidity 0.8.4;

contract BaseProxy {
    address public impl;

    constructor(address _impl) { impl = _impl; }

    function _getRevertMsg(bytes memory _returnData) internal pure returns(string memory) {
        if (_returnData.length < 68) return 'Transaction reverted silently';
        assembly {
            _returnData := add(_returnData, 0x04)
        }
        return abi.decode(_returnData, (string));
    }

    function _call(bytes memory _payload) virtual internal returns(bool, string memory) {
        (bool success, bytes memory returnData) = impl.call{value: msg.value}(_payload);
        string memory _msg;
        if (!success) _msg =_getRevertMsg(returnData);
        return (success, _msg);
    }
}
