const program = require("commander");
const fs = require("fs");
const nunjucks = require("nunjucks");

const init_cycle = require("./init_cycle")

program.version("0.0.1");
program.option(
    "-t, --template <template>",
    "CandidateHub template file",
    "./contracts/CandidateHub.template"
);

program.option(
    "-o, --output <output-file>",
    "CandidateHub.sol",
    "./contracts/CandidateHub.sol"
)

program.option("--mock <mock>",
    "if use mock",
    false);


program.parse(process.argv);

const data = {
  initValidatorCount: init_cycle.validatorCount,
  mock: program.mock,
};

const templateString = fs.readFileSync(program.template).toString();
const resultString = nunjucks.renderString(templateString, data);
fs.writeFileSync(program.output, resultString);
console.log("CandidateHub file updated.");
