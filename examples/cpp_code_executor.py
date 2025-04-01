import json
import os

from rich import print_json

from arbiterx import CodeExecutor, Constraints


class CPPCodeExecutor(CodeExecutor):
    def get_compile_command(self, src: str) -> str:
        return f"g++ -o {src}/a.out {src}/solution.cpp"

    def get_run_command(self, src: str) -> str:
        return f"{src}/a.out"


if __name__ == "__main__":
    constraints: Constraints = {
        "time_limit": 2,
        "memory_limit": 10,
        "memory_swap_limit": 0,  # No swap
        # Let's say we want to limit the CPU usage to 1 core (100%)
        "cpu_quota": 1000000,
        "cpu_period": 1000000,
    }
    WORK_DIR = os.path.join(os.getcwd(), "data", "cpp-submission")
    with CPPCodeExecutor(
            docker_image="cpp11:v1",
            src=WORK_DIR,
            user="sandbox",
            constraints=constraints,
    ) as executor:
        for result in executor.run(shuffle=True):
            print_json(json.dumps(result), indent=4)
