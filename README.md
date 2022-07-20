# core-genesis-contracts

This repo hold all the genesis contracts on Core chain.

## Prepare

Install dependency:
```shell script
npm install
``` 

## test
```shell
# install test dependency
pip install -r requirements.txt

node generate-candidatehub.js --mock true
node generate-pledgeagent.js --mock true
brownie test -v --stateful false
```

Flatten all system contracts:
```shell script
npm run flatten
```

## how to generate genesis file.
 
1. Edit `init_holders.js` file to alloc the initial CORE holder.
2. Edit `validators.js` file to alloc the initial validator set.
3. Edit `init_cycle.js` file to change params of cycle.
4. Edit `generate-btclightclient.js` file to change `initConsensusStateBytes`.
5. run ` node generate-genesis.js` will generate genesis.json

## License

The library is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0),
also included in our repository in the [LICENSE](LICENSE) file.
