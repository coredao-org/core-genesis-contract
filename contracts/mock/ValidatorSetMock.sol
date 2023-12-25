// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "../ValidatorSet.sol";
import {BaseMock} from "./BaseMock.sol";

contract ValidatorSetMock is ValidatorSet , BaseMock {

    uint256 private constant MOCK_SUBSIDY_REDUCE_INTERVAL = 10512000;
    bytes private constant MOCK_INIT_VALIDATORSET_BYTES = hex"f90285ea944121f067b0f5135d77c29b2b329e8cb1bd96c96094f8b18cecc98d976ad253d38e4100a73d4e154726ea947f461f8a1c35edecd6816e76eb2e84eb661751ee94f8b18cecc98d976ad253d38e4100a73d4e154726ea94fd806ab93db5742944b7b50ce759e5eee5f6fe5094f8b18cecc98d976ad253d38e4100a73d4e154726ea947ef3a94ad1c443481fb3d86829355ca90477f8b594f8b18cecc98d976ad253d38e4100a73d4e154726ea9467d1ad48f91e131413bd0b04e823f3ae4f81e85394f8b18cecc98d976ad253d38e4100a73d4e154726ea943fb42cab4416024dc1b4c9e21b9acd0dfcef35f694f8b18cecc98d976ad253d38e4100a73d4e154726ea943511e3b8ac7336b99517d324145e9b5bb33e08a494f8b18cecc98d976ad253d38e4100a73d4e154726ea94729f39a54304fcc6ec279684c71491a385d7b9ae94f8b18cecc98d976ad253d38e4100a73d4e154726ea94f44a785fd9f23f0abd443541386e71356ce619dc94f8b18cecc98d976ad253d38e4100a73d4e154726ea942efd3cf0733421aec3e4202480d0a90bd157514994f8b18cecc98d976ad253d38e4100a73d4e154726ea94613b0f519ada008cb99b6130e89122ba416bf15994f8b18cecc98d976ad253d38e4100a73d4e154726ea94c0925eeb800ff6ba4695ded61562a10102152b5f94f8b18cecc98d976ad253d38e4100a73d4e154726ea9419e3c7d7e69f273f3f91c060bb438a007f6fc33c94f8b18cecc98d976ad253d38e4100a73d4e154726ea94e127f110d172a0c4c6209fe045dd71781e8fe9d494f8b18cecc98d976ad253d38e4100a73d4e154726ea94f778dc4a199a440dbe9f16d1e13e185bb179b3b794f8b18cecc98d976ad253d38e4100a73d4e154726";

    uint private s_subsidyInterval = MOCK_SUBSIDY_REDUCE_INTERVAL;

    function developmentInit() external {
        blockReward = blockReward / 1e14;

        for (uint i=0; i<currentValidatorSet.length; i++) {
            delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
        }
        delete currentValidatorSet;

        bytes memory initValidatorSet = hex"f8d7ea9401bca3615d24d3c638836691517b2b9b49b054b1943ae030dc3717c66f63d6e8f1d1508a5c941ff46dea94a458499604a85e90225a14946f36368ae24df16d94de442f5ba55687a24f04419424e0dc2593cc9f4cea945e00c0d5c4c10d4c805aba878d51129a89d513e094cb089be171e256acdaac1ebbeb32ffba0dd438eeea941cd652bc64af3f09b490daae27f46e53726ce230940a53b7e0ffd97357e444b85f4d683c1d8e22879aea94da37ccecbb2d7c83ae27ee2bebfe8ebce162c60094d82c24274ebbfe438788d684dc6034c3c67664a4";
        (Validator[] memory validatorSet, bool valid) = decodeValidatorSet(initValidatorSet);
        require(valid, "failed to parse init validatorSet");
        uint256 validatorSize = validatorSet.length;
        for (uint256 i = 0; i < validatorSize; i++) {
          currentValidatorSet.push(validatorSet[i]);
          currentValidatorSetMap[validatorSet[i].consensusAddress] = i + 1;
        }
    }
    function updateBlockReward(uint256 _blockReward) external {
        blockReward = _blockReward;
    }
    function updateSubsidyReduceInterval(uint256 _internal) external {
        s_subsidyInterval = _internal;
    }

    function _initValidatorSet() internal pure override returns (bytes memory){
      return MOCK_INIT_VALIDATORSET_BYTES;
    }

    function _subsidyReduceInterval() internal override view returns(uint256) {
      return s_subsidyInterval;
    }

    function getSubsidyReduceInterval() external view returns(uint256) {
      return s_subsidyInterval;
    }

    function addRoundRewardMock(address[] memory agentList, uint256[] memory rewardList)
    external {
        uint256 rewardSum = 0;
        for (uint256 i = 0; i < rewardList.length; i++) {
        	rewardSum += rewardList[i];
        }
        IPledgeAgent(_pledgeAgent()).addRoundReward{ value: rewardSum }(agentList, rewardList);
    }

    function jailValidator(address operateAddress, uint256 round, uint256 fine) external {
        ICandidateHub(_candidateHub()).jailValidator(operateAddress, round, fine);
    }

    function getValidatorByConsensus(address consensus) external view returns(Validator memory) {
        uint indexPlus1 = currentValidatorSetMap[consensus];
        require(indexPlus1 > 0, "no match validator");
        uint index_ = indexPlus1 - 1;
        return currentValidatorSet[index_];
    }

    function setValidatorSetMap(address validator) external {
        currentValidatorSetMap[validator] = 1;
    }

    function _isBlockProducer() internal override pure returns (bool) {
        return true;
    }

    function _zeroGasPrice() internal override pure returns (bool) {
        return true;
    }


    // -- address mock overrides --

    function _validatorSet() view internal override returns (address) {
        return _notNull(s_validatorSet);
    }

    function _slash() view internal override returns (address) {
        return _notNull(s_slash);
    }

    function _systemReward() view internal override returns (address) {
        return _notNull(s_systemReward);   
    }

    function _lightClient() view internal override returns (address) {
        return _notNull(s_lightClient); 
    }

    function _relayerHub() view internal override returns (address) {
        return _notNull(s_relayerHub);  
    }

    function _candidateHub() view internal override returns (address) {
        return _notNull(s_candidateHub);  
    }

    function _govHub() view internal override returns (address) {
        return _notNull(s_govHub);
    }

    function _pledgeAgent() view internal override returns (address) {
        return _notNull(s_pledgeAgent);  
    }

    function _burn() view internal override returns (address) {
        return _notNull(s_burn);  
    }

    function _foundation() view internal override returns (address) {
        return _notNull(s_foundation);  
    }    
}

