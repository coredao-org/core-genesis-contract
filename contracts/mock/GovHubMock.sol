pragma experimental ABIEncoderV2;
pragma solidity ^0.6.4;

import "../GovHub.sol";

contract GovHubMock is GovHub {
    constructor() GovHub() public {}

    function developmentInit() external {
        votingPeriod = 20;
        bytes memory initMembers = hex"ea949fB29AAc15b9A4B7F17c3385939b007540f4d7919496C42C56fdb78294F96B0cFa33c92bed7D75F96a";
        delete memberSet;
        RLPDecode.RLPItem[] memory items = initMembers.toRLPItem().toList();
        for (uint256 i = 0; i < items.length; i++) {
            address addr = items[i].toAddress();
            memberSet.push(addr);
            members[addr] = memberSet.length;
        }
    }
}
