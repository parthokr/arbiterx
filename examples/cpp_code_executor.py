import json

from rich import print_json
from arbiter import CodeExecutor, Constraints


class CPPCodeExecutor(CodeExecutor):
    def get_compile_command(self, src: str) -> str:
        return f"g++ -o {src}/a.out {src}/main.cpp"

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
    with CPPCodeExecutor(
            docker_image="cpp_image:v1",
            user="partho",
            src="/Users/parthokr/Documents/Projects/python-packages/base-code-executor/data/submission12",
            constraints=constraints,
            working_dir_in_container="/app",
            disable_compile=False,
            lazy_container=False,
            early_exit=False,
            dry_run=False,
    ) as executor:
        for result in executor.run(shuffle=True):
            print_json(json.dumps(result), indent=4)

