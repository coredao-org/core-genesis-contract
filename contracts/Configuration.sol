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
        address rewardAddr;
        uint256 rewardPercentage;
    }

    /// @dev Struct to store event details.
    struct Event {
        Reward[] rewards;
        bytes32 eventSignature;
        uint256 gas;
    }

    /// @dev Struct to store function signature and gas details.
    struct FunctionSignatures {
        Reward[] rewards;
        bytes32 functionSignature;
        uint256 gas;
    }

    /// @dev Struct to store config details.
    struct Config {
        Event[] events;
        FunctionSignatures[] functionSignatures;
        address configAddress;
        bool isActive;
    }

    // DAO Address
    address public daoAddress;

    // Constants
    uint256 public constant DENOMINATOR = 10000;   

    uint256 public constant MAX_REWARD_ADDRESS = 5;

    uint256 public maxRewardAddress;

    Config[] public configs;

    // Event to signal config updates
    event ConfigUpdated(address indexed configAddress, uint256 eventCount, uint256 functionSignatureCount);

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
            if (items.length != 3) revert MismatchParamLength(key); // Updated length check

            address contractAddr = items[0].toAddress();
            RLPDecode.RLPItem[] memory eventsItems = items[1].toList(); // New events items
            RLPDecode.RLPItem[] memory functionSignaturesItems = items[2].toList(); // New function signatures items

            Event[] memory events = new Event[](eventsItems.length);
            for (uint i = 0; i < eventsItems.length; i++) {
                RLPDecode.RLPItem[] memory eventItem = eventsItems[i].toList();
                Reward[] memory rewards = new Reward[](eventItem[0].toList().length);
                for (uint j = 0; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = eventItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: rewardItem[1].toUint()
                    });
                }
                events[i] = Event({
                    rewards: rewards,
                    eventSignature: toBytes32(eventItem[1]),
                    gas: eventItem[2].toUint()
                });
            }

            FunctionSignatures[] memory functionSignatures = new FunctionSignatures[](functionSignaturesItems.length);
            for (uint i = 0; i < functionSignaturesItems.length; i++) {
                RLPDecode.RLPItem[] memory functionItem = functionSignaturesItems[i].toList();
                Reward[] memory rewards = new Reward[](functionItem[0].toList().length);
                for (uint j = 0; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = functionItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: rewardItem[1].toUint()
                    });
                }
                functionSignatures[i] = FunctionSignatures({
                    rewards: rewards,
                    functionSignature: toBytes32(functionItem[1]),
                    gas: functionItem[2].toUint()
                });
            }

            _addConfig(contractAddr, events, functionSignatures, true); // Assuming active status is true
        } else if (Memory.compareStrings(key, "removeConfig")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key); 
            address contractAddr = items[0].toAddress();
            _removeConfig(contractAddr);
        } else if (Memory.compareStrings(key, "updateConfig")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 3) revert MismatchParamLength(key); // Updated length check

            address contractAddr = items[0].toAddress();
            RLPDecode.RLPItem[] memory eventsItems = items[1].toList(); // New events items
            RLPDecode.RLPItem[] memory functionSignaturesItems = items[2].toList(); // New function signatures items

            Event[] memory events = new Event[](eventsItems.length);
            for (uint i = 0; i < eventsItems.length; i++) {
                RLPDecode.RLPItem[] memory eventItem = eventsItems[i].toList();
                Reward[] memory rewards = new Reward[](eventItem[0].toList().length);
                for (uint j = 0; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = eventItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: rewardItem[1].toUint()
                    });
                }
                events[i] = Event({
                    rewards: rewards,
                    eventSignature: toBytes32(eventItem[1]),
                    gas: eventItem[2].toUint()
                });
            }

            FunctionSignatures[] memory functionSignatures = new FunctionSignatures[](functionSignaturesItems.length);
            for (uint i = 0; i < functionSignaturesItems.length; i++) {
                RLPDecode.RLPItem[] memory functionItem = functionSignaturesItems[i].toList();
                Reward[] memory rewards = new Reward[](functionItem[0].toList().length);
                for (uint j = 0; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = functionItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: rewardItem[1].toUint()
                    });
                }
                functionSignatures[i] = FunctionSignatures({
                    rewards: rewards,
                    functionSignature: toBytes32(functionItem[1]),
                    gas: functionItem[2].toUint()
                });
            }

            _updateConfig(contractAddr, events, functionSignatures); 
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
        } else {
            revert UnsupportedGovParam(key);
        }
    }

   /**
     * @dev Internal function to add a config.
     * @param contractAddr The address of the contract to add the config to.
     * @param events The list of events to apply.
     * @param functionSignatures The list of function signatures to apply.
     * @param isActive The active status of the config.
     */
    function _addConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures,
        bool isActive
    ) internal {
        if(maxRewardAddress == 0) {
            maxRewardAddress = MAX_REWARD_ADDRESS;
        }
        if(events.length > maxRewardAddress || functionSignatures.length > maxRewardAddress) {
            revert TooManyIssuers();
        }

        // Check if the config for the given contract already exists.
        for (uint i = 0; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
                revert AddressAlreadyExists(contractAddr);
            }
        }

        Config storage p = configs.push();
        p.events = events;
        p.functionSignatures = functionSignatures;
        p.configAddress = contractAddr;
        p.isActive = isActive;

        emit ConfigUpdated(contractAddr, events.length, functionSignatures.length);
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

        emit ConfigUpdated(contractAddr, 0, 0);
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
        for (uint i = 0; i < config.events.length; i++) {
            for (uint j = 0; j < config.events[i].rewards.length; j++) {
                if (config.events[i].rewards[j].rewardAddr == issuer) {
                    config.events[i].rewards[j] = config.events[i].rewards[config.events[i].rewards.length - 1];
                    config.events[i].rewards.pop();
                    found = true;
                    break;
                }
            }
        }

        for (uint i = 0; i < config.functionSignatures.length; i++) {
            for (uint j = 0; j < config.functionSignatures[i].rewards.length; j++) {
                if (config.functionSignatures[i].rewards[j].rewardAddr == issuer) {
                    config.functionSignatures[i].rewards[j] = config.functionSignatures[i].rewards[config.functionSignatures[i].rewards.length - 1];
                    config.functionSignatures[i].rewards.pop();
                    found = true;
                    break;
                }
            }
        }

        if (!found) revert IssuerNotFound(issuer);

        emit ConfigUpdated(contractAddr, config.events.length, config.functionSignatures.length);
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
        emit ConfigUpdated(contractAddr, config.events.length, config.functionSignatures.length);
    }

    // Function to get all configs
    function getAllconfigs() public view returns (Config[] memory) {
        return configs;
    }

    // Function to get the config for a given contract address
    function getConfig(address contractAddr) external view returns (
        bool isActive,
        address configAddress,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures
    ) {
        for (uint256 i = 0; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
                return (
                    configs[i].isActive,
                    configs[i].configAddress,
                    configs[i].events,
                    configs[i].functionSignatures
                );
            }
        }
        revert("Config not found");
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
        for (uint i = 0; i < config.events.length; i++) {
            for (uint j = 0; j < config.events[i].rewards.length; j++) {
                if (config.events[i].rewards[j].rewardAddr == issuer) {
                    return true;
                }
            }
        }
        for (uint i = 0; i < config.functionSignatures.length; i++) {
            for (uint j = 0; j < config.functionSignatures[i].rewards.length; j++) {
                if (config.functionSignatures[i].rewards[j].rewardAddr == issuer) {
                    return true;
                }
            }
        }
        return false;
    }

    /**
     * @dev External function for the DAO to add a config.
     * @param contractAddr The address of the contract to add the config to.
     * @param events The list of events to apply.
     * @param functionSignatures The list of function signatures to apply.
     */
    function addConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures
    ) external onlyDAO onlyInit {
        _addConfig(contractAddr, events, functionSignatures, true);
    }

    /**
     * @dev External function for the DAO to remove a config.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function removeConfig(address contractAddr) external onlyDAO onlyInit {
        _removeConfig(contractAddr);
    }

    // Example function to retrieve rewards from an event
    function getEventRewards(uint256 configIndex, uint256 eventIndex) external view returns (Reward[] memory) {
        require(configIndex < configs.length, "Config index out of bounds");
        require(eventIndex < configs[configIndex].events.length, "Event index out of bounds");

        return configs[configIndex].events[eventIndex].rewards;
    }

    /**
     * @dev Internal function to update the config with new events and function signatures.
     * @param contractAddr The address of the contract to update the config for.
     * @param events The new list of events to set.
     * @param functionSignatures The new list of function signatures to set.
     */
    function _updateConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures
    ) internal {
        uint256 index = _findConfigIndex(contractAddr); // Assuming you have this function to find the index
        Config storage config = configs[index];

        // Update the events and function signatures
        config.events = events;
        config.functionSignatures = functionSignatures;

        // Emit the ConfigUpdated event
        emit ConfigUpdated(contractAddr, events.length, functionSignatures.length);
    }

    function toBytes32(RLPDecode.RLPItem memory item) internal pure returns (bytes32) {
        bytes memory data = item.toBytes(); // Convert RLPItem to bytes
        require(data.length == 32, "Invalid bytes length for bytes32 conversion");
        bytes32 result;
        assembly {
            result := mload(add(data, 32)) // Load the bytes into a bytes32 variable
        }
        return result;
    }

}
