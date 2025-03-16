// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/Memory.sol";
import "./lib/RLPDecode.sol";

/**
 * @title Configuration
 * @dev Contract for managing configs with multiple reward addresses and percentages.
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

    // DAO Address
    address public daoAddress;

    /// @dev Struct to store config details.
    struct Config {
        uint256 configRate;
        uint256 userConfigRate;
        bool isActive;
        address configAddress; 
        Reward[] rewards;  // List of reward addresses and their percentages
    }

    // Constants
    uint256 public constant DENOMINATOR = 10000;   

    uint256 public constant MAX_REWARD_ADDRESS = 5;

    uint256 public maxRewardAddress;

    Config[] public configs;

    // Events
    event ConfigAdded(address indexed contractAddress, uint256 configRate, uint256 userConfigRate);
    event ConfigRemoved(address indexed contractAddress);
    event ConfigUpdated(address indexed contractAddress, uint256 oldRate, uint256 newRate);
    event ConfigStatusChanged(address indexed contractAddress, bool isActive);
    event IssuerRemoved(address indexed contractAddress, address indexed issuer);

    // Errors
    error InvalidConfigRate(uint256 rate);
    error AddressAlreadyExists(address addr);
    error AddressNotFound(address addr);
    error InvalidIssuer(address issuer);
    error TooManyIssuers();
    error IssuerNotFound(address issuer);
    error InvalidRewardPercentage(uint256 percentage);
    error EOAConfigAlreadySet();

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
    }


    // Helper function to find a config by address
    function _findConfigIndex(address contractAddr) internal view returns (uint256) {
        for (uint256 i = 0; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
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
        if (Memory.compareStrings(key, "addConfig")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 5) revert MismatchParamLength(key);

            address contractAddr = items[0].toAddress();
            uint256 configRate = items[1].toUint();
            uint256 userConfigRate = items[2].toUint();
            RLPDecode.RLPItem[] memory rewardsItems = items[3].toList();
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

            _addConfig(contractAddr, configRate, userConfigRate, rewards);
        } else if (Memory.compareStrings(key, "removeConfig")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key); 
            address contractAddr = items[0].toAddress();
            _removeConfig(contractAddr);
        } else if (Memory.compareStrings(key, "updateConfig")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 4) revert MismatchParamLength(key); // Updated length check

            address contractAddr = items[0].toAddress();
            uint256 newRate = items[1].toUint();
            uint256 newUserConfigRate = items[2].toUint();
            RLPDecode.RLPItem[] memory rewardsItems = items[3].toList(); // New rewards items

            Reward[] memory newRewards = new Reward[](rewardsItems.length); // Create new rewards array
            for (uint i = 0; i < rewardsItems.length; i++) {
                RLPDecode.RLPItem[] memory rewardItem = rewardsItems[i].toList();
                newRewards[i] = Reward({
                    rewardAddress: rewardItem[0].toAddress(),
                    rewardPercentage: rewardItem[1].toUint()
                });
            }
            _updateConfigRate(contractAddr, newRate, newUserConfigRate, newRewards); 
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
        } else if (Memory.compareStrings(key, "setConfigStatus")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 2) revert MismatchParamLength(key);

            address contractAddr = items[0].toAddress();
            bool isActive = items[1].toBoolean();
            _setConfigStatus(contractAddr, isActive);
        } else if (Memory.compareStrings(key, "updatedMaximumRewardAddress")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxRewardAddress = items[0].toUint();
            maxRewardAddress = newMaxRewardAddress;
        }  else {
            revert UnsupportedGovParam(key);
        }
    }

   /**
     * @dev Internal function to add a config.
     * @param contractAddr The address of the contract to add the config to.
     * @param configRate The config rate to apply.
     * @param userConfigRate The user config rate to apply.
     * @param rewards The list of reward addresses and their percentages.
     */
    function _addConfig(
        address contractAddr,
        uint256 configRate,
        uint256 userConfigRate,
        Reward[] memory rewards
    ) internal {
        if(maxRewardAddress == 0) {
            maxRewardAddress = MAX_REWARD_ADDRESS;
        }
        if(rewards.length > maxRewardAddress) {
            revert TooManyIssuers();
        }

        // Check if the config for the given contract already exists.
        for (uint i = 0; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
                revert AddressAlreadyExists(contractAddr);
            }
        }

        // Validate rewards and calculate total percentage.
        uint256 totalPercentage;
        for (uint i = 0; i < rewards.length; i++) {
            if (rewards[i].rewardAddress == address(0)) revert InvalidIssuer(rewards[i].rewardAddress);
            if (rewards[i].rewardPercentage == 0 || rewards[i].rewardPercentage > configRate) {
                revert InvalidRewardPercentage(rewards[i].rewardPercentage);
            }
            totalPercentage += rewards[i].rewardPercentage;
        }

        // Ensure total percentage + userConfigRate equals configRate.
        if (totalPercentage + userConfigRate != configRate || configRate >= DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }

        Config storage p = configs.push();
        p.configRate = configRate;
        p.userConfigRate = userConfigRate;
        p.isActive = true;
        p.configAddress = contractAddr;


        // Initialize the rewards array in storage.
        for (uint i = 0; i < rewards.length; i++) {
            // Create a new Reward struct in storage and assign values.
            Reward memory newReward = Reward({
                rewardAddress: rewards[i].rewardAddress,
                rewardPercentage: rewards[i].rewardPercentage
            });
            p.rewards.push(newReward);
        }

        emit ConfigAdded(contractAddr, configRate, userConfigRate);
    }


    /**
     * @dev Internal function to remove a config.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function _removeConfig(address contractAddr) internal {
        uint256 index = _findConfigIndex(contractAddr);

        // Remove by swapping with the last element
        configs[index] = configs[configs.length - 1];
        configs.pop();

        emit ConfigRemoved(contractAddr);
    }

    /**
     * @dev Internal function to remove an issuer from a config.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer to remove.
     */
    function _removeIssuer(address contractAddr, address issuer) internal {
        uint256 index = _findConfigIndex(contractAddr);
        Config storage config = configs[index];

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
     * @dev Internal function to update the config rate and user config rate of a configuration.
     * @param contractAddr The address of the contract.
     * @param newConfigRate The new config rate to set.
     * @param newUserConfigRate The new user config rate to set.
     * @param newRewards The new list of rewards to set.
     */
    function _updateConfigRate(
        address contractAddr,
        uint256 newConfigRate,
        uint256 newUserConfigRate,
        Reward[] memory newRewards
    ) internal {
        uint256 index = _findConfigIndex(contractAddr);
        Config storage config = configs[index];

        uint256 oldRate = config.configRate;
        config.configRate = newConfigRate;
        config.userConfigRate = newUserConfigRate;

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

        // Check that the total percentage plus user config rate equals the new config rate
        if (totalPercentage + newUserConfigRate != newConfigRate || newConfigRate >= DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }

        emit ConfigUpdated(contractAddr, oldRate, newConfigRate);
    }

    /**
     * @dev Internal function to set the active status of a config.
     * @param contractAddr The address of the contract.
     * @param isActive The new active status to set.
     */
    function _setConfigStatus(address contractAddr, bool isActive) internal {
        uint256 index = _findConfigIndex(contractAddr);
        Config storage config = configs[index];

        config.isActive = isActive;
        emit ConfigStatusChanged(contractAddr, isActive);
    }

    // Function to get all configs
    function getAllconfigs() public view returns (Config[] memory) {
        return configs;
    }

    // Function to get the config for a given contract address
    function getConfig(address contractAddr) external view returns (
        uint256 configRate,
        uint256 userConfigRate,
        bool isActive,
        address configAddress,
        Reward[] memory rewards
    ) {
        uint256 index = _findConfigIndex(contractAddr);
        Config storage config = configs[index];
        
        return (
            config.configRate,
            config.userConfigRate,
            config.isActive,
            config.configAddress,
            config.rewards
        );
    }

    /**
     * @dev Checks if an address is an issuer for a given config.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer.
     * @return True if the address is an issuer, false otherwise.
     */
    function isIssuerForConfig(address contractAddr, address issuer) external view returns (bool) {
        uint256 index = _findConfigIndex(contractAddr);
        Config storage config = configs[index];
        for (uint i = 0; i < config.rewards.length; i++) {
            if (config.rewards[i].rewardAddress == issuer) {
                return true;
            }
        }
        return false;
    }

    /**
     * @dev External function for the DAO to add a config.
     * @param contractAddr The address of the contract to add the config to.
     * @param configRate The config rate to apply.
     * @param userConfigRate The user config rate to apply.
     * @param rewards The list of reward addresses and their percentages.
     */
    function addConfig(
        address contractAddr,
        uint256 configRate,
        uint256 userConfigRate,
        Reward[] memory rewards
    ) external onlyDAO onlyInit {
        _addConfig(contractAddr, configRate, userConfigRate, rewards);
    }

    /**
     * @dev External function for the DAO to remove a config.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function removeConfig(address contractAddr) external onlyDAO onlyInit {
        _removeConfig(contractAddr);
    }

    /**
     * @dev External function for the DAO to update a config.
     * @param contractAddr The address of the contract to update the config for.
     * @param newRate The new config rate to set.
     * @param newUserConfigRate The new user config rate to set.
     * @param newRewards The new list of rewards to set.
     */
    function updateConfig (
        address contractAddr,
        uint256 newRate,
        uint256 newUserConfigRate,
        Reward[] memory newRewards
    ) external onlyDAO onlyInit {
        _updateConfigRate(contractAddr, newRate, newUserConfigRate, newRewards);
    }

}
