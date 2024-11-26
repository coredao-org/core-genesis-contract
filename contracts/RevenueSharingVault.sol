// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./lib/Address.sol";
import "./base/GovernanceDelegateManaged.sol";
import "./base/ReentryGuardUpgradeable.sol";

// pool semantics - incoming funds not attached to a specific address
contract RevenueSharingVault is GovernanceDelegateManaged, ReentryGuardUpgradeable {
	
    event FundsReceived(address indexed sender, uint indexed value);
    event RevenueExtracted(address indexed to, uint indexed sum);
    event RevenueTargetSet(address indexed target);
    event RevenueTargetBalanceIncreased(address indexed target, uint indexed addToBalance);
    event RevenueTargetAddressUpdated(address indexed oldTargetAddress, address indexed newTargetAddress, uint indexed balance);

    struct RevenueTarget {
        bool isSet;
        uint balance;
    }

    mapping(address => RevenueTarget) public targetBalance;

    function init() external onlyNotInit {
        __ReentrancyGuard_init();
        alreadyInit = true;
        // governanceDelegate must be set for contract to become functional
    }

    receive() external payable {
        emit FundsReceived(msg.sender, msg.value);
    }

    function setRevenueTarget(address target) external onlyGovDelegate {
        require(target != address(0), "null address");
        require(!targetBalance[target].isSet, "address already set");
        targetBalance[target] = RevenueTarget({isSet: true, balance: 0});
        emit RevenueTargetSet(target);
    }

    function updateRevenueTargetAddress(address oldTargetAddress, address newTargetAddress) external onlyGovDelegate {
        // mainly for disaster recovery 
        require(targetBalance[oldTargetAddress].isSet, "old target not found");
        require(newTargetAddress != address(0), "null address");
        require(!targetBalance[newTargetAddress].isSet, "new target already set");
        uint balance = targetBalance[oldTargetAddress].balance;
        targetBalance[newTargetAddress] = RevenueTarget({isSet: true, balance: balance});
        delete targetBalance[oldTargetAddress];
        require(!targetBalance[oldTargetAddress].isSet, "target removal failed"); // sanity check        
        emit RevenueTargetAddressUpdated(oldTargetAddress, newTargetAddress, balance);
    }

    function increaseRevenueTargetBalance(address target, uint addToBalance) external onlyGovDelegate {
        // no CORE transfer, rather increase 'virtual' balance
        require(targetBalance[target].isSet, "not a valid target");
        targetBalance[target].balance += addToBalance;
        emit RevenueTargetBalanceIncreased(target, addToBalance);
    }

    function extractRevenue(uint sum) external nonReentrant {
        // called by RevenueTarget to extract allocated revenues
        require(targetBalance[msg.sender].isSet, "not a target");
        require(targetBalance[msg.sender].balance >= sum, "not enough revenues in target account");
        Address.sendValue(payable(msg.sender), sum); // @attack: DoS will only affect the paid user hence meaningless
        emit RevenueExtracted(msg.sender, sum);
    }
}
