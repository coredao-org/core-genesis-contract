const web3 = require("web3")
const RLP = require('rlp');

// Configure
const members = [
  "0x91fb7d8a73d2752830ea189737ea0e007f999b94",
  "0x48bfbc530e7c54c332b0fae07312fba7078b8789",
  "0xde60b7d0e6b758ca5dd8c61d377a2c5f1af51ec1"
];

// ===============  Do not edit below ====
function membersRlpEncode(members) {
  return web3.utils.bytesToHex(RLP.encode(members));
}

initMembersBytes = membersRlpEncode(members)
exports = module.exports = {
  initMembers: initMembersBytes
}