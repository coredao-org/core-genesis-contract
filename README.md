# Core Genesis Contracts

This repo holds all the genesis contracts on Core blockchain, which are part of the core implementations of Satoshi Plus consensus. For more information about Core blockchain and Satoshi Plus consensus, please read the [technical whitepaper](https://whitepaper.coredao.org/core-white-paper-v1.0.7).



## List of Contracts

- [System.sol](./contracts/System.sol): This contract defines system constants (such as the genesis contract addresses) and various modifiers that can be used across the system to limit the accessibility to function.
- [BTCLightClient.sol](./contracts/BtcLightClient.sol): This contract implements a BTC light client on the Core blockchain. Relayers transmit BTC block headers to Core by calling this contract. 
  - It also calculates powers of BTC miners in each round, which is used to calculate hybrid score and reward distribution.
  - It also provides support to verify Bitcoin transactions for BTC staking. 
- [Burn.sol](./contracts/Burn.sol): This contract burns CORE tokens up to pre-defined CAP.
- [CandidateHub.sol](./contracts/CandidateHub.sol): This contract manages all validator candidates on the Core blockchain. It also exposes the method `turnRound` for the consensus engine to execute the `turn round` workflow.
- [Foundation.sol](./contracts/Foundation.sol): This is the DAO Treasury smart contract. The funds in this contract can only be moved through governance vote.
- [GovHub.sol](./contracts/GovHub.sol): This is the smart contract to manage governance votes.
- [PledgeAgent.sol](./contracts/PledgeAgent.sol): This contract manages user delegation, including both delegation of CORE from token holders and delegation of PoW from Bitcoin miners. **This contract is deprecated since version 1.0.12 and it is replaced by Stakehub.sol and a few agent contracts**.
- [RelayerHub.sol](./contracts/RelayerHub.sol): This contract manages BTC relayers on the Core blockchain.
- [SlashIndicator.sol](./contracts/SlashIndicator.sol): This contract manages all slash and jail operations pertaining to validators on the Core blockchain.
- [SystemReward.sol](./contracts/SystemReward.sol): This smart contract manages funds for relayers and verifiers.
- [ValidatorSet.sol](./contracts/ValidatorSet.sol): This contract manages elected validators in each round. All rewards for validators on Core blockchain are minted in genesis block and stored in this contract.
- [StakeHub.sol](./contracts/StakeHub.sol): This contract deals with overall hybrid score and reward distribution logics. It replaces the existing role of PledgeAgent.sol to interact with CandidateHub.sol and other protocol contracts during the turnround process.
- [CoreAgent.sol](./contracts/CoreAgent.sol): This contract handles CORE staking.
- [HashPowerAgent.sol](./contracts/HashPowerAgent.sol): This contract handles Bitcoin hash power staking (measured in BTC blocks).
- [BitcoinAgent.sol](./contracts/BitcoinAgent.sol): This contract handles BTC staking. It interacts with BitcoinStake.sol and BitcoinLSTStake.sol for non-custodial BTC staking and LST BTC staking correspondingly. 
- [BitcoinStake.sol](./contracts/BitcoinStake.sol): This contract handles non-custodial BTC staking. 
- [BitcoinLSTStake.sol](./contracts/BitcoinLSTStake.sol): This contract handles LST BTC staking.
- [BitcoinLSTToken.sol](./contracts/BitcoinLSTToken.sol): ERC20 token contract of Core BTC LST.
- [Configuration.sol](./contracts/Configuration.sol): This contract handles Rev+ event configuration.


## Prepare
Install ganache globally:
```shell script
npm install -g ganache
```

Install dependency:
```shell script
npm install
```

## Run Tests

```shell
# install test dependency
pip install -r requirements.txt
brownie pm install OpenZeppelin/openzeppelin-contracts@4.9.6

# generate contracts for testing
./generate-test-contracts.sh

# run brownie tests
brownie test -v --stateful false
# run brownie tests in a single file
brownie test tests/{the-file-name.py} -v
# run brownie with a single testcase
brownie test -k <method-name> -v
```



Flatten all system contracts:

```shell script
npm run flatten
```



## Generate genesis.json

1. Edit `init_holders.js` file to alloc the initial CORE holders.
2. Edit `validators.js` file to alloc the initial validator set.
3. Edit `init_cycle.js` file to change core blockchain parameters.
4. Edit `generate-btclightclient.js` file to change `initConsensusStateBytes`.
5. Run ` node generate-genesis.js` to generate genesis.json.



## License

The library is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0),
also included in our repository in the [LICENSE](LICENSE) file.
