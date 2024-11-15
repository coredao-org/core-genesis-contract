// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../lib/Memory.sol";
import "../lib/BytesToTypes.sol";
import "../interface/ILightClient.sol";
import "../interface/ICandidateHub.sol";
import "../interface/ISystemReward.sol";
import "../interface/IParamSubscriber.sol";                  
import "../System.sol";

abstract contract GovernanceDelegateManaged is System, IParamSubscriber {
    address private govDelegate;
	uint[16] private __gap; // allow adding state without breaking derived contracts

	event SetGovernanceDelegate(address indexed oldDelegate, address indexed newDelegate);

	modifier onlyGovDelegate() {
        require(_wasInitialized()); // govDelegate is set after init
        require(msg.sender == govDelegate); // @attacks: govDelegate not yet set -> affectively render contract as paused
        _;
  	}

    function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
        if (value.length != 32) {
            revert MismatchParamLength(key);
        }
        if (Memory.compareStrings(key, "governanceDelegate")) {
            address newDelegate = BytesToTypes.bytesToAddress(32, value);
            _setGovernanceDelegate(newDelegate);
        } else {
            require(false, "unknown param");
        }
    }

    function _setGovernanceDelegate(address newDelegate) private {
		// newDelegate can be set to zero which will result in temporary cancellation of governanceDelegate
		address oldDelegate = govDelegate;
		govDelegate = newDelegate;
		emit SetGovernanceDelegate(oldDelegate, govDelegate);
    }

	function governanceDelegate() public view returns(address) {
		return govDelegate;
	}

	function _wasInitialized() internal view returns(bool) {
		return alreadyInit;
	}
}
