// SPDX-License-Identifier: Apache2.0
pragma solidity 0.8.4;

import "./System.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IValidatorSet.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ISystemReward.sol";
import "./interface/ICandidateHub.sol";
import "./lib/RLPDecode.sol";

/// This contract manages elected validators in each round
/// All rewards for validators on Core blockchain are minted in genesis block and stored in this contract
contract ValidatorSet is IValidatorSet, System, IParamSubscriber {
  using RLPDecode for bytes;
  using RLPDecode for RLPDecode.Iterator;
  using RLPDecode for RLPDecode.RLPItem;

  uint256 public constant BLOCK_REWARD = 3e18;
  uint256 public constant BLOCK_REWARD_INCENTIVE_PERCENT = 10;
  uint256 public constant REDUCE_FACTOR = 9639;
  uint256 public constant SUBSIDY_REDUCE_INTERVAL = 10512000;

  bytes public constant INIT_VALIDATORSET_BYTES = hex"f90285ea944121f067b0f5135d77c29b2b329e8cb1bd96c96094f8b18cecc98d976ad253d38e4100a73d4e154726ea947f461f8a1c35edecd6816e76eb2e84eb661751ee94f8b18cecc98d976ad253d38e4100a73d4e154726ea94fd806ab93db5742944b7b50ce759e5eee5f6fe5094f8b18cecc98d976ad253d38e4100a73d4e154726ea947ef3a94ad1c443481fb3d86829355ca90477f8b594f8b18cecc98d976ad253d38e4100a73d4e154726ea9467d1ad48f91e131413bd0b04e823f3ae4f81e85394f8b18cecc98d976ad253d38e4100a73d4e154726ea943fb42cab4416024dc1b4c9e21b9acd0dfcef35f694f8b18cecc98d976ad253d38e4100a73d4e154726ea943511e3b8ac7336b99517d324145e9b5bb33e08a494f8b18cecc98d976ad253d38e4100a73d4e154726ea94729f39a54304fcc6ec279684c71491a385d7b9ae94f8b18cecc98d976ad253d38e4100a73d4e154726ea94f44a785fd9f23f0abd443541386e71356ce619dc94f8b18cecc98d976ad253d38e4100a73d4e154726ea942efd3cf0733421aec3e4202480d0a90bd157514994f8b18cecc98d976ad253d38e4100a73d4e154726ea94613b0f519ada008cb99b6130e89122ba416bf15994f8b18cecc98d976ad253d38e4100a73d4e154726ea94c0925eeb800ff6ba4695ded61562a10102152b5f94f8b18cecc98d976ad253d38e4100a73d4e154726ea9419e3c7d7e69f273f3f91c060bb438a007f6fc33c94f8b18cecc98d976ad253d38e4100a73d4e154726ea94e127f110d172a0c4c6209fe045dd71781e8fe9d494f8b18cecc98d976ad253d38e4100a73d4e154726ea94f778dc4a199a440dbe9f16d1e13e185bb179b3b794f8b18cecc98d976ad253d38e4100a73d4e154726";

  /*********************** state of the contract **************************/
  uint256 public blockReward;
  uint256 public blockRewardIncentivePercent;
  Validator[] public currentValidatorSet;
  uint256 public totalInCome;

  // key is the `consensusAddress` of `Validator`,
  // value is the index of the element in `currentValidatorSet`.
  mapping(address => uint256) public currentValidatorSetMap;

  struct Validator {
    address operateAddress;
    address consensusAddress;
    address payable feeAddress;
    uint256 commissionThousandths;
    uint256 income;
  }

  /*********************** events **************************/
  event validatorSetUpdated();
  event systemTransfer(uint256 amount);
  event directTransfer(
    address indexed operateAddress,
    address payable indexed validator,
    uint256 amount,
    uint256 totalReward
  );
  event directTransferFail(
    address indexed operateAddress,
    address payable indexed validator,
    uint256 amount,
    uint256 totalReward
  );
  event deprecatedDeposit(address indexed validator, uint256 amount);
  event validatorDeposit(address indexed validator, uint256 amount);
  event validatorMisdemeanor(address indexed validator, uint256 amount);
  event validatorFelony(address indexed validator, uint256 amount);
  event paramChange(string key, bytes value);

  modifier onlyIfCurrentValidator(address validator) {
    require(currentValidatorSetMap[validator] > 0, "not a current validator");
    _;
  }

  /*********************** init **************************/
  function init() external onlyNotInit {
    (Validator[] memory validatorSet, bool valid) = decodeValidatorSet(INIT_VALIDATORSET_BYTES);
    require(valid, "failed to parse init validatorSet");
    uint256 validatorSize = validatorSet.length;
    for (uint256 i = 0; i < validatorSize; i++) {
      currentValidatorSet.push(validatorSet[i]);
      currentValidatorSetMap[validatorSet[i].consensusAddress] = i + 1;
    }
    blockReward = BLOCK_REWARD;
    blockRewardIncentivePercent = BLOCK_REWARD_INCENTIVE_PERCENT;
    alreadyInit = true;
  }

  /*********************** External Functions **************************/
  /// Check whether the input address belongs to an active validator
  /// @param addr The address to check
  /// @return true/false
  function isValidator(address addr) public override view returns (bool) {
    return currentValidatorSetMap[addr] != 0;
  }

/* @product Called by the current block producer to add block reward to a validator
   @logic
      1. The caller passes with this call eth value that is not tested for min/max caps @openissue
      2. If the current block number is a multiplier of SUBSIDY_REDUCE_INTERVAL (=10512000) 
         the blockReward is reduced - from this operation henceforth - by a factor of 0.9639
      3. if the validator address is valid, the validator's income is increased by a value 
         calculated as follows:
            a. start with the eth value passed by the block producer with the call
            b. if the ValidatorSet balance (not including current transfer) is equal
               or larger than the global totalInCome + blockReward then add blockReward eth 
               to the value
      4. ..And the global totalInCome value is increased by the same value
      5. Else - a deprecatedDeposit() event is emitted
*/
    function deposit(address valAddr) external payable onlyCoinbase onlyInit onlyZeroGasPrice {
    if (block.number % SUBSIDY_REDUCE_INTERVAL == 0) {
      blockReward = blockReward * REDUCE_FACTOR / 10000;
    }
    uint256 value = msg.value;
    if (address(this).balance >= totalInCome + value + blockReward) {
      value += blockReward;
    }
    uint256 index = currentValidatorSetMap[valAddr];
    if (index != 0) {
      Validator storage validator = currentValidatorSet[index - 1];
      totalInCome = totalInCome + value;
      validator.income = validator.income + value;
      emit validatorDeposit(valAddr, value);
    } else {
      emit deprecatedDeposit(valAddr, value);
    }
  }

/* @product Called by the CandidateHub contract at the beginning of turn round to distribute 
    rewards to all validators (and delegators through PledgeAgent)
   
   @logic
      1. all validators are iterated and for each an incentive value value is calculated 
         to be 1% of the sum of the current validator income plus a global
         blockRewardIncentivePercent value
      2. Each validator's income gets reduce by the validator's incentive values
      3. The sum of all validator's incentive values is stored as incentiveSum
      4. After that the SystemReward's receiveRewards function is invoked with eth value
         set to incentiveSum, read its doc for the details of its action
      5. Once done, the validators are iterated over again and, for each validator:
         if the validator's fee is positive that the validator reward is sent to the validator's 
         fee address, after which the validator's income is zeroed the validator reward is 
         calculated as a single promile (1/1000) of the validator's income times the 
         validator's commissionThousandths value and the rewardSum of all validators is set 
         to be the sum of all validators' (income - reward) values
      6. After that, the PledgeAgent contract addRoundReward() function is invoked with eth value set 
         to rewardSum and with operateAddressList and rewardList as params. Read its documentation for details.
      7. Finally the global totalInCome value is set to zero
*/
  function distributeReward() external override onlyCandidate returns (address[] memory operateAddressList) {
    address payable feeAddress;
    uint256 validatorReward;

    uint256 incentiveSum = 0;
    uint256 validatorSize = currentValidatorSet.length;
    for (uint256 i = 0; i < validatorSize; i++) {
      Validator storage v = currentValidatorSet[i];
      uint256 incentiveValue = (v.income * blockRewardIncentivePercent) / 100;
      incentiveSum += incentiveValue;
      v.income -= incentiveValue;
    }
    ISystemReward(SYSTEM_REWARD_ADDR).receiveRewards{ value: incentiveSum }();

    operateAddressList = new address[](validatorSize);
    uint256[] memory rewardList = new uint256[](validatorSize);
    uint256 rewardSum = 0;
    uint256 tempIncome;
    for (uint256 i = 0; i < validatorSize; i++) {
      Validator storage v = currentValidatorSet[i];
      operateAddressList[i] = v.operateAddress;
      tempIncome = v.income;
      if (tempIncome != 0) {
        feeAddress = v.feeAddress;
        validatorReward = (tempIncome * v.commissionThousandths) / 1000;
        if (tempIncome > validatorReward) {
          rewardList[i] = tempIncome - validatorReward;
          rewardSum += rewardList[i];
        }

        v.income = 0;
        bool success = feeAddress.send(validatorReward);
        if (success) {
          emit directTransfer(v.operateAddress, feeAddress, validatorReward, tempIncome);
        } else {
          emit directTransferFail(v.operateAddress, feeAddress, validatorReward, tempIncome);
        }
      }
    }

    IPledgeAgent(PLEDGE_AGENT_ADDR).addRoundReward{ value: rewardSum }(operateAddressList, rewardList);
    totalInCome = 0;
    return operateAddressList;
  } 

/* @product Called by the CandidateHub contract as part of the turn round flow to update validator 
       set of the new round with elected validators
   @param operateAddrList: List of validator operator addresses
   @param consensusAddrList: List of validator consensus addresses
   @param feeAddrList: List of validator fee addresses
   @param commissionThousandthsList: List of validator commission fees in promils (=thousandth)

   @logic
      1. The function validates that all list parameters are of the same length and that
         each element commissionThousandthsList is less than 1000
      2. It then replaces the current validators with the newly passed ones, each validator containing
         an operate address, a consensus addrress, a fee address and a commissionThousandths count
*/
  function updateValidatorSet(
    address[] calldata operateAddrList,
    address[] calldata consensusAddrList,
    address payable[] calldata feeAddrList,
    uint256[] calldata commissionThousandthsList
  ) external override onlyCandidate {
    // do verify.
    checkValidatorSet(operateAddrList, consensusAddrList, feeAddrList, commissionThousandthsList);
    if (consensusAddrList.length == 0) {
      return;
    }
    // do update validator set state
    uint256 i;
    uint256 lastLength = currentValidatorSet.length;
    uint256 currentLength = consensusAddrList.length;
    for (i = 0; i < lastLength; i++) {
      delete currentValidatorSetMap[currentValidatorSet[i].consensusAddress];
    }
    for (i = currentLength; i < lastLength; i++) {
      currentValidatorSet.pop();
    }

    for (i = 0; i < currentLength; ++i) {
      if (i >= lastLength) {
        currentValidatorSet.push(Validator(operateAddrList[i], consensusAddrList[i], feeAddrList[i],commissionThousandthsList[i], 0));
      } else {
        currentValidatorSet[i] = Validator(operateAddrList[i], consensusAddrList[i], feeAddrList[i],commissionThousandthsList[i], 0);
      }
      currentValidatorSetMap[consensusAddrList[i]] = i + 1;
    }

    emit validatorSetUpdated();
  }

  /// Get list of validators in the current round
  /// @return List of validator consensus addresses
  function getValidators() external view returns (address[] memory) {
    uint256 validatorSize = currentValidatorSet.length;
    address[] memory consensusAddrs = new address[](validatorSize);
    for (uint256 i = 0; i < validatorSize; i++) {
      consensusAddrs[i] = currentValidatorSet[i].consensusAddress;
    }
    return consensusAddrs;
  }

  /// Get incoming, which is the reward to distribute at the end of the round, of a validator
  /// @param validator The validator address
  /// @return The incoming reward of the validator
  function getIncoming(address validator) external view returns (uint256) {
    uint256 index = currentValidatorSetMap[validator];
    if (index == 0) {
      return 0;
    }
    return currentValidatorSet[index - 1].income;
  }

  /*********************** For slash **************************/
  /// Slash the validator for misdemeanor behaviors
  /// @param validator The validator to slash
  function misdemeanor(address validator) external override onlySlash {
    uint256 index = currentValidatorSetMap[validator];
    if (index == 0) {
      return;
    }
    // the actually index
    index = index - 1;
    uint256 income = currentValidatorSet[index].income;
    currentValidatorSet[index].income = 0;
    uint256 rest = currentValidatorSet.length - 1;
    address operateAddress = currentValidatorSet[index].operateAddress;
    emit validatorMisdemeanor(operateAddress, income);
    if (rest == 0) {
      // should not happen, but still protect
      return;
    }
    uint256 averageDistribute = income / rest;
    if (averageDistribute != 0) {
      for (uint256 i = 0; i < index; i++) {
        currentValidatorSet[i].income += averageDistribute;
      }
      uint256 n = currentValidatorSet.length;
      for (uint256 i = index + 1; i < n; i++) {
        currentValidatorSet[i].income += averageDistribute;
      }
    }
  }

/* @product Called by the Slash contract (only) to slash validators for felony behaviors
   @param validator: The validator to slash
   @param felonyRound: The number of rounds to jail the validator
   @param felonyDeposit: The amount of deposits to slash

   @logic
        1. If the 'bad' validator is the only validator then he will not be jailed, but 
           his income will be zeroed
        2. Else the validator will be removed from the current.validators list
        3. And a sum equal to the 'bad' validator income will be equally divided between the 
           rest of the validators without clearing of the 'bad' validator's income @openissue
        4. Finally the CandidateHub's jailValidator() function will be invoked to place the 
           validator in jail for felonyRound and slash some amount of deposits. Read its 
           documentation for more details
*/
  function felony(address validator, uint256 felonyRound, uint256 felonyDeposit) 
          external override onlySlash onlyIfCurrentValidator(validator) {
    uint256 index = currentValidatorSetMap[validator];
    // the actually index
    index = index - 1;
    uint256 income = currentValidatorSet[index].income;
    uint256 rest = currentValidatorSet.length - 1;
    if (rest == 0) {
      // will not remove the validator if it is the only one validator.
      currentValidatorSet[index].income = 0;
      return;
    }
    address operateAddress = currentValidatorSet[index].operateAddress;
    emit validatorFelony(operateAddress, income);
    delete currentValidatorSetMap[validator];
    // It is ok that the validatorSet is not in order.
    if (index != currentValidatorSet.length - 1) {
      currentValidatorSet[index] = currentValidatorSet[currentValidatorSet.length - 1];
      currentValidatorSetMap[currentValidatorSet[index].consensusAddress] = index + 1;
    }
    currentValidatorSet.pop();
    uint256 averageDistribute = income / rest;
    if (averageDistribute != 0) {
      uint256 n = currentValidatorSet.length;
      for (uint256 i = 0; i < n; i++) {
        currentValidatorSet[i].income += averageDistribute;
      }
    }
    ICandidateHub(CANDIDATE_HUB_ADDR).jailValidator(operateAddress, felonyRound, felonyDeposit);
  }

  /*********************** Param update ********************************/
  /// Update parameters through governance vote
  /// @param key The name of the parameter
  /// @param value the new value set to the parameter
  function updateParam(string calldata key, bytes calldata value) external override onlyInit onlyGov {
    if (value.length != 32) {
      revert MismatchParamLength(key);
    }
    if (Memory.compareStrings(key, "blockRewardIncentivePercent")) {
      uint256 newBlockRewardIncentivePercent = BytesToTypes.bytesToUint256(32, value);
      if (newBlockRewardIncentivePercent > 100) {
        revert OutOfBounds(key, newBlockRewardIncentivePercent, 0, 100);
      }
      blockRewardIncentivePercent = newBlockRewardIncentivePercent;
    } else {
      require(false, "unknown param");
    }
    emit paramChange(key, value);
  }

  /*********************** Internal Functions **************************/
  function checkValidatorSet(
    address[] memory operateAddrList,
    address[] memory consensusAddrList,
    address payable[] memory feeAddrList,
    uint256[] memory commissionThousandthsList
  ) private pure {
    require(
      consensusAddrList.length == operateAddrList.length,
      "the numbers of consensusAddresses and operateAddresses should be equal"
    );
    require(
      consensusAddrList.length == feeAddrList.length,
      "the numbers of consensusAddresses and feeAddresses should be equal"
    );
    require(
      consensusAddrList.length == commissionThousandthsList.length,
      "the numbers of consensusAddresses and commissionThousandthss should be equal"
    );
    for (uint256 i = 0; i < consensusAddrList.length; i++) {
      for (uint256 j = 0; j < i; j++) {
        require(consensusAddrList[i] != consensusAddrList[j], "duplicate consensus address");
      }
      require(commissionThousandthsList[i] <= 1000, "commissionThousandths out of bound");
    }
  }

  //rlp encode & decode function
  function decodeValidatorSet(bytes memory msgBytes) internal pure returns (Validator[] memory, bool) {
    RLPDecode.RLPItem[] memory items = msgBytes.toRLPItem().toList();
    uint256 itemSize = items.length;
    Validator[] memory validatorSet = new Validator[](itemSize);
    for (uint256 j = 0; j < itemSize; j++) {
      (Validator memory val, bool ok) = decodeValidator(items[j]);
      if (!ok) {
        return (validatorSet, false);
      }
      validatorSet[j] = val;
    }
    bool success = itemSize != 0;
    return (validatorSet, success);
  }

  function decodeValidator(RLPDecode.RLPItem memory itemValidator) internal pure returns (Validator memory, bool) {
    Validator memory validator;
    RLPDecode.Iterator memory iter = itemValidator.iterator();
    bool success = false;
    while (iter.hasNext()) {
      validator.consensusAddress = iter.next().toAddress();
      validator.feeAddress = payable(iter.next().toAddress());
      validator.operateAddress = validator.feeAddress;
      validator.commissionThousandths = 1000;
      success = true;
    }
    return (validator, success);
  }
}
