const { spawn } = require("child_process")
const program = require("commander")
const nunjucks = require("nunjucks")
const fs = require("fs")
const web3 = require("web3")

const validators = require("./validators")
const init_holders = require("./init_holders")
const init_cycle = require("./init_cycle")


program.option("-c, --chainid <chainid>", "chain id, mainnet 1116 testnet 1115 devnet 1112", "1116")

program.option(
    "--initValidatorSetBytes <initValidatorSetBytes>",
    "initValidatorSetBytes",
    ""
)
program.option("--initConsensusStateBytes <initConsensusStateBytes>",
    "init consensusState bytes, hex encoding, no prefix with 0x",
    "42696e616e63652d436861696e2d4e696c650000000000000000000000000000000000000000000229eca254b3859bffefaf85f4c95da9fbd26527766b784272789c30ec56b380b6eb96442aaab207bc59978ba3dd477690f5c5872334fc39e627723daa97e441e88ba4515150ec3182bc82593df36f8abb25a619187fcfab7e552b94e64ed2deed000000e8d4a51000");

require("./generate-lib");
require("./generate-system");
require("./generate-validatorset");
require("./generate-btclightclient");
require("./generate-govhub");
require("./generate-candidatehub");

program.version("0.0.1")
program.option(
  "-o, --output <output-file>",
  "Genesis json file",
  "./genesis.json"
)
program.option(
  "-t, --template <template>",
  "Genesis template json",
  "./genesis-template.json"
)
program.parse(process.argv)

// compile contract
function compileContract(key, contractFile, contractName) {
  return new Promise((resolve, reject) => {
    const ls = spawn("solc", [
      "@openzeppelin/=./node_modules/@openzeppelin/",
      "--bin-runtime",
      "/=/",
      "--optimize",
      "--optimize-runs",
      "10000",
      contractFile
    ])

    const result = []
    ls.stdout.on("data", data => {
      result.push(data.toString())
    })

    ls.stderr.on("data", data => {
      // console.log(`stderr: ${data}`)
    })

    ls.on("close", code => {
      console.log(`child process exited with code ${code}`)
      resolve(result.join(""))
    })
  }).then(compiledData => {
    console.log(`${contractFile}:${contractName}`)
    compiledData = compiledData.replace(
      `======= ${contractFile}:${contractName} =======\nBinary of the runtime part:`,
      "@@@@"
    )

    const matched = compiledData.match(/@@@@\n([a-f0-9]+)/)
    return { key, compiledData: matched[1], contractName, contractFile }
  })
}

// compile files
Promise.all([
  compileContract(
    "validatorContract",
    "contracts/ValidatorSet.sol",
    "ValidatorSet"
  ),
  compileContract(
    "systemRewardContract",
    "contracts/SystemReward.sol",
    "SystemReward"
  ),
  compileContract(
      "slashContract",
      "contracts/SlashIndicator.sol",
      "SlashIndicator"
  ),
  compileContract(
      "btcLightClient",
      "contracts/BtcLightClient.sol",
      "BtcLightClient"
  ),
  compileContract(
      "relayerHub",
      "contracts/RelayerHub.sol",
      "RelayerHub"
  ),
  compileContract(
      "candidateHub",
      "contracts/CandidateHub.sol",
      "CandidateHub"
  ),
  compileContract(
      "govHub",
      "contracts/GovHub.sol",
      "GovHub"
  ),
  compileContract(
      "pledgeAgent",
      "contracts/PledgeAgent.sol",
      "PledgeAgent"
  ),
  compileContract(
    "burn",
    "contracts/Burn.sol",
    "Burn"
  ),
  compileContract(
    "foundation",
    "contracts/Foundation.sol",
    "Foundation"
  ),
  compileContract(
    "stakehub",
    "contracts/StakeHub.sol",
    "StakeHub"
  ),
  compileContract(
    "coreagent",
    "contracts/CoreAgent.sol",
    "CoreAgent"
  ),
  compileContract(
    "hashpoweragent",
    "contracts/HashPowerAgent.sol",
    "HashPowerAgent"
  ),
  compileContract(
    "bitcoinagent",
    "contracts/BitcoinAgent.sol",
    "BitcoinAgent"
  ),
  compileContract(
    "bitcoinstake",
    "contracts/BitcoinStake.sol",
    "BitcoinStake"
  ),
  compileContract(
    "bitcoinLSTstake",
    "contracts/BitcoinLSTStake.sol",
    "BitcoinLSTStake"
  )
]).then(result => {

  const data = {
    chainId: program.chainid,
    initHolders: init_holders,
    initCycle: init_cycle,
    extraData: web3.utils.bytesToHex(validators.extraValidatorBytes),
  }
  result.forEach(r => {
    data[r.key] = r.compiledData
  })
  const templateString = fs.readFileSync(program.template).toString()
  const resultString = nunjucks.renderString(templateString, data)
  fs.writeFileSync(program.output, resultString)

})
