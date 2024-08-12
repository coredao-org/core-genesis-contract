import json
import os
from .. import common
from . import task as task_module
from . import chain_state
from . import constants


class Scenario:
    def __init__(self):
        self.init_round = 0
        self.round_tasks = {}
        self.chain = None

    def load(self, json_file):
        ok, init_round, round_tasks = self.__load(json_file)
        assert ok, f"Load json file error"

        self.init_round = init_round
        self.round_tasks = round_tasks

    def dump(self, write_file):
        assert self.init_round >= constants.MIN_ROUND
        assert self.round_tasks is not None and len(self.round_tasks) > 0

        json_data = {
            "init_round": self.init_round,
            "round_tasks": self.round_tasks
        }
        with open(write_file, 'w') as json_file:
            json.dump(json_data, json_file, indent=4)

    def set_init_round(self, init_round):
        self.init_round = init_round

    def set_round_tasks(self, round_tasks):
        self.round_tasks = round_tasks

    def get_task_count(self):
        assert self.round_tasks is not None

        count = 0
        for tasks in self.round_tasks.values():
            count += len(tasks)

        return count

    def execute(self):
        init_round = self.init_round
        round_tasks = self.round_tasks

        assert init_round >= constants.MIN_ROUND, f"Initial round is too small (init_round >= {constants.MIN_ROUND})"
        if init_round != common.get_current_round():
            common.set_round_tag(init_round)

        self.chain = chain_state.ChainState(init_round)
        last_advanced_round = 0

        for advanced_round, tasks in round_tasks.items():
            round = init_round + int(advanced_round)

            turn_round_count = int(advanced_round) - last_advanced_round
            if turn_round_count > 0:
                self.__execute_task(
                    int(advanced_round),
                    round - turn_round_count,
                    "TurnRound",
                    [turn_round_count]
                )

            assert round == common.get_current_round(), f"Invalid round {round}"

            for task in tasks:
                ##task[0] is task name
                ##task[1:] is execute params
                assert len(task) > 0
                self.__execute_task(
                    int(advanced_round),
                    round,
                    task[0],
                    task[1:] if len(task) > 1 else []
                )

            last_advanced_round = int(advanced_round)

    def __execute_task(self, advanced_round, round, task_name, task_params):
        TaskClass = getattr(task_module, task_name)
        task_inst = TaskClass()

        assert task_inst.is_supported(advanced_round), \
            f"Unsupport execute task {task_name} in advanced_round={advanced_round}"

        task_inst.set_round(round)
        task_inst.set_chain_state(self.chain)
        task_inst.pre_execute(task_params)
        task_inst.execute()
        task_inst.post_execute()

    def __load(self, json_file):
        # pattern = os.path.join(config_dir, '*.json')
        # json_files = glob.glob(pattern)

        # for json_file in json_files:
        if not os.path.isfile(json_file):
            return False

        return self.__parse(json_file)

    def __parse(self, json_file):
        init_round = 0
        round_tasks = []

        if not os.path.exists(json_file):
            return False, init_round, round_tasks

        ok = False

        try:
            with open(json_file, 'r') as file:
                data = json.load(file)
                init_round = data['init_round']
                round_tasks = data['round_tasks']
                ok = True

        except FileNotFoundError:
            print(f"Error: File {json_file} not found.")
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON in{json_file}, {e}")
        except Exception as e:
            print(f"Error: {e}")

        return ok, init_round, round_tasks
