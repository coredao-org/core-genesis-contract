import pytest
from .scenario.scenario_generator import ScenarioGenerator
from .scenario.scenario import Scenario
from .scenario.account_mgr import AccountMgr
import os


def make_failed_scenario_file_path(start_round, stop_round, candidate_count, delegator_count):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = f"{start_round}_{stop_round}_{candidate_count}_{delegator_count}_error.json"
    file_path = os.path.join(base_dir, 'scenario', 'config', file_name)
    return file_path


@pytest.mark.skip(reason="This test is temporarily skipped")
@pytest.mark.parametrize("start_round,stop_round,candidate_count,delegator_count", [
    [7, 17, 6, 5],
    [10, 50, 26, 15]
])
def test_random_scenario(
        start_round,
        stop_round,
        candidate_count,
        delegator_count):
    AccountMgr.init_account_mgr()
    generator = ScenarioGenerator()
    scenario = generator.generate(start_round, stop_round, candidate_count, delegator_count)

    try:
        scenario.execute()
    except Exception as e:
        # when execution fails, dump the scenario configuration for issue diagnosis and execution verification
        file_path = make_failed_scenario_file_path(start_round, stop_round, candidate_count, delegator_count)
        scenario.dump(file_path)
        print(f"An random scenario {file_path} executed: {e}")
        assert False

    print(f"Executed {scenario.get_task_count()} scenario tasks")
