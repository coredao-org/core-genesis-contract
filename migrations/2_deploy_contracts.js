const BytesLib = artifacts.require("BytesLib");
const BytesToTypes = artifacts.require("BytesToTypes");
const Memory = artifacts.require("Memory");
const RLPDecode = artifacts.require("RLPDecode");
const RLPEncode = artifacts.require("RLPEncode");
const SafeMath = artifacts.require("SafeMath");

const BtcLightClient = artifacts.require("BtcLightClientUnitMock");
const CandidateHub = artifacts.require("CandidateHubUnitMock");
const GovHub = artifacts.require("GovHubMock");
const RelayerHub = artifacts.require("RelayerHub");
const SlashIndicator = artifacts.require("SlashIndicatorUnitMock");
const SystemReward = artifacts.require("SystemRewardMock");
const ValidatorSet = artifacts.require("ValidatorSetMock");
const PledgeAgent = artifacts.require("PledgeAgentUnitMock");
const Burn = artifacts.require("Burn");

module.exports = async function(deployer, network, accounts) {
  await deployer.deploy(BytesLib);
  await deployer.deploy(BytesToTypes);
  await deployer.deploy(Memory);
  await deployer.deploy(RLPDecode);
  await deployer.deploy(RLPEncode);
  await deployer.deploy(SafeMath);

  deployer.link(BytesLib, [GovHub, SlashIndicator]);
  deployer.link(BytesToTypes, [BtcLightClient, CandidateHub, GovHub, RelayerHub, SlashIndicator, ValidatorSet, PledgeAgent, Burn]);
  deployer.link(Memory, [BtcLightClient, CandidateHub, GovHub, RelayerHub, SlashIndicator, ValidatorSet, PledgeAgent, Burn]);
  deployer.link(RLPDecode, [GovHub, ValidatorSet, SlashIndicator, CandidateHub]);
  deployer.link(RLPEncode, [CandidateHub, SlashIndicator, PledgeAgent]);
  deployer.link(SafeMath, [BtcLightClient, CandidateHub, RelayerHub, ValidatorSet, PledgeAgent]);

  let btcLightClientInstance;
  await deployer.deploy(BtcLightClient).then(function(_btcLightClientInstance){
    btcLightClientInstance=_btcLightClientInstance;
    btcLightClientInstance.init();
  });

  let candidateHubInstance;
  await deployer.deploy(CandidateHub).then(async function (_candidateHubInstance) {
    candidateHubInstance = _candidateHubInstance;
    await candidateHubInstance.init();
    if (network == 'develop' ||network=='soliditycoverage') {
        await candidateHubInstance.developmentInit();
    }
  });

  let govHubInstance;
  await deployer.deploy(GovHub).then(async function (_govHubInstance) {
    govHubInstance = _govHubInstance;
    await govHubInstance.init();
    if (network == 'develop' ||network=='soliditycoverage') {
        await govHubInstance.developmentInit();
    }
  });

  let relayerHubInstance;
  await deployer.deploy(RelayerHub).then(function (_relayerHubInstance) {
    relayerHubInstance = _relayerHubInstance;
    relayerHubInstance.init();
  });

  let slashIndicatorInstance;
  await deployer.deploy(SlashIndicator).then(async function (_slashIndicatorInstance) {
    slashIndicatorInstance = _slashIndicatorInstance;
    await slashIndicatorInstance.init();
    if (network == 'develop' ||network=='soliditycoverage') {
        await slashIndicatorInstance.developmentInit();
    }
  });

  let systemRewardInstance;
  await deployer.deploy(SystemReward).then(function (_systemRewardInstance) {
    systemRewardInstance = _systemRewardInstance;
  });

  let validatorSetInstance;
  await deployer.deploy(ValidatorSet).then(function (_validatorSetInstance) {
    validatorSetInstance = _validatorSetInstance;
    validatorSetInstance.init();
  });

  let pledgeAgentInstance;
  await deployer.deploy(PledgeAgent).then(function (_pledgeCandidateInstance) {
    pledgeAgentInstance = _pledgeCandidateInstance;
    pledgeAgentInstance.init();
  });

  let burnInstance;
  await deployer.deploy(Burn).then(function (_burnInstance) {
      burnInstance = _burnInstance;
      burnInstance.init();
  });

  btcLightClientInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  candidateHubInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  govHubInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  relayerHubInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  slashIndicatorInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  systemRewardInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  validatorSetInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  pledgeAgentInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);
  burnInstance.updateContractAddr(validatorSetInstance.address, slashIndicatorInstance.address, systemRewardInstance.address, btcLightClientInstance.address, relayerHubInstance.address, candidateHubInstance.address, govHubInstance.address, pledgeAgentInstance.address, burnInstance.address);

  systemRewardInstance.init();
};
