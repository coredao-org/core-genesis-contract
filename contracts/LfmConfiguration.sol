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

    event AddDestinationAddress(address indexed destination);
	event RemoveDestinationAddress(address indexed destination);
    event AddGasFactor(address indexed addr, uint indexed factor);
    event UpdateGasFactor(address indexed addr, uint indexed oldFactor, uint indexed newFactor);
    event SetMeanGasPrice(uint indexed oldPrice, uint indexed newPrice);
    event SetNetworkConfigRefreshInterval(uint indexed oldInterval, uint indexed newInterval);
    event SetLfmGasPriceValues(uint indexed oldLen, uint indexed newLen);
	event SetGasFactorLimits(uint oldMin, uint oldMax, uint indexed newMin, uint indexed newMax);

	error CouldNotFindAddressToRemove(address addrToRemove);
	error NonAscendingStepArray(uint ind0, uint priceStep0, uint ind1, uint priceStep1);
	error NonAscendingDiscountedArray(uint ind0, uint discountedPrice0, uint ind1, uint discountedPrice1);
	error GasFactorTooLow(uint factor, uint minGasFactor);
	error GasFactorTooHigh(uint factor, uint maxGasFactor);

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

    function addDestinationAddress(address addrToAdd) external onlyGovDelegate {
	   _safeAddToAddressArr(destinationAddresses, addrToAdd);
       emit AddDestinationAddress(addrToAdd);
    }

	function _safeAddToAddressArr(address[] storage arr, address addrToAdd) private {
       require(addrToAdd != address(0), "address cannot be null");
       for (uint i = 0; i < arr.length; i++) {
			require(arr[i] != addrToAdd, "address already exists");
	   }
       arr.push(addrToAdd);
	}

    function removeDestinationAddress(address addrToRemove) external onlyGovDelegate {
		_safeRemoveFromAddressArr(destinationAddresses, addrToRemove);
		emit RemoveDestinationAddress(addrToRemove);
    }

	function _safeRemoveFromAddressArr(address[] storage arr, address addrToRemove) private {
       require(addrToRemove != address(0), "address cannot be null");
	   uint len = arr.length;
       for (uint i = 0; i < len; i++) {
			if (arr[i] == addrToRemove) {
				arr[i] = arr[len-1]; // order is not important
				arr.pop();
				return;
			}
	   }
	   revert CouldNotFindAddressToRemove(addrToRemove);
   }

	function setGasFactorLimits(uint newMin, uint newMax) external onlyGovDelegate {
		//both: [0..infinite]
        require(newMin <= newMax); // equal is fine
		uint oldMin = minGasFactor;
		uint oldMax = maxGasFactor;
		minGasFactor = newMin;
		maxGasFactor = newMax;
		emit SetGasFactorLimits(oldMin, oldMax, newMin, newMax);
	}

	function setGasFactor(address addr, uint factor) external onlyGovDelegate {
		require(addr != address(0));
		_verifyGasFactor(factor);
		if (_existingGasFactorUpdated(addr, factor)) {
			return;
		}
		destinationAddresses.push(addr);
		s_destinationGasFactors.push(factor);
		require(destinationAddresses.length == s_destinationGasFactors.length); // sanity check
       	emit AddGasFactor(addr, factor);
    }

	function _existingGasFactorUpdated(address addr, uint newFactor) private returns(bool) {
		for (uint i = 0; i < destinationAddresses.length; i++) {
			if (destinationAddresses[i] == addr) {
				_updateGasFactor(i, newFactor, addr);
				return true;
			}
		}
		return false;
	}

	function _updateGasFactor(uint ind, uint newFactor, address addr) private {
		uint oldFactor = s_destinationGasFactors[ind];
		s_destinationGasFactors[ind] = newFactor;
		emit UpdateGasFactor(addr, oldFactor, newFactor);
	}

    function setMeanGasPrice(uint newPrice) external onlyGovDelegate {
       uint oldPrice =  meanGasPrice;
       meanGasPrice = newPrice;
       emit SetMeanGasPrice(oldPrice, meanGasPrice);
    }

    function setNetworkConfigRefreshInterval(uint newInterval) external onlyGovDelegate {
       uint oldInterval = refreshIntervalInBlocks;
       refreshIntervalInBlocks = newInterval;
       emit SetNetworkConfigRefreshInterval(oldInterval, refreshIntervalInBlocks);
    }

	function getConfigParams() external view returns(uint, uint, uint[] memory, uint[] memory, address[] memory, uint[] memory) {
		uint[] memory correctedDestFactors = _correctDestFactorsByRange(); // correct by min/max
		return (meanGasPrice, refreshIntervalInBlocks, gasPriceSteps, gasDiscountedPrices, destinationAddresses, correctedDestFactors); 
	}

   function getEffectiveDestFactor(uint ind) external view returns(uint) {
      return _adjustGasFactorByLimits(s_destinationGasFactors[ind]);
   }

    function _correctDestFactorsByRange() private view returns(uint[] memory) {
		// make sure factors adhere to current (and not only historical) range limits
		uint len = s_destinationGasFactors.length;
		uint[] memory corrected = new uint[](len);
		for (uint i = 0; i < len; i++) {
			corrected[i] = _adjustGasFactorByLimits(s_destinationGasFactors[i]);
		}
		return corrected;
	}

	function _adjustGasFactorByLimits(uint factor) private view returns(uint) {
		// factor may not exceed current limits
		if (factor < minGasFactor) return minGasFactor;
		if (factor > maxGasFactor) return maxGasFactor;
		return factor;
	}

    function setGasPriceValues(uint[] calldata _gasPriceSteps, uint[] calldata _gasDiscountedPrices) external onlyGovDelegate {
	  uint newLen = _gasPriceSteps.length;
      require(newLen > 0, "must have at least one step");
      require(newLen == _gasDiscountedPrices.length, "inconsistent array length"); // zero length is fine
      // verify lists are ascending
	  for (uint i = 0+1; i < newLen; i++) {
	    if (_gasPriceSteps[i] <= _gasPriceSteps[i-1]) {
		    revert NonAscendingStepArray(i-1, _gasPriceSteps[i-1], i, _gasPriceSteps[i]);
		}
		if (_gasDiscountedPrices[i] <= _gasDiscountedPrices[i-1]) {
			revert NonAscendingDiscountedArray(i-1, _gasDiscountedPrices[i-1], i, _gasDiscountedPrices[i]);
		}
	  }
      uint oldLen = gasPriceSteps.length;
      gasPriceSteps = _gasPriceSteps;
      gasDiscountedPrices = _gasDiscountedPrices;
      emit SetLfmGasPriceValues(oldLen, newLen);
    }

    function _verifyGasFactor(uint factor) private view {
		if (factor < minGasFactor) {
		    revert GasFactorTooLow(factor, minGasFactor);
		}
		if (factor > maxGasFactor) {
			revert GasFactorTooHigh(factor, maxGasFactor);
		}
	}
}
