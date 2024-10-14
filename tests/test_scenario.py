import pytest
from brownie import *
import os

from .scenario.scenario import Scenario
from .scenario.account_mgr import AccountMgr

init_account_mgr = AccountMgr.init_account_mgr

@pytest.mark.skip(reason="This test is temporarily skipped")
@pytest.mark.parametrize("file_name", [
    'example_scenario.json',
])
def test_scenario(file_name):
    init_account_mgr()
    scenario = Scenario()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'scenario', 'config', file_name)

    scenario.load(file_path)
    scenario.execute()
