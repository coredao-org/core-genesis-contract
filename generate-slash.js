const program = require("commander");
const fs = require("fs");
const nunjucks = require("nunjucks");

program.version("0.0.1");
program.option(
    "-t, --template <template>",
    "SlashIndicator template file",
    "./contracts/SlashIndicator.template"
);

program.option(
    "-o, --output <output-file>",
    "SlashIndicator.sol",
    "./contracts/SlashIndicator.sol"
)
program.option("--mock <mock>",
    "if use mock",
    false);
program.option("-c, --chainid <chainid>", "chain id", "1116")

program.parse(process.argv);

const data = {
  mock: program.mock,
  chainid: program.chainid
};

const templateString = fs.readFileSync(program.template).toString();
const resultString = nunjucks.renderString(templateString, data);
fs.writeFileSync(program.output, resultString);
console.log("SlashIndicator file updated.");
