const web3 = require("web3")
const RLP = require('rlp');

// Configure
const validators = [
  
   {
     "consensusAddr": "0x4121F067B0F5135D77C29b2B329e8Cb1bd96C960",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x7f461f8a1c35eDEcD6816e76Eb2E84eb661751eE",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xfD806AB93db5742944B7B50Ce759E5EeE5f6FE50",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x7Ef3a94AD1c443481fb3d86829355CA90477F8b5",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x67D1ad48f91E131413BD0b04e823F3AE4F81E853",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x3Fb42caB4416024dC1B4C9e21B9acD0DFcef35f6",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x3511E3b8aC7336B99517D324145e9b5Bb33e08a4",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x729f39a54304fCc6eC279684c71491A385d7b9aE",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xF44a785Fd9F23F0abd443541386E71356Ce619dC",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x2EFd3CF0733421aec3E4202480d0A90bd1575149",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x613b0F519aDA008CB99B6130E89122BA416Bf159",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xc0925eeb800fF6Ba4695DED61562A10102152B5f",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0x19e3C7D7E69F273f3F91C060Bb438a007f6Fc33c",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xE127f110D172a0c4C6209fE045dd71781e8fe9d4",
     "feeAddr": "0xF8B18CeCC98D976ad253D38E4100a73D4e154726",
   },
   {
     "consensusAddr": "0xF778dc4A199A440dBE9f16d1e13e185bB179B3b7",
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