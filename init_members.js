const web3 = require("web3")
const RLP = require('rlp');

// Configure
const members = [
  "0x548e6ACCE441866674E04ab84587af2D394034c0",
  "0xBb06D463bc143EeCC4A0cfa35e0346d5690fa9f6",
  "0xe2fe60f349C6e1a85caaD1d22200C289DA40DC12",
  "0xB198DB68258f06e79D415A0998Be7f9B38Ea7226",
  "0xdd173b85f306128F1B10D7d7219059c28c6D6c09"
];

const testnetMembers = [
  "0x91fb7d8a73d2752830ea189737ea0e007f999b94",
  "0x48bfbc530e7c54c332b0fae07312fba7078b8789",
  "0xde60b7d0e6b758ca5dd8c61d377a2c5f1af51ec1"
];

// ===============  Do not edit below ====
function membersRlpEncode(members) {
  return web3.utils.bytesToHex(RLP.encode(members));
}

initMembersBytes = membersRlpEncode(members)
initMembersTestnetBytes = membersRlpEncode(testnetMembers)
exports = module.exports = {
  initMembers: initMembersBytes,
  initMembersTestnet: initMembersTestnetBytes,
}