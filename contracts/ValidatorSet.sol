pragma solidity 0.8.4;

import "./System.sol";
import "./lib/BytesToTypes.sol";
import "./lib/Memory.sol";
import "./interface/IParamSubscriber.sol";
import "./interface/IValidatorSet.sol";
import "./interface/IPledgeAgent.sol";
import "./interface/ISystemReward.sol";
import "./interface/ICandidateHub.sol";
import "./lib/SafeMath.sol";
import "./lib/RLPDecode.sol";

/// This contract manages elected validators in each round
/// All rewards for validators on Core blockchain are minted in genesis block and stored in this contract
contract ValidatorSet is IValidatorSet, System, IParamSubscriber {
  using SafeMath for uint256;
  using RLPDecode for *;

  uint256 public constant BLOCK_REWARD = 3e18;
  uint256 public constant BLOCK_REWARD_INCENTIVE_PERCENT = 10;
  uint256 public constant REDUCE_FACTOR = 9639;
  uint256 public constant SUBSIDY_REDUCE_INTERVAL = 10512000;

  bytes public constant INIT_VALIDATORSET_BYTES = hex"f8d7ea9401bca3615d24d3c638836691517b2b9b49b054b1943ae030dc3717c66f63d6e8f1d1508a5c941ff46dea94a458499604a85e90225a14946f36368ae24df16d94de442f5ba55687a24f04419424e0dc2593cc9f4cea945e00c0d5c4c10d4c805aba878d51129a89d513e094cb089be171e256acdaac1ebbeb32ffba0dd438eeea941cd652bc64af3f09b490daae27f46e53726ce230940a53b7e0ffd97357e444b85f4d683c1d8e22879aea94da37ccecbb2d7c83ae27ee2bebfe8ebce162c60094d82c24274ebbfe438788d684dc6034c3c67664a4";

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
  function isValidator(address addr) public override returns (bool) {
    return currentValidatorSetMap[addr] != 0;
  }

  /// Add block reward on a validator 
  /// @dev This method is called by the golang consensus engine every block
  /// @param valAddr The validator address
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

  /// Distribute rewards to validators (and delegators through PledgeAgent)
  /// @dev this method is called by the CandidateHub contract at the beginning of turn round
  /// @dev this is where we deal with reward distribution logics
  function distributeReward() external override onlyCandidate {
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

    address[] memory operateAddressList = new address[](validatorSize);
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
  } 

  /// Update validator set of the new round with elected validators 
  /// @param operateAddrList List of validator operator addresses
  /// @param consensusAddrList List of validator consensus addresses
  /// @param feeAddrList List of validator fee addresses
  /// @param commissionThousandthsList List of validator commission fees in thousandth
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
    if (index <= 0) {
      return 0;
    }
    return currentValidatorSet[index - 1].income;
  }

  /*********************** For slash **************************/
  /// Slash the validator for misdemeanor behaviors
  /// @param validator The validator to slash
  function misdemeanor(address validator) external override onlySlash {
    uint256 index = currentValidatorSetMap[validator];
    if (index <= 0) {
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

  /// Slash the validator for felony behaviors
  /// @param validator The validator to slash
  /// @param felonyRound The number of rounds to jail
  /// @param felonyDeposit The amount of deposits to slash
  function felony(address validator, uint256 felonyRound, uint256 felonyDeposit) external override onlySlash {
    uint256 index = currentValidatorSetMap[validator];
    if (index <= 0) {
      return;
    }
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
    if (Memory.compareStrings(key, "blockRewardIncentivePercent")) {
      require(value.length == 32, "length of blockRewardIncentivePercent mismatch");
      uint256 newBlockRewardIncentivePercent = BytesToTypes.bytesToUint256(32, value);
      require(newBlockRewardIncentivePercent <= 100, "the blockRewardIncentivePercent out of range");
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
