// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/Memory.sol";
import "./lib/RLPDecode.sol";
import "./lib/SatoshiPlusHelper.sol";

/**
 * @title Configuration
 * @dev Contract for managing configurations with multiple reward addresses and percentages.
 */
contract Configuration is System {
    using RLPDecode for bytes;
    using RLPDecode for RLPDecode.Iterator;
    using RLPDecode for RLPDecode.RLPItem;

    /// @dev Struct to store reward address and its percentage.
    struct Reward {
        address rewardAddr;
        uint16 rewardPercentage;
    }

    /// @dev Struct to store event details.
    struct Event {
        bytes32 eventSignature;
        uint32 gas;
        Reward[] rewards;
    }

    /// @dev Struct to store function signature and gas details.
    struct Function {
        bytes32 functionSignature;
        uint32 gas;
        Reward[] rewards;
    }

    /// @dev Struct to store config details.
    struct Config {
        address configAddress;
        bool isActive;
        Event[] events;
        Function[] functions;
    }

    // DAO Address
    address public daoAddress;

    uint256 public MAX_REWARD_ADDRESS;
    uint256 public MAX_EVENTS;
    uint256 public MAX_FUNCTIONS;
    uint256 public MAX_GAS;

    // Replace the array with a mapping and an address array
    address[] public configAddresses;
    mapping(address => Config) public configsMap;

    // Event to signal config updates
    event ConfigUpdated(address indexed configAddress, uint256 eventCount, uint256 functionCount);
    event ConstantUpdated();
    event ConfigRemoved(address indexed configAddress);

    // Errors
    error AddressAlreadyExists(address addr);
    error AddressNotFound(address addr);
    error InvalidIssuer(address issuer);
    error TooManyEvents();
    error TooManyRewardAddresses();
    error InvalidGasValue(uint gas);
    error IssuerNotFound(address issuer);
    error InvalidRewardPercentage(uint256 percentage);

    // Modifier to restrict access to DAO
    modifier onlyDAO() {
        require(msg.sender == daoAddress, "Caller is not the DAO");
        _;
    }

    /**
     * @dev Initializes the contract. Can only be called once.
     */
    function init() external onlyNotInit {
        daoAddress = 0x7e5C92fA765Aac46042AfBba05b0F3846C619423;
        alreadyInit = true;
        MAX_REWARD_ADDRESS = 5;
        MAX_EVENTS = 5;
        MAX_FUNCTIONS = 5;
        MAX_GAS = 1000000;
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

            Event[] memory events = new Event[](eventsItems.length);
            for (uint i; i < eventsItems.length; i++) {
                RLPDecode.RLPItem[] memory eventItem = eventsItems[i].toList();
                Reward[] memory rewards = new Reward[](eventItem[0].toList().length);
                for (uint j; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = eventItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: uint16(rewardItem[1].toUint())
                    });
                }
                events[i] = Event({
                    rewards: rewards,
                    eventSignature: toBytes32(eventItem[1]),
                    gas: uint32(eventItem[2].toUint())
                });
            }

            Function[] memory functions = new Function[](0);

            _addConfig(contractAddr, events, functions, true); // Assuming active status is true
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

            Event[] memory events = new Event[](eventsItems.length);
            for (uint i; i < eventsItems.length; i++) {
                RLPDecode.RLPItem[] memory eventItem = eventsItems[i].toList();
                Reward[] memory rewards = new Reward[](eventItem[0].toList().length);
                for (uint j; j < rewards.length; j++) {
                    RLPDecode.RLPItem[] memory rewardItem = eventItem[0].toList()[j].toList();
                    rewards[j] = Reward({
                        rewardAddr: rewardItem[0].toAddress(),
                        rewardPercentage: uint16(rewardItem[1].toUint())
                    });
                }
                events[i] = Event({
                    rewards: rewards,
                    eventSignature: toBytes32(eventItem[1]),
                    gas: uint32(eventItem[2].toUint())
                });
            }

            Function[] memory functions = new Function[](0);

            _updateConfig(contractAddr, events, functions);
        } else if (Memory.compareStrings(key, "setDAOAddress")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);
            daoAddress = items[0].toAddress();
            emit ConstantUpdated();
        } else if (Memory.compareStrings(key, "setConfigStatus")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 2) revert MismatchParamLength(key);

            address contractAddr = items[0].toAddress();
            bool isActive = items[1].toBoolean();
            _setConfigStatus(contractAddr, isActive);
            emit ConstantUpdated();
        } else if (Memory.compareStrings(key, "updatedMaximumRewardAddress")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxRewardAddress = items[0].toUint();
            MAX_REWARD_ADDRESS = newMaxRewardAddress;
            emit ConstantUpdated();
        } else if (Memory.compareStrings(key, "updateMaxEvents")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxEvents = items[0].toUint();
            MAX_EVENTS = newMaxEvents;
            emit ConstantUpdated();
        } else if (Memory.compareStrings(key, "updateMaxGas")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxGas = items[0].toUint();
            MAX_GAS = newMaxGas;
            emit ConstantUpdated();
        } else if (Memory.compareStrings(key, "updateMaxFunctions")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxFunctions = items[0].toUint();
            MAX_FUNCTIONS = newMaxFunctions;
            emit ConstantUpdated();
        } else {
            revert UnsupportedGovParam(key);
        }
    }

    /**
     * @dev Helper function to convert RLP data to bytes32.
     * @param item The RLP item to convert.
     * @return The bytes32 representation.
     */
    function toBytes32(RLPDecode.RLPItem memory item) internal pure returns (bytes32) {
        bytes memory data = item.toBytes();
        bytes32 result;

        assembly {
            result := mload(add(data, 32))
        }

        return result;
    }

    /**
     * @dev Public function to add a configuration.
     * @param contractAddr The address of the contract to add the config to.
     * @param events Array of events.
     * @param functions Array of function signatures.
     * @param isActive The active status of the config.
     */
    function addConfig(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions,
        bool isActive
    ) external onlyDAO onlyInit {
        _addConfig(contractAddr, events, functions, isActive);
    }

    /**
     * @dev Internal function to add a configuration.
     * @param contractAddr The address of the contract to add the config to.
     * @param events Array of events.
     * @param functions Array of function signatures.
     * @param isActive The active status of the config.
     */
    function _addConfig(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions,
        bool isActive
    ) internal {
        // Check if the config for the given contract already exists.
        if (configsMap[contractAddr].configAddress != address(0)) {
            revert AddressAlreadyExists(contractAddr);
        }

        if (events.length > MAX_EVENTS && events.length != 0) {
            revert TooManyEvents();
        }

        if (functions.length > MAX_FUNCTIONS) {
            revert TooManyEvents();
        }

        // Validate reward percentages for all events
        for (uint i; i < events.length; i++) {
            _validateRewardPercentages(events[i].rewards);
            _validateGas(events[i].gas);
        }

        // Add the new config to the mapping and address array
        Config storage newConfig = configsMap[contractAddr];
        newConfig.configAddress = contractAddr;
        newConfig.isActive = isActive;

        // Manually copy events and their rewards
        for (uint i = 0; i < events.length; i++) {
            Event storage newEvent = newConfig.events.push();
            newEvent.eventSignature = events[i].eventSignature;
            newEvent.gas = events[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < events[i].rewards.length; j++) {
                newEvent.rewards.push(events[i].rewards[j]);
            }
        }

        // Manually copy function signatures
        for (uint i = 0; i < functions.length; i++) {
            Function storage newFunction = newConfig.functions.push();
            newFunction.functionSignature = functions[i].functionSignature;
            newFunction.gas = functions[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < functions[i].rewards.length; j++) {
                newFunction.rewards.push(functions[i].rewards[j]);
            }
        }

        configAddresses.push(contractAddr);

        emit ConfigUpdated(contractAddr, events.length, functions.length);
    }

    /**
     * @dev Internal function to update a configuration.
     * @param contractAddr The address of the contract to update the config for.
     * @param events The new array of events.
     * @param functions The new array of function signatures.
     */
    function _updateConfig(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions
    ) internal {
        // Check if the config exists
        if (configsMap[contractAddr].configAddress == address(0)) {
            revert AddressNotFound(contractAddr);
        }

        if (events.length > MAX_EVENTS && events.length != 0) {
            revert TooManyEvents();
        }

        if (functions.length > MAX_FUNCTIONS) {
            revert TooManyEvents();
        }

        // Validate reward percentages for all events
        for (uint i; i < events.length; i++) {
            _validateRewardPercentages(events[i].rewards);
            _validateGas(events[i].gas);
        }

        // Update the config in the mapping
        Config storage existingConfig = configsMap[contractAddr];

        // Clear existing arrays
        delete existingConfig.events;
        delete existingConfig.functions;

        // Manually copy events and their rewards
        for (uint i = 0; i < events.length; i++) {
            Event storage newEvent = existingConfig.events.push();
            newEvent.eventSignature = events[i].eventSignature;
            newEvent.gas = events[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < events[i].rewards.length; j++) {
                newEvent.rewards.push(events[i].rewards[j]);
            }
        }

        // Manually copy function signatures and their rewards
        for (uint i = 0; i < functions.length; i++) {
            Function storage newFunction = existingConfig.functions.push();
            newFunction.functionSignature = functions[i].functionSignature;
            newFunction.gas = functions[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < functions[i].rewards.length; j++) {
                newFunction.rewards.push(functions[i].rewards[j]);
            }
        }

        emit ConfigUpdated(contractAddr, events.length, functions.length);
    }

    /**
     * @dev Internal function to set the active status of a configuration.
     * @param contractAddr The address of the contract.
     * @param isActive The active status to set.
     */
    function _setConfigStatus(address contractAddr, bool isActive) internal {
        if (configsMap[contractAddr].configAddress == address(0)) {
            revert AddressNotFound(contractAddr);
        }
        configsMap[contractAddr].isActive = isActive;
        emit ConfigUpdated(contractAddr, 0, 0);
    }

    /**
     * @dev Internal function to validate that total reward percentages don't exceed 100%.
     * @param rewards Array of rewards to validate.
     */
    function _validateRewardPercentages(Reward[] memory rewards) internal view {
        uint256 totalPercentage = 0;
        for (uint i; i < rewards.length; i++) {
            totalPercentage += rewards[i].rewardPercentage;
        }
        if (totalPercentage != SatoshiPlusHelper.DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }
    }

    /**
     * @dev Validate gas values are within limits.
     * @param gas The gas value to validate.
     */
    function _validateGas(uint32 gas) internal view {
        if (gas > MAX_GAS) {
            revert InvalidGasValue(gas);
        }
    }

    /**
     * @dev Public function to remove a configuration.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function removeConfig(address contractAddr) external onlyDAO onlyInit {
        _removeConfig(contractAddr);
    }

    /**
     * @dev Public function to update a configuration.
     * @param contractAddr The address of the contract to update the config for.
     * @param events The new array of events.
     * @param functions The new array of function signatures.
     */
    function updateConfig(
        address contractAddr,
        Event[] memory events,
        Function[] memory functions
    ) external onlyDAO onlyInit {
        _updateConfig(contractAddr, events, functions);
    }

    /**
     * @dev Public function to set the active status of a configuration.
     * @param contractAddr The address of the contract.
     * @param isActive The active status to set.
     */
    function setConfigStatus(address contractAddr, bool isActive) external onlyDAO onlyInit {
        _setConfigStatus(contractAddr, isActive);
    }

    /**
     * @dev Internal function to remove a configuration.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function _removeConfig(address contractAddr) internal {
        // Check if the config exists
        if (configsMap[contractAddr].configAddress == address(0)) {
            revert AddressNotFound(contractAddr);
        }

        // Remove the config from the mapping
        delete configsMap[contractAddr];

        // Remove the address from the address array
        for (uint i = 0; i < configAddresses.length; i++) {
            if (configAddresses[i] == contractAddr) {
                configAddresses[i] = configAddresses[configAddresses.length - 1];
                configAddresses.pop();
                break;
            }
        }

        emit ConfigRemoved(contractAddr);
    }

    /**
     * @dev Returns the configuration details for a given address.
     * @param contractAddr The address of the contract.
     * @return The configuration details.
     */
    function getConfig(address contractAddr) external view returns (Config memory) {
        return configsMap[contractAddr];
    }

    /**
     * @dev Returns all configuration addresses.
     * @return An array of all configuration addresses.
     */
    function getAllConfigAddresses() external view returns (address[] memory) {
        return configAddresses;
    }

    /**
     * @dev Checks if a configuration exists for a given address.
     * @param contractAddr The address of the contract.
     * @return True if the configuration exists, false otherwise.
     */
    function configExists(address contractAddr) external view returns (bool) {
        return configsMap[contractAddr].configAddress != address(0);
    }

    /**
     * @dev Returns the details of a specific event within a configuration.
     * @param contractAddr The address of the contract.
     * @param eventIndex The index of the event.
     * @return The event details.
     */
    function getEventDetails(address contractAddr, uint256 eventIndex) external view returns (Event memory) {
        require(eventIndex < configsMap[contractAddr].events.length, "Event index out of bounds");
        return configsMap[contractAddr].events[eventIndex];
    }

    /**
     * @dev Returns the details of a specific function within a configuration.
     * @param contractAddr The address of the contract.
     * @param functionIndex The index of the function.
     * @return The function details.
     */
    function getFunctionDetails(address contractAddr, uint256 functionIndex) external view returns (Function memory) {
        require(functionIndex < configsMap[contractAddr].functions.length, "Function index out of bounds");
        return configsMap[contractAddr].functions[functionIndex];
    }
}   