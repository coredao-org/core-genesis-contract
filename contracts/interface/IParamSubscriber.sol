pragma solidity 0.6.12;

interface IParamSubscriber {
    function updateParam(string calldata key, bytes calldata value) external;
}