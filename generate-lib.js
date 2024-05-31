const program = require("commander");
const fs = require("fs");
const nunjucks = require("nunjucks");

const init_cycle = require("./init_cycle")

program.version("0.0.1");
program.option(
    "-t, --template <template>",
    "SatoshiPlus template file",
    "./contracts/lib/SatoshiPlusHelper.template"
);

program.option(
    "-o, --output <output-file>",
    "SatoshiPlusHelper.sol",
    "./contracts/lib/SatoshiPlusHelper.sol"
)

program.option("--mock <mock>",
    "if use mock",
    false);
program.option("-c, --chainid <chainid>", "chain id", "1116")


program.parse(process.argv);

const data = {
  chainid: program.chainid,
  initRoundInterval: init_cycle.roundInterval,
};

const templateString = fs.readFileSync(program.template).toString();
const resultString = nunjucks.renderString(templateString, data);
fs.writeFileSync(program.output, resultString);
console.log("SatoshiPlusHelper file updated.");
