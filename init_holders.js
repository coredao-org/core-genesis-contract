const web3 = require("web3")
const init_holders = [
   //
   {
      address: "0xf14c914eA16C216b5f5D0223628016F1228695b2",
      balance: web3.utils.toBN("100000000000000000000000000").toString("hex")
   },
   //
   {
      address: "0x288244402acfdb405f2a1730d7a41033ac6ac271",
      balance: web3.utils.toBN("500000000000000000000000000").toString("hex")
   },
];


exports = module.exports = init_holders
