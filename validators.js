const web3 = require("web3")
const RLP = require('rlp');

// Configure
const validators = [
  
   {
     "consensusAddr": "0xf81399FC678D9AC35685e0900Aa09F5EBB477fc4",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xE801aAB42A5ED64FD8EFd798EA8e919b3F8A727d",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xB26aAA7769DE824B5aACcE5da62C7Ae71bFF2e53",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
    "consensusAddr": "0x40861Aa6542C59D505446747290fB1F001C042F4",
    "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
  },
  {
    "consensusAddr": "0x43026BE461B8D7774AcAc7C3Fe4Ca490ccdc20E7",
    "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
  },
];

// ===============  Do not edit below ====
function generateExtradata(validators) {
  let extraVanity =Buffer.alloc(32);
  let validatorsBytes = extraDataSerialize(validators);
  let extraSeal =Buffer.alloc(65);
  return Buffer.concat([extraVanity,validatorsBytes,extraSeal]);
}

function extraDataSerialize(validators) {
  let n = validators.length;
  let arr = [];
  for (let i = 0;i<n;i++) {
    let validator = validators[i];
    arr.push(Buffer.from(web3.utils.hexToBytes(validator.consensusAddr)));
  }
  return Buffer.concat(arr);
}

function validatorUpdateRlpEncode(validators) {
  let n = validators.length;
  let vals = [];
  for (let i = 0;i<n;i++) {
    vals.push([
      validators[i].consensusAddr,
      validators[i].feeAddr,
    ]);
  }
  return web3.utils.bytesToHex(RLP.encode(vals));
}

extraValidatorBytes = generateExtradata(validators);
validatorSetBytes = validatorUpdateRlpEncode(validators);

exports = module.exports = {
  extraValidatorBytes: extraValidatorBytes,
  validatorSetBytes: validatorSetBytes,
}