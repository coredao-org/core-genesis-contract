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
        Reward[] rewards;
        bytes32 eventSignature;
        uint32 gas;
    }

    /// @dev Struct to store function signature and gas details.
    struct FunctionSignatures {
        Reward[] rewards;
        bytes32 functionSignature;
        uint32 gas;
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

    uint256 public MAX_REWARD_ADDRESS;

    uint256 public MAX_EVENTS;

    uint256 public MAX_FUNCTION_SIGNATURES;

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
        MAX_REWARD_ADDRESS = 5;
        MAX_EVENTS = 5;
        MAX_FUNCTION_SIGNATURES = 5;
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
     * @dev Function to add a configuration.
     * @param contractAddr The address of the contract to add the config to.
     * @param eventSignatures Array of event signatures.
     * @param eventGas Array of gas values for events.
     * @param rewardAddrs Array of reward addresses.
     * @param rewardPercentages Array of reward percentages.
     * @param isActive The active status of the config.
     */
    function addConfig(
        address contractAddr,
        bytes32[] memory eventSignatures,
        uint32[] memory eventGas,
        address[] memory rewardAddrs,
        uint16[] memory rewardPercentages,
        bool isActive
    ) public {
        require(eventSignatures.length == eventGas.length, "Event arrays length mismatch");
        require(rewardAddrs.length == rewardPercentages.length, "Reward arrays length mismatch");
        
        if(maxRewardAddress == 0) {
            maxRewardAddress = MAX_REWARD_ADDRESS;
        }
        if(eventSignatures.length > MAX_EVENTS) {
            revert TooManyIssuers();
        }

        // Check if the config for the given contract already exists.
        for (uint i = 0; i < configs.length; i++) {
            if (configs[i].configAddress == contractAddr) {
                revert AddressAlreadyExists(contractAddr);
            }
        }

        Config storage p = configs.push();
        p.configAddress = contractAddr;
        p.isActive = isActive;
        
        // Initialize the events array in storage
        for (uint i = 0; i < eventSignatures.length; i++) {
            // Create a new Event struct in storage
            Event storage newEvent = p.events.push();
            newEvent.eventSignature = eventSignatures[i];
            newEvent.gas = eventGas[i];

            for (uint j = 0; j < rewardAddrs.length; j++) {
                Reward storage newReward = newEvent.rewards.push();
                newReward.rewardAddr = rewardAddrs[j];
                newReward.rewardPercentage = rewardPercentages[j];
            }
        }
        
        emit ConfigUpdated(contractAddr, eventSignatures.length, 0); 
    }
}
