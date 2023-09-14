pragma solidity 0.8.4;
import "./BaseProxy.sol";

interface ICandidate {
    function requiredMargin() external returns(uint256);
}

contract ReentryCandidateHubProxy is BaseProxy {
    event proxyRegister(address consensusAddr);
    event proxyUnregister(bool success, string msg);

    constructor(address _candidateHub) BaseProxy(_candidateHub) {}

    function register(address consensusAddr, address payable feeAddr, uint32 commissionThousandths)
        external
        payable {
        bytes memory payload = abi.encodeWithSignature(
            "register(address,address,uint32)", consensusAddr, feeAddr, commissionThousandths
        );
        _call(payload);
        emit proxyRegister(consensusAddr);
    }

    function unregister() public {
        bytes memory payload = abi.encodeWithSignature("unregister()");
        (bool success, string memory _msg) = _call(payload);
        emit proxyUnregister(success, _msg);
    }

    function _call(bytes memory _payload) override internal returns(bool, string memory) {
        (bool success, bytes memory returnData) = impl.call(_payload);
        string memory _msg;
        if (!success) _msg =_getRevertMsg(returnData);
        return (success, _msg);
    }
}

contract UnRegisterReentry is ReentryCandidateHubProxy {
    event InReceive();
    constructor(address _candidateHub) ReentryCandidateHubProxy(_candidateHub) {}

    receive() external payable {
        emit InReceive();
        if (impl.balance >= ICandidate(impl).requiredMargin()) unregister();
    }
}
