// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./lib/Address.sol";
import "./base/ReentryGuardUpgradeable.sol";
import "./base/GovernanceDelegateManaged.sol";

// pool semantics - incoming funds not attached to a specific address
contract RevenueSharingVault is GovernanceDelegateManaged, ReentryGuardUpgradeable { 

    using Address for address;

    event FundsReceived(address indexed sender, uint indexed value);
    event FundsSent(address indexed to, uint indexed sum);

	function init() external onlyNotInit {
		__ReentrancyGuard_init();
		alreadyInit = true;
		// governanceDelegate must be set for contract to become functional
	}

	receive() external payable {
		emit FundsReceived(msg.sender, msg.value);
	}

	function distributeFunds(address to, uint sum) external onlyGovDelegate nonReentrant  {
		require(to != address(0), "destination address not set");
		Address.sendValue(payable(to), sum); // @attack: DoS will only affect the paid user hence meaningless
		emit FundsSent(to, sum);
	}
}
