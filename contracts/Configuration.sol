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
    address public daoAddress = address(0x1);

    // Constants
    uint256 public DENOMINATOR = 10000;   

    uint256 public MAX_REWARD_ADDRESS;

    uint256 public MAX_EVENTS;

    uint256 public MAX_FUNCTION_SIGNATURES;

    uint256 public MAX_GAS;

    Config[] public configs;

    // Event to signal config updates
    event ConfigUpdated(address indexed configAddress, uint256 eventCount, uint256 functionSignatureCount);
    event ConstantUpdated();

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
        alreadyInit = true;
        MAX_REWARD_ADDRESS = 5;
        MAX_EVENTS = 5;
        MAX_FUNCTION_SIGNATURES = 5;
        MAX_GAS = 1000000;
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
    function _addConfig(address contractAddr, Event[] memory events, FunctionSignatures[] memory functionSignatures, bool isActive) internal {
        // Check if the config for the given contract already exists.
        for (uint i; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
                revert AddressAlreadyExists(contractAddr);
            }
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

        Config storage p = configs.push();
        p.configAddress = contractAddr;
        p.isActive = isActive;
        
        // Add events
        for (uint i; i < events.length; i++) {
            Event storage newEvent = p.events.push();
            newEvent.eventSignature = events[i].eventSignature;
            newEvent.gas = events[i].gas;
            
            for (uint j; j < events[i].rewards.length; j++) {
                if (events[i].rewards.length > MAX_REWARD_ADDRESS) {
                    revert TooManyRewardAddresses();
                }
                Reward storage newReward = newEvent.rewards.push();
                newReward.rewardAddr = events[i].rewards[j].rewardAddr;
                newReward.rewardPercentage = events[i].rewards[j].rewardPercentage;
            }
        }
   
        emit ConfigUpdated(contractAddr, events.length, 0);
    }

    /**
     * @dev Function to remove a configuration.
     * @param contractAddr The address of the contract to remove the config from.
     */
    function _removeConfig(address contractAddr) internal {
        uint256 idx = _findConfigIndex(contractAddr);
        configs[idx] = configs[configs.length - 1];
        configs.pop();
        emit ConfigUpdated(contractAddr, 0, 0);
    }

    /**
     * @dev Internal function to update a configuration.
     * @param contractAddr The address of the contract to update the config for.
     * @param events The new array of events.
     * @param functionSignatures The new array of function signatures.
     */
    function _updateConfig(address contractAddr, Event[] memory events, FunctionSignatures[] memory functionSignatures) internal {
        uint256 idx = _findConfigIndex(contractAddr);
        
        if (events.length > MAX_EVENTS && events.length != 0) {
            revert TooManyEvents();
        }
        
        if (functionSignatures.length > MAX_FUNCTION_SIGNATURES) {
            revert TooManyEvents();
        }

        // Validate reward percentages for all events
        for (uint i = 0; i < events.length; i++) {
            _validateRewardPercentages(events[i].rewards);
            _validateGas(events[i].gas);
        }
        
        // Clear existing events and add new ones
        delete configs[idx].events;
        for (uint i; i < events.length; i++) {
            Event storage newEvent = configs[idx].events.push();
            newEvent.eventSignature = events[i].eventSignature;
            newEvent.gas = events[i].gas;
            
            for (uint j; j < events[i].rewards.length; j++) {
                if (events[i].rewards.length > MAX_REWARD_ADDRESS) {
                    revert TooManyRewardAddresses();
                }
                Reward storage newReward = newEvent.rewards.push();
                newReward.rewardAddr = events[i].rewards[j].rewardAddr;
                newReward.rewardPercentage = events[i].rewards[j].rewardPercentage;
            }
        }
        
        
        emit ConfigUpdated(contractAddr, events.length, 0);
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
        for (uint i; i < configs[idx].events.length; i++) {
            for (uint j; j < configs[idx].events[i].rewards.length; j++) {
                if (configs[idx].events[i].rewards[j].rewardAddr == issuer) {
                    // Replace with the last element and remove the last
                    configs[idx].events[i].rewards[j] = configs[idx].events[i].rewards[configs[idx].events[i].rewards.length - 1];
                    configs[idx].events[i].rewards.pop();
                    found = true;
                    break;
                }
            }
        }
        
        if (!found) {
            revert IssuerNotFound(issuer);
        }

        emit ConfigUpdated(contractAddr, configs[idx].events.length, 0);
    }

    /**
     * @dev Internal function to set the active status of a configuration.
     * @param contractAddr The address of the contract.
     * @param isActive The active status to set.
     */
    function _setConfigStatus(address contractAddr, bool isActive) internal {
        uint256 idx = _findConfigIndex(contractAddr);
        configs[idx].isActive = isActive;
        emit ConfigUpdated(contractAddr, 0, 0);
    }

    /**
    * @dev Internal function to validate that total reward percentages don't exceed 100%.
    * @param rewards Array of rewards to validate.
    */
    function _validateRewardPercentages(Reward[] memory rewards) internal view  {
        uint256 totalPercentage = 0;
        for (uint i; i < rewards.length; i++) {
            totalPercentage += rewards[i].rewardPercentage;
        }
        if (totalPercentage != DENOMINATOR) {
            revert InvalidRewardPercentage(totalPercentage);
        }
    }

    /**
    * @dev Validate gas values are within limits
    * @param gas The gas value to validate
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

}   
