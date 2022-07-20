const fs = require("fs");
const readline = require('readline');
const nunjucks = require("nunjucks");
const program = require("commander")

program.option(
    "--network <network>",
    "network",
    "mainnet"
)

program.parse(process.argv)

async function processValidatorConf(network) {
  const fileStream = fs.createReadStream(__dirname + '/validators_'+network+'.conf');

  const rl = readline.createInterface({
    input: fileStream,
    crlfDelay: Infinity
  });
  let validators = [];
  for await (const line of rl) {
    // Each line in input.txt will be successively available here as `line`.
    if (line === "") continue;
    let vs = line.split(",")
    validators.push({
      consensusAddr: vs[0],
      feeAddr: vs[1],
    })
  }
  return validators
}

processValidatorConf(program.network).then(function (validators) {
  const data = {
    validators: validators
  };
  const templateString = fs.readFileSync(__dirname + '/validators.template').toString();
  const resultString = nunjucks.renderString(templateString, data);
  fs.writeFileSync(__dirname + '/validators.js', resultString);
  console.log("validators.js file updated.");
})
