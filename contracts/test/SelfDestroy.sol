pragma solidity 0.8.4;

contract SelfDestroy {
    function destruct(address payable target) public{
        selfdestruct(target);
    }

    receive() external payable{}
}
