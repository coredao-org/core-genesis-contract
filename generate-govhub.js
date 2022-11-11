const program = require("commander");
const fs = require("fs");
const nunjucks = require("nunjucks");

program.version("0.0.1");
program.option(
    "-t, --template <template>",
    "GovHub template file",
    "./contracts/GovHub.template"
);

program.option(
    "-o, --output <output-file>",
    "GovHub.sol",
    "./contracts/GovHub.sol"
)
program.option(
    "--initMembersBytes <initMembersBytes>",
    "initMembersBytes",
    ""
)

program.option(
    "--votingPeriod <votingPeriod>",
    "votingPeriod",
    201600
)

program.option(
    "--executePeriod <executePeriod>",
    "executePeriod",
    201600
)

program.option("--mock <mock>",
    "if use mock",
    false);


program.parse(process.argv);

const members = require("./init_members")
let initMembersBytes = program.initValidatorSetBytes;
if (initMembersBytes == ""){
    initMembersBytes = members.initMembers.slice(2);
}

const data = {
    initMembersBytes: initMembersBytes,
    votingPeriod: program.votingPeriod,
    executePeriod: program.executePeriod,
    mock: program.mock,
};

const templateString = fs.readFileSync(program.template).toString();
const resultString = nunjucks.renderString(templateString, data);
fs.writeFileSync(program.output, resultString);
console.log("GovHub file updated.");
