// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import {console} from "forge-std/console.sol";
import {BaseTest} from "../common/BaseTest.t.sol";
import {CandidateHub} from "../../contracts/CandidateHub.sol";

contract CandidateHubTest is BaseTest  {
    uint256 private constant INIT_REQUIRED_MARGIN = 1e22;

    CandidateHub private s_candidateHub;

    constructor() BaseTest(REJECT_PAYMENTS) {} 

	function setUp() public override {
	    BaseTest.setUp();
        s_candidateHub = CandidateHub(s_deployer.CANDIDATE_HUB_ADDR());
	}

    function testFuzz_register(uint32 commissionThousandths, uint value) public {
        _register(commissionThousandths, value);
    }

    function testFuzz_unregister(uint32 commissionThousandths, uint value) public {
        address candidate = _register(commissionThousandths, value);
        _hoaxWithGas(candidate);
        s_candidateHub.unregister();
    }

    function testFuzz_refuseDelegate(uint32 commissionThousandths, uint value) public {
        address candidate = _register(commissionThousandths, value);
        _hoaxWithGas(candidate);
        s_candidateHub.refuseDelegate();
    }

    function testFuzz_acceptDelegate(uint32 commissionThousandths, uint value) public {
        address candidate = _register(commissionThousandths, value);
        _hoaxWithGas(candidate);
        s_candidateHub.acceptDelegate();
    }

    function testFuzz_addMargin(uint32 commissionThousandths, uint value, uint marginValue) public {
        marginValue = bound(marginValue, 1, 1000 ether); // positive else revert in s_candidateHub.addMargin()
        address candidate = _register(commissionThousandths, value);
        _hoaxWithGas(candidate, marginValue);
        s_candidateHub.addMargin{value: marginValue}();
    }

    function testFuzz_jailValidator(uint32 commissionThousandths, uint value, uint256 round, uint256 fine) public {
        address candidate = _register(commissionThousandths, value);
        round = bound(round, 0, 1_000_000);
        fine = bound(fine, 0, 100 ether);
        _hoaxWithGas(s_deployer.VALIDATOR_CONTRACT_ADDR()); // only validator may call jailValidator()
        s_candidateHub.jailValidator(candidate, round, fine);
    }

    // function testFuzz_turnRound(uint validatorSetBalance) public {
    //     validatorSetBalance = bound(validatorSetBalance, 1, 1000 ether); // must be positive else revert in validatorSet().distributeReward()
    //     _hoaxWithGas(block.coinbase);         
    //     vm.deal(s_deployer.VALIDATOR_CONTRACT_ADDR(), validatorSetBalance);
    //     s_candidateHub.turnRound();
    // }

    function _register(uint32 commissionThousandths, uint value) private returns(address candidate){
        value = bound(value, INIT_REQUIRED_MARGIN+1, 10*INIT_REQUIRED_MARGIN); // onlyIfValueExceedsMargin()
        commissionThousandths = uint32(bound(commissionThousandths, 1, 1000-1)); // valid value: opern interval (0, 1000)
        address payable feeAddr = payable(makeAddr("feeAddr"));
        address consensusAddr = makeAddr("consensusAddr");
        candidate = makeAddr("candidate");
        _hoaxWithGas(candidate, value); 
        s_candidateHub.register{value: value}(consensusAddr, feeAddr, commissionThousandths);
    }
}

