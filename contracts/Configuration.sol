// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/Memory.sol";
import "./lib/RLPDecode.sol";

/**
 * @title Configuration
 * @dev Contract for managing discount configurations with multiple reward addresses and percentages.
 */
contract Configuration is System {
    using RLPDecode for bytes;
    using RLPDecode for RLPDecode.Iterator;
    using RLPDecode for RLPDecode.RLPItem;

    /// @dev Struct to store reward address and its percentage. 
    struct Reward {
        address rewardAddress;
        uint256 rewardPercentage; 
    }

    // Governance-controlled minimum
    uint256 public minimumValidatorShare;

    // DAO Address
    address public daoAddress;

    /// @dev Struct to store discount configuration details.
    struct DiscountConfig {
        uint256 discountRate;
        uint256 userDiscountRate;
        bool isActive;
        uint256 timestamp;
        address discountAddress; 
        uint256 minimumValidatorShare;
        bool isEOADiscount;
        Reward[] rewards;  // List of reward addresses and their percentages
    }

    // Constants
    uint256 public constant DENOMINATOR = 10000;   

    uint256 public constant MINIMUM_VALIDATOR_SHARE = 1000;

    uint256 public constant MAX_REWARD_ADDRESS = 5;

    uint256 public maxRewardAddress;

    bool private isEOADiscountSet;

    DiscountConfig[] public discountConfigs;

    mapping(address => uint256) public issuerDiscountCount;  

    // Events
    event DiscountAdded(address indexed contractAddress, uint256 discountRate, uint256 userDiscountRate, uint256 timestamp);
    event DiscountRemoved(address indexed contractAddress);
    event DiscountUpdated(address indexed contractAddress, uint256 oldRate, uint256 newRate);
    event DiscountStatusChanged(address indexed contractAddress, bool isActive);
    event IssuerRemoved(address indexed contractAddress, address indexed issuer);

    // Errors
    error InvalidDiscountRate(uint256 rate);
    error AddressAlreadyExists(address addr);
    error AddressNotFound(address addr);
    error InvalidIssuer(address issuer);
    error TooManyIssuers();
    error IssuerAlreadyExists(address issuer);
    error IssuerNotFound(address issuer);
    error NoIssuersProvided();
    error InvalidRewardPercentage(uint256 percentage);
    error EOADiscountAlreadySet();

    // Modifier to restrict access to DAO
    modifier onlyDAO() {
        require(msg.sender == daoAddress, "Caller is not the DAO");
        _;
    }

    /**
     * @dev Initializes the contract. Can only be called once.
     */
    function init() external onlyNotInit {
        alreadyInit = true;
        maxRewardAddress = MAX_REWARD_ADDRESS;
        minimumValidatorShare = MINIMUM_VALIDATOR_SHARE;
    }


    // Helper function to find a config by address
    function _findConfigIndex(address contractAddr) internal view returns (uint256) {
        for (uint256 i = 0; i < discountConfigs.length; i++) {
            if (discountConfigs[i].discountAddress == contractAddr) {
                return i;
            }
        }
        revert AddressNotFound(contractAddr);
    }


    /**
     * @dev Updates a parameter based on the provided key and value.
     * @param key The parameter key to update.
     * @param value The encoded value for the parameter.
     */
    function updateParam(string calldata key, bytes calldata value) external onlyInit onlyGov {
        if (Memory.compareStrings(key, "addDiscount")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 5) revert MismatchParamLength(key);

            address contractAddr = items[0].toAddress();
            uint256 discountRate = items[1].toUint();
            uint256 userDiscountRate = items[2].toUint();
            RLPDecode.RLPItem[] memory rewardsItems = items[3].toList();
            bool isEOADiscount = items[4].toBoolean();
            Reward[] memory rewards = new Reward[](rewardsItems.length);
            uint256 totalPercentage;
            for (uint i = 0; i < rewardsItems.length; i++) {
                RLPDecode.RLPItem[] memory rewardItem = rewardsItems[i].toList();
                rewards[i] = Reward({
                    rewardAddress: rewardItem[0].toAddress(),
                    rewardPercentage: rewardItem[1].toUint()
                });
                totalPercentage += rewards[i].rewardPercentage;
            }

            _addDiscount(contractAddr, discountRate, userDiscountRate, isEOADiscount, rewards);
        } else if (Memory.compareStrings(key, "removeDiscount")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key); 
            address contractAddr = items[0].toAddress();
            _removeDiscount(contractAddr);
        } else if (Memory.compareStrings(key, "updateDiscount")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 4) revert MismatchParamLength(key); // Updated length check

            address contractAddr = items[0].toAddress();
            uint256 newRate = items[1].toUint();
            uint256 newUserDiscountRate = items[2].toUint();
            RLPDecode.RLPItem[] memory rewardsItems = items[3].toList(); // New rewards items

            Reward[] memory newRewards = new Reward[](rewardsItems.length); // Create new rewards array
            for (uint i = 0; i < rewardsItems.length; i++) {
                RLPDecode.RLPItem[] memory rewardItem = rewardsItems[i].toList();
                newRewards[i] = Reward({
                    rewardAddress: rewardItem[0].toAddress(),
                    rewardPercentage: rewardItem[1].toUint()
                });
            }
            _updateDiscountRate(contractAddr, newRate, newUserDiscountRate, newRewards); 
        } else if (Memory.compareStrings(key, "removeIssuer")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 2) revert MismatchParamLength(key);
            address contractAddr = items[0].toAddress();
            address issuer = items[1].toAddress();
            _removeIssuer(contractAddr, issuer);
        } else if (Memory.compareStrings(key, "setDAOAddress")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key); 
            daoAddress = items[0].toAddress();
        } else if (Memory.compareStrings(key, "setDiscountStatus")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 2) revert MismatchParamLength(key);

            address contractAddr = items[0].toAddress();
            bool isActive = items[1].toBoolean();
            _setDiscountStatus(contractAddr, isActive);
        } else if (Memory.compareStrings(key, "updatedMaximumRewardAddress")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxRewardAddress = items[0].toUint();
            maxRewardAddress = newMaxRewardAddress;
        } else if (Memory.compareStrings(key, "updateMinimumValidatorShare")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMinimumValidatorShare = items[0].toUint();
            require(newMinimumValidatorShare >= MINIMUM_VALIDATOR_SHARE, "Minimum validator sharecannot be below hardcoded limit");
            minimumValidatorShare = newMinimumValidatorShare;
        } else {
            revert UnsupportedGovParam(key);
        }
    }
    
    
    /**
     * @dev Internal function to validate the discount rate.
     * @param discountRate The discount rate to validate.
     */
    function _validateDiscountRate(uint256 discountRate) internal view {
        require(discountRate <= (DENOMINATOR - minimumValidatorShare), "Discount rate exceeds allowed limit");
    }


   /**
     * @dev Internal function to add a discount configuration.
     * @param contractAddr The address of the contract to add the discount to.
     * @param discountRate The discount rate to apply.
     * @param userDiscountRate The user discount rate to apply.
     * @param rewards The list of reward addresses and their percentages.
     */
    function _addDiscount(
        address contractAddr,
        uint256 discountRate,
        uint256 userDiscountRate,
        bool isEOADiscount,
        Reward[] memory rewards
    ) internal {
        _validateDiscountRate(discountRate);
        if(maxRewardAddress == 0) {
            maxRewardAddress = MAX_REWARD_ADDRESS;
        }
        if(rewards.length > maxRewardAddress) {
            revert TooManyIssuers();
        }

        // Check if the discount configuration for the given contract already exists.
        for (uint i = 0; i < discountConfigs.length; i++) {
            if (discountConfigs[i].discountAddress == contractAddr) {
                revert AddressAlreadyExists(contractAddr);
            }
        }

        if (isEOADiscount && isEOADiscountSet) {
            revert EOADiscountAlreadySet();
        } else if (isEOADiscount && !isEOADiscountSet) {
            isEOADiscountSet = true;
        }

        // Validate rewards and calculate total percentage.
        uint256 totalPercentage;
        for (uint i = 0; i < rewards.length; i++) {
            if (rewards[i].rewardAddress == address(0)) revert InvalidIssuer(rewards[i].rewardAddress);
            if (rewards[i].rewardPercentage == 0 || rewards[i].rewardPercentage > discountRate) {
                revert InvalidRewardPercentage(rewards[i].rewardPercentage);
            }
            totalPercentage += rewards[i].rewardPercentage;
        }

        // Ensure total percentage + userDiscountRate equals discountRate.
        if (totalPercentage + userDiscountRate != discountRate || discountRate >= DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }

        DiscountConfig storage p = discountConfigs.push();
        p.discountRate = discountRate;
        p.userDiscountRate = userDiscountRate;
        p.isActive = true;
        p.timestamp = block.timestamp;
        p.discountAddress = contractAddr;
        if(minimumValidatorShare == 0) {
            p.minimumValidatorShare = MINIMUM_VALIDATOR_SHARE;
        } else {
            p.minimumValidatorShare = minimumValidatorShare;
        }

        p.isEOADiscount = isEOADiscount;

        // Initialize the rewards array in storage.
        for (uint i = 0; i < rewards.length; i++) {
            // Create a new Reward struct in storage and assign values.
            Reward memory newReward = Reward({
                rewardAddress: rewards[i].rewardAddress,
                rewardPercentage: rewards[i].rewardPercentage
            });
            p.rewards.push(newReward);
        }

        emit DiscountAdded(contractAddr, discountRate, userDiscountRate, block.timestamp);
    }


    /**
     * @dev Internal function to remove a discount configuration.
     * @param contractAddr The address of the contract to remove the discount from.
     */
    function _removeDiscount(address contractAddr) internal {
        uint256 index = _findConfigIndex(contractAddr);

        // Remove by swapping with the last element
        discountConfigs[index] = discountConfigs[discountConfigs.length - 1];
        discountConfigs.pop();

        emit DiscountRemoved(contractAddr);
    }

    /**
     * @dev Internal function to remove an issuer from a discount configuration.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer to remove.
     */
    function _removeIssuer(address contractAddr, address issuer) internal {
        uint256 index = _findConfigIndex(contractAddr);
        DiscountConfig storage config = discountConfigs[index];

        bool found = false;
        for (uint i = 0; i < config.rewards.length; i++) {
            if (config.rewards[i].rewardAddress == issuer) {
                config.rewards[i] = config.rewards[config.rewards.length - 1];
                config.rewards.pop();
                found = true;
                break;
            }
        }

        if (!found) revert IssuerNotFound(issuer);

        emit IssuerRemoved(contractAddr, issuer);
    }

    /**
     * @dev Internal function to update the discount rate and user discount rate of a configuration.
     * @param contractAddr The address of the contract.
     * @param newDiscountRate The new discount rate to set.
     * @param newUserDiscountRate The new user discount rate to set.
     * @param newRewards The new list of rewards to set.
     */
    function _updateDiscountRate(
        address contractAddr,
        uint256 newDiscountRate,
        uint256 newUserDiscountRate,
        Reward[] memory newRewards
    ) internal {
        _validateDiscountRate(newDiscountRate);
        uint256 index = _findConfigIndex(contractAddr);
        DiscountConfig storage config = discountConfigs[index];

        uint256 oldRate = config.discountRate;
        config.discountRate = newDiscountRate;
        config.userDiscountRate = newUserDiscountRate;

        // Clear existing rewards
        delete config.rewards;

        uint256 totalPercentage;

        if(maxRewardAddress == 0) {
            maxRewardAddress = MAX_REWARD_ADDRESS;
        }

        if(newRewards.length > maxRewardAddress) {
            revert TooManyIssuers();
        }

        for (uint i = 0; i < newRewards.length; i++) {
            if (newRewards[i].rewardAddress == address(0)) revert InvalidIssuer(newRewards[i].rewardAddress);
            totalPercentage += newRewards[i].rewardPercentage;
            config.rewards.push(newRewards[i]); // Push each reward to storage
        }

        // Check that the total percentage plus user discount rate equals the new discount rate
        if (totalPercentage + newUserDiscountRate != newDiscountRate || newDiscountRate >= DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }

        config.timestamp = block.timestamp;
        emit DiscountUpdated(contractAddr, oldRate, newDiscountRate);
    }

    /**
     * @dev Internal function to set the active status of a discount configuration.
     * @param contractAddr The address of the contract.
     * @param isActive The new active status to set.
     */
    function _setDiscountStatus(address contractAddr, bool isActive) internal {
        uint256 index = _findConfigIndex(contractAddr);
        DiscountConfig storage config = discountConfigs[index];

        config.isActive = isActive;
        config.timestamp = block.timestamp;

        emit DiscountStatusChanged(contractAddr, isActive);
    }

    // Function to get all discount configurations
    function getAllDiscountConfigs() public view returns (DiscountConfig[] memory) {
        return discountConfigs;
    }

    // Function to get the discount configuration for a given contract address
    function getDiscountConfig(address contractAddr) external view returns (
        uint256 discountRate,
        uint256 userDiscountRate,
        bool isActive,
        uint256 timestamp,
        address discountAddress,
        bool isEOADiscount,
        uint256 minimumValidatorSharesOfValidator,
        Reward[] memory rewards
    ) {
        uint256 index = _findConfigIndex(contractAddr);
        DiscountConfig storage config = discountConfigs[index];
        
        return (
            config.discountRate,
            config.userDiscountRate,
            config.isActive,
            config.timestamp,
            config.discountAddress,
            config.isEOADiscount,
            config.minimumValidatorShare,
            config.rewards
        );
    }

    /**
     * @dev Checks if an address is an issuer for a given discount configuration.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer.
     * @return True if the address is an issuer, false otherwise.
     */
    function isIssuerForDiscount(address contractAddr, address issuer) external view returns (bool) {
        uint256 index = _findConfigIndex(contractAddr);
        DiscountConfig storage config = discountConfigs[index];
        for (uint i = 0; i < config.rewards.length; i++) {
            if (config.rewards[i].rewardAddress == issuer) {
                return true;
            }
        }
        return false;
    }

    /**
     * @dev External function for the DAO to add a discount.
     * @param contractAddr The address of the contract to add the discount to.
     * @param discountRate The discount rate to apply.
     * @param userDiscountRate The user discount rate to apply.
     * @param rewards The list of reward addresses and their percentages.
     */
    function addDiscount(
        address contractAddr,
        uint256 discountRate,
        uint256 userDiscountRate,
        bool isEOADiscount,
        Reward[] memory rewards
    ) external onlyDAO onlyInit {
        _addDiscount(contractAddr, discountRate, userDiscountRate, isEOADiscount, rewards);
    }

    /**
     * @dev External function for the DAO to remove a discount.
     * @param contractAddr The address of the contract to remove the discount from.
     */
    function removeDiscount(address contractAddr) external onlyDAO onlyInit {
        _removeDiscount(contractAddr);
    }

    /**
     * @dev External function for the DAO to update a discount.
     * @param contractAddr The address of the contract to update the discount for.
     * @param newRate The new discount rate to set.
     * @param newUserDiscountRate The new user discount rate to set.
     * @param newRewards The new list of rewards to set.
     */
    function updateDiscount (
        address contractAddr,
        uint256 newRate,
        uint256 newUserDiscountRate,
        Reward[] memory newRewards
    ) external onlyDAO onlyInit {
        _updateDiscountRate(contractAddr, newRate, newUserDiscountRate, newRewards);
    }

}