import json
import os

from rich import print_json
from arbiter import CodeExecutor, Constraints


class PythonCodeExecutor(CodeExecutor):
    def get_compile_command(self, src: str) -> str:
        return ""

    def get_run_command(self, src: str) -> str:
        return f"python3 {src}/solution.py"


if __name__ == "__main__":
    constraints: Constraints = {
        "time_limit": 2,
        "memory_limit": 10,
        "memory_swap_limit": 0,  # No swap
        # Let's say we want to limit the CPU usage to 1 core (100%)
        "cpu_quota": 1000000,
        "cpu_period": 1000000,
    }
    WORK_DIR = "/Users/parthokr/Documents/Projects/python-packages/base-code-executor/"
    with PythonCodeExecutor(
            docker_image="cpp_image:v1",
            user="partho",
            src=os.path.join(WORK_DIR, "data/submission"),
            constraints=constraints,
            disable_compile=True,
    ) as executor:
        for result in executor.run():
            print_json(json.dumps(result), indent=4)

