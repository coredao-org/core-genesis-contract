const program = require("commander");
const fs = require("fs");
const nunjucks = require("nunjucks");

const init_cycle = require("./init_cycle")

program.version("0.0.1");
program.option(
    "-t, --template <template>",
    "PledgeAgent template file",
    "./contracts/PledgeAgent.template"
);

program.option(
    "-o, --output <output-file>",
    "PledgeAgent.sol",
    "./contracts/PledgeAgent.sol"
)

program.option("--mock <mock>",
    "if use mock",
    false);


program.parse(process.argv);

const data = {
  roundInterval: init_cycle.roundInterval,
  blockPeriod: init_cycle.blockPeriod,
  epochLength: init_cycle.epochLength,
  mock: program.mock,
};

const templateString = fs.readFileSync(program.template).toString();
const resultString = nunjucks.renderString(templateString, data);
fs.writeFileSync(program.output, resultString);
console.log("PledgeAgent file updated.");
