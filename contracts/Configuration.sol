// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/Memory.sol";
import "./lib/RLPDecode.sol";


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
    struct FunctionSignatures {
        bytes32 functionSignature;
        uint32 gas;
        Reward[] rewards;
    }

    /// @dev Struct to store config details.
    struct Config {
        address configAddress;
        bool isActive;
        Event[] events;
        FunctionSignatures[] functionSignatures;
    }

    // DAO Address
    address public daoAddress;

    // Constants
    uint256 public DENOMINATOR;
    uint256 public MAX_REWARD_ADDRESS;
    uint256 public MAX_EVENTS;
    uint256 public MAX_FUNCTION_SIGNATURES;
    uint256 public MAX_GAS;

    // Replace the array with a mapping and an address array
    address[] public configAddresses;
    mapping(address => Config) public configsMap;

    // Event to signal config updates
    event ConfigUpdated(address indexed configAddress, uint256 eventCount, uint256 functionSignatureCount);
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
        MAX_FUNCTION_SIGNATURES = 5;
        MAX_GAS = 1000000;
        DENOMINATOR = 10000;
    }

    /**
     * @dev Helper function to find a config by address.
     * @param contractAddr The address of the contract to find.
     * @return The index of the config in the address array.
     */
    function _findConfigIndex(address contractAddr) internal view returns (uint256) {
        for (uint256 i = 0; i < configAddresses.length; i++) {
            if (configAddresses[i] == contractAddr) {
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

            FunctionSignatures[] memory functionSignatures = new FunctionSignatures[](0);

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

            FunctionSignatures[] memory functionSignatures = new FunctionSignatures[](0);

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
        } else if (Memory.compareStrings(key, "updateMaxFunctionSignatures")) {
            RLPDecode.RLPItem[] memory items = value.toRLPItem().toList();
            if (items.length != 1) revert MismatchParamLength(key);

            uint256 newMaxFunctionSignatures = items[0].toUint();
            MAX_FUNCTION_SIGNATURES = newMaxFunctionSignatures;
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
     * @param functionSignatures Array of function signatures.
     * @param isActive The active status of the config.
     */
    function addConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures,
        bool isActive
    ) external onlyDAO onlyInit {
        _addConfig(contractAddr, events, functionSignatures, isActive);
    }

    /**
     * @dev Internal function to add a configuration.
     * @param contractAddr The address of the contract to add the config to.
     * @param events Array of events.
     * @param functionSignatures Array of function signatures.
     * @param isActive The active status of the config.
     */
    function _addConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures,
        bool isActive
    ) internal {
        // Check if the config for the given contract already exists.
        if (configsMap[contractAddr].configAddress != address(0)) {
            revert AddressAlreadyExists(contractAddr);
        }

        if (events.length > MAX_EVENTS && events.length != 0) {
            revert TooManyEvents();
        }

        if (functionSignatures.length > MAX_FUNCTION_SIGNATURES) {
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
        for (uint i = 0; i < functionSignatures.length; i++) {
            FunctionSignatures storage newFunctionSignature = newConfig.functionSignatures.push();
            newFunctionSignature.functionSignature = functionSignatures[i].functionSignature;
            newFunctionSignature.gas = functionSignatures[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < functionSignatures[i].rewards.length; j++) {
                newFunctionSignature.rewards.push(functionSignatures[i].rewards[j]);
            }
        }

        configAddresses.push(contractAddr);

        emit ConfigUpdated(contractAddr, events.length, functionSignatures.length);
    }

    /**
     * @dev Internal function to update a configuration.
     * @param contractAddr The address of the contract to update the config for.
     * @param events The new array of events.
     * @param functionSignatures The new array of function signatures.
     */
    function _updateConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures
    ) internal {
        // Check if the config exists
        if (configsMap[contractAddr].configAddress == address(0)) {
            revert AddressNotFound(contractAddr);
        }

        if (events.length > MAX_EVENTS && events.length != 0) {
            revert TooManyEvents();
        }

        if (functionSignatures.length > MAX_FUNCTION_SIGNATURES) {
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
        delete existingConfig.functionSignatures;

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
        for (uint i = 0; i < functionSignatures.length; i++) {
            FunctionSignatures storage newFunctionSignature = existingConfig.functionSignatures.push();
            newFunctionSignature.functionSignature = functionSignatures[i].functionSignature;
            newFunctionSignature.gas = functionSignatures[i].gas;

            // Manually copy rewards
            for (uint j = 0; j < functionSignatures[i].rewards.length; j++) {
                newFunctionSignature.rewards.push(functionSignatures[i].rewards[j]);
            }
        }

        emit ConfigUpdated(contractAddr, events.length, functionSignatures.length);
    }

    /**
     * @dev Internal function to remove an issuer from a configuration.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer to remove.
     */
    function _removeIssuer(address contractAddr, address issuer) internal {
        uint256 idx = _findConfigIndex(contractAddr);
        bool found = false;

        // Check events
        for (uint i; i < configsMap[contractAddr].events.length; i++) {
            for (uint j; j < configsMap[contractAddr].events[i].rewards.length; j++) {
                if (configsMap[contractAddr].events[i].rewards[j].rewardAddr == issuer) {
                    // Replace with the last element and remove the last
                    configsMap[contractAddr].events[i].rewards[j] = configsMap[contractAddr].events[i].rewards[configsMap[contractAddr].events[i].rewards.length - 1];
                    configsMap[contractAddr].events[i].rewards.pop();
                    found = true;
                    break;
                }
            }
        }

        if (!found) {
            revert IssuerNotFound(issuer);
        }

        emit ConfigUpdated(contractAddr, configsMap[contractAddr].events.length, 0);
    }

    /**
     * @dev Internal function to set the active status of a configuration.
     * @param contractAddr The address of the contract.
     * @param isActive The active status to set.
     */
    function _setConfigStatus(address contractAddr, bool isActive) internal {
        uint256 idx = _findConfigIndex(contractAddr);
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
        if (totalPercentage != DENOMINATOR) {
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
     * @param functionSignatures The new array of function signatures.
     */
    function updateConfig(
        address contractAddr,
        Event[] memory events,
        FunctionSignatures[] memory functionSignatures
    ) external onlyDAO onlyInit {
        _updateConfig(contractAddr, events, functionSignatures);
    }

    /**
     * @dev Public function to remove an issuer from a configuration.
     * @param contractAddr The address of the contract.
     * @param issuer The address of the issuer to remove.
     */
    function removeIssuer(address contractAddr, address issuer) external onlyDAO onlyInit {
        _removeIssuer(contractAddr, issuer);
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
}