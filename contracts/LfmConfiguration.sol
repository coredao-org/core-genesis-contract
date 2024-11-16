// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./base/GovernanceDelegateManaged.sol";

contract LfmConfiguration is GovernanceDelegateManaged {

    uint public constant INITIAL_MEAN_GAS_PRICE = 35783571428;
    uint public constant INITIAL_REFRESH_INTERVAL = 3;
    uint public constant INITIAL_MIN_GAS_FACTOR_MILLIS = 0;
    uint public constant INITIAL_MAX_GAS_FACTOR_MILLIS = 10000;

    uint public meanGasPrice; // historical mean
    uint public refreshIntervalInBlocks;

    uint public minGasFactor;
    uint public maxGasFactor;

    uint[] public gasPriceSteps;
    uint[] public gasDiscountedPrices;

    address[] public destinationAddresses;
    uint[] private s_destinationGasFactors; // measured in millis:

    event AddNewDestinationContract(address indexed destination, uint indexed gasFactor);
    event RemoveDestinationContract(address indexed destination);
    event UpdateGasFactor(address indexed addr, uint indexed oldGasFactor, uint indexed newGasFactor);
    event SetMeanGasPrice(uint indexed oldPrice, uint indexed newPrice);
    event SetNetworkConfigRefreshInterval(uint indexed oldInterval, uint indexed newInterval);
    event SetLfmGasPriceValues(uint indexed oldLen, uint indexed newLen);
    event SetGasFactorLimits(uint oldMin, uint oldMax, uint indexed newMin, uint indexed newMax);		

    error CouldNotFindAddressToRemove(address addrToRemove);
    error NonAscendingStepArray(uint ind0, uint priceStep0, uint ind1, uint priceStep1);
    error NonAscendingDiscountedArray(uint ind0, uint discountedPrice0, uint ind1, uint discountedPrice1);
    error GasFactorTooLow(uint factor, uint minGasFactor);
    error GasFactorTooHigh(uint factor, uint maxGasFactor);
		error ContractAddressNotFound(address addr);

    function init() external onlyNotInit {
        meanGasPrice = INITIAL_MEAN_GAS_PRICE;
        refreshIntervalInBlocks = INITIAL_REFRESH_INTERVAL;
        minGasFactor = INITIAL_MIN_GAS_FACTOR_MILLIS;
        maxGasFactor = INITIAL_MAX_GAS_FACTOR_MILLIS;
        alreadyInit = true;
        // governanceDelegate must be set for contract to become functional
    }

    function numDestinationAddresses() external view returns (uint) {
        return destinationAddresses.length;
    }

    function addNewDestinationContract(address newAddress, uint newGasFactor) external onlyGovDelegate {
        require(newAddress != address(0), "address cannot be null");
        _verifyAddressNotInArray(newAddress, destinationAddresses);
				_validateGasFactor(newGasFactor);
        destinationAddresses.push(newAddress);
				s_destinationGasFactors.push(newGasFactor);
        emit AddNewDestinationContract(newAddress, newGasFactor);
    }

    function _verifyAddressNotInArray(address addrToLookup, address[] storage arr) private view {
        for (uint i = 0; i < arr.length; i++) {
            require(arr[i] != addrToLookup, "address already exists");
        }
    }

    function removeDestinationContract(address addrToRemove) external onlyGovDelegate {
        uint index = _safeRemoveFromAddressArr(addrToRemove, destinationAddresses);
				_removeEntryByIndex(index, s_destinationGasFactors);
        emit RemoveDestinationContract(addrToRemove);
    }

    function _safeRemoveFromAddressArr(address addrToRemove, address[] storage arr) private returns(uint) {
        require(addrToRemove != address(0), "address cannot be null");
        uint len = arr.length;
        for (uint i = 0; i < len; i++) {
            if (arr[i] == addrToRemove) {
                arr[i] = arr[len-1]; // order is not important
                arr.pop();
                return i;
            }
        }
        revert CouldNotFindAddressToRemove(addrToRemove);
    }

    function _removeEntryByIndex(uint ind, uint[] storage arr) private {
				uint len = arr.length;
        require(ind < len, "bad index");
				arr[ind] = arr[len-1]; // order is not important
				arr.pop();
    }

    function setGasFactorLimits(uint newMin, uint newMax) external onlyGovDelegate {
        //both: [0..infinite]
        require(newMin <= newMax, "min factor cannot exceed max"); // equal is fine
        uint oldMin = minGasFactor;
        uint oldMax = maxGasFactor;
        minGasFactor = newMin;
        maxGasFactor = newMax;
        emit SetGasFactorLimits(oldMin, oldMax, newMin, newMax);
    }

    function updateGasFactor(address addr, uint newGasFactor) external onlyGovDelegate {
        require(addr != address(0));
        _validateGasFactor(newGasFactor);
        for (uint i = 0; i < destinationAddresses.length; i++) {
            if (destinationAddresses[i] == addr) {
                _updateGasFactor(i, addr, newGasFactor);
								return;
            }
        }
        revert ContractAddressNotFound(addr);
    }

    function _updateGasFactor(uint ind, address addrToUpdate, uint newGasFactor) private {
        uint oldGasFactor = s_destinationGasFactors[ind];
        s_destinationGasFactors[ind] = newGasFactor;
        emit UpdateGasFactor(addrToUpdate, oldGasFactor, newGasFactor);
    }

    function setMeanGasPrice(uint newPrice) external onlyGovDelegate {
        uint oldPrice = meanGasPrice;
        meanGasPrice = newPrice;
        emit SetMeanGasPrice(oldPrice, meanGasPrice);
    }

    function setNetworkConfigRefreshInterval(uint newInterval) external onlyGovDelegate {
        uint oldInterval = refreshIntervalInBlocks;
        refreshIntervalInBlocks = newInterval;
        emit SetNetworkConfigRefreshInterval(oldInterval, refreshIntervalInBlocks);
    }

    function getConfigParams() external view
        returns (
            uint,
            uint,
            uint[] memory,
            uint[] memory,
            address[] memory,
            uint[] memory
        )
    {
        uint[] memory correctedDestFactors = _correctDestFactorsByRange(); // correct by min/max
        return (
            meanGasPrice,
            refreshIntervalInBlocks,
            gasPriceSteps,
            gasDiscountedPrices,
            destinationAddresses,
            correctedDestFactors
        );
    }

    function _correctDestFactorsByRange() private view returns (uint[] memory) {
        // make sure factors adhere to current (and not only historical) range limits
        uint len = s_destinationGasFactors.length;
        uint[] memory corrected = new uint[](len);
        for (uint i = 0; i < len; i++) {
            corrected[i] = _adjustGasFactorByLimits(s_destinationGasFactors[i]);
        }
        return corrected;
    }

		function getEffectiveDestFactor(uint ind) external view returns (uint) {
    		return _adjustGasFactorByLimits(s_destinationGasFactors[ind]);
    }

    function _adjustGasFactorByLimits(uint factor) private view returns (uint) {
        // factor may not exceed current limits
        if (factor < minGasFactor) return minGasFactor;
        if (factor > maxGasFactor) return maxGasFactor;
        return factor;
    }

		// set steps & price-values used to discount native transfer gas price
    function setGasPriceGradient(uint[] calldata newSteps, uint[] calldata newPrices) external onlyGovDelegate {
        uint newLen = newSteps.length;
        require(newLen > 0, "must have at least one step");
        require(newLen == newPrices.length, "inconsistent array length"); // zero length is fine
        _verifyGradientListsAreAscending(newSteps, newPrices);
        uint oldLen = gasPriceSteps.length;
        gasPriceSteps = newSteps;
        gasDiscountedPrices = newPrices;
        emit SetLfmGasPriceValues(oldLen, newLen);
    }

    function _verifyGradientListsAreAscending(uint[] calldata newSteps, uint[] calldata newPrices) private pure {
				uint len = newSteps.length;
        for (uint i = 0+1; i < len; i++) {
            if (newSteps[i] <= newSteps[i-1]) {
                revert NonAscendingStepArray(i-1, newSteps[i-1], i, newSteps[i]);
            }
            if (newPrices[i] <= newPrices[i-1]) {
                revert NonAscendingDiscountedArray(i-1, newPrices[i-1], i, newPrices[i]);
            }
        }
		}

    function _validateGasFactor(uint factor) private view {
        if (factor < minGasFactor) {
            revert GasFactorTooLow(factor, minGasFactor);
        }
        if (factor > maxGasFactor) {
            revert GasFactorTooHigh(factor, maxGasFactor);
        }
    }
}
