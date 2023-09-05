const web3 = require("web3")
const init_holders = [
   //
   {
      address: "0xa2d48116761f2af265bed1d9b000ebbcca3f12c4",
      balance: web3.utils.toBN("100000000000000000000000000").toString("hex")
   },
   //
   {
      address: "0x288244402acfdb405f2a1730d7a41033ac6ac271",
      balance: web3.utils.toBN("500000000000000000000000000").toString("hex")
   },
];


exports = module.exports = init_holders
