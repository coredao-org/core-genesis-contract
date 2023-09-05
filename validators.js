const web3 = require("web3")
const RLP = require('rlp');

// Configure
const validators = [
   {
     "consensusAddr": "0x01Bca3615D24d3c638836691517b2B9b49b054B1",
     "feeAddr": "0x3aE030Dc3717C66f63D6e8f1d1508a5C941ff46D",
   },
   {
     "consensusAddr": "0xa458499604A85E90225a14946f36368Ae24df16D",
     "feeAddr": "0xde442f5ba55687a24f04419424e0dc2593cc9f4c",
   },
   {
     "consensusAddr": "0x5E00C0D5C4C10d4c805aba878D51129A89d513e0",
     "feeAddr": "0xcb089be171e256acdaac1ebbeb32ffba0dd438ee",
   },
   {
     "consensusAddr": "0x1Cd652bC64Af3f09B490dAae27f46e53726ce230",
     "feeAddr": "0x0a53b7e0ffd97357e444b85f4d683c1d8e22879a",
   },
   {
     "consensusAddr": "0xDA37ccECBB2D7C83aE27eE2BeBFE8EBCe162c600",
     "feeAddr": "0xd82c24274ebbfe438788d684dc6034c3c67664a4",
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