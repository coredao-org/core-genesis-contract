pragma solidity 0.8.4;
import "../lib/Memory.sol";

contract TestLibMemory {
    function testCopy(bytes memory input, uint len) public pure returns(bytes memory output) {
        output = new bytes(len);
        uint src = Memory.dataPtr(input);
        uint dest;
        assembly {
            dest := add(output, 0x20)
        }
        Memory.copy(src, dest, len);
    }
}
