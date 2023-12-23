// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

abstract contract BaseMock {

    address public s_validatorSet;
    address public s_slash;
    address public s_systemReward;
    address public s_lightClient;
    address public s_relayerHub;
    address public s_candidateHub;
    address public s_govHub;
    address public s_pledgeAgent;
    address public s_burn;
    address public s_foundation;

    function updateContractAddr(address validatorSet_, address slash_, address systemReward_, 
                            address lightClient_, address relayerHub_, address candidateHub_, 
                            address govHub_, address pledgeAgent_, address burn_, address foundation_) external {

        assert( validatorSet_ != address(0));
        assert( slash_ != address(0));
        assert( systemReward_ != address(0));
        assert( lightClient_ != address(0));
        assert( relayerHub_ != address(0));
        assert( candidateHub_ != address(0));
        assert( govHub_ != address(0));
        assert( pledgeAgent_ != address(0));
        assert( burn_ != address(0));
        assert( foundation_ != address(0));

        s_validatorSet = validatorSet_;
        s_slash = slash_;
        s_systemReward = systemReward_;
        s_lightClient = lightClient_;
        s_relayerHub = relayerHub_;
        s_candidateHub = candidateHub_;
        s_govHub = govHub_;
        s_pledgeAgent = pledgeAgent_;
        s_burn = burn_;
        s_foundation = foundation_;
    }

    function _notNull(address addr) internal pure returns (address) {
        require(addr != address(0), "address is null");
        return addr;
    }
}