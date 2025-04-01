## arbiterx


### Installation
```bash 
pip install arbiterx
```

### Directory structure of a test suite
```bash
submission
├── input
│   ├── input1.txt
│   └── input2.txt
|        ...
├── output
│   ├── output1.txt
│   └── output2.txt
|        ...
└── solution.py // The main file to be executed. Name can be anything.
```
#### See the `data/submission` directory for an example.

### Python Executor Example

```python
import json
import os

from rich import print_json # not necessary, just for pretty printing

from arbiterx import CodeExecutor, Constraints


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
        # cpu quota and period are in microseconds
        "cpu_quota": 1000000,
        "cpu_period": 1000000,
    }
    WORK_DIR = <submission_directory>
    with PythonCodeExecutor(
            user="sandbox", # Default is "nobody"
            docker_image="python312:v1",
            src=WORK_DIR,
            constraints=constraints,
            disable_compile=True,
    ) as executor:
        for result in executor.run():
            print_json(json.dumps(result), indent=4)
```

### C++ Executor Example

```python
import json

from rich import print_json
from arbiterx import CodeExecutor, Constraints


class CPPCodeExecutor(CodeExecutor):
    def get_compile_command(self, src: str) -> str:
        return f"g++ -o {src}/a.out {src}/main.cpp"

    def get_run_command(self, src: str) -> str:
        return f"{src}/a.out"


if __name__ == "__main__":
    constraints: Constraints = {
        "time_limit": 2,
        "memory_limit": 10,
        "memory_swap_limit": 0, 
        "cpu_quota": 1000000,
        "cpu_period": 1000000,
    }
    WORK_DIR = <submission_directory>
    with CPPCodeExecutor(
            user="sandbox",
            docker_image="cpp11:v1",
            src=WORK_DIR,
            constraints=constraints,
    ) as executor:
        for result in executor.run(shuffle=True):
            print_json(json.dumps(result), indent=4)

```

### Output
```json
{
    "test_case": 1,
    "exit_code": 0,
    "stats": {
        "memory_peak": 5332992,
        "memory_events": {
            "low": 0,
            "high": 0,
            "max": 0,
            "oom": 0,
            "oom_kill": 0,
            "oom_group_kill": 0
        },
        "cpu_stat": {
            "usage_usec": 19407,
            "user_usec": 8733,
            "system_usec": 10674,
            "nr_periods": 0,
            "nr_throttled": 0,
            "throttled_usec": 0,
            "nr_bursts": 0,
            "burst_usec": 0
        },
        "pids_peak": 4
    },
    "verdict": "AC",
    "verdict_label": "Accepted",
    "verdict_details": "The program ran successfully and produced the correct output.",
    "input": "3\n1\n2\n3\n",
    "actual_output": "YES\nNO\nYES\n",
    "expected_output": "YES\nNO\nYES\n"
}
```
Sometimes we need custom checker as not all problems can have a predefined output.
This makes sense when the expected output is not deterministic or the expected output is not unique.
Some criteria may be different for different problems.
* Criterion 1: The output should be case-insensitive, e.g., `YES` and `yes` should be considered the same.
* Criterion 2: Order of the output should not matter, e.g., `1 2 3` and `3 2 1` should be considered the same.
* Criterion 3: Output may not be unique, e.g., for a problem where the output is a path from source to destination, there can be multiple paths.

In such cases, we need some middleware to transform the output to a common format that complies with the problem constraints while keeping the original output intact.

In that case we can pass in our custom checker script by its path.
Currently `arbiterx` only supports python scripts as custom checkers.
### An example demonstrating the use of custom checker

---
The custom checker is invoked with 3 arguments:
- Argument 1: input file path
- Argument 2: actual output file path
- Argument 3: expected output file path

The checker should exit with status code 0 if the output is correct, otherwise exit with status code 1.

#### Create a custom checker script `custom_checker.py`
```python
#!/usr/bin/python3

import sys

input_file = sys.argv[1]
output_file = sys.argv[2]
expected_output_file = sys.argv[3]

with open(output_file, "r") as f:
    output = f.read().strip()

with open(expected_output_file, "r") as f:
    expected_output = f.read().strip()

if output.upper() == expected_output:
    sys.exit(0)
else:
    sys.exit(1)
```
Make sure to put the shebang at the top of the script.

Then you should mark the script as executable.
```bash
chmod +x custom_checker.py
```

#### Now let's use the custom checker in the executor
```python
...
    WORK_DIR = <submission_directory>
    with PythonCodeExecutor(
            user="sandbox",
            docker_image="python312:v1",
            src=os.path.join(WORK_DIR),
            constraints=constraints,
            disable_compile=True,
    ) as executor:
        for result in executor.run(checker=os.path.join(WORK_DIR, "custom_checker.py")):
            print_json(json.dumps(result), indent=4)
```

For examples in detail, refer to the [examples](https://github.com/parthokr/arbiterx/tree/main/examples) directory.

### Set log level
```bash
export LOG_LEVEL=DEBUG
```
This will print the logs in the console.

### Possible verdicts
| Verdict | Label                     | Description |
|---------|---------------------------|-------------|
| AC      | Accepted                  | The program ran successfully and produced the correct output. |
| WA      | Wrong Answer               | The program ran successfully but produced incorrect output. |
| TLE     | Time Limit Exceeded        | The program took longer than the allowed execution time. |
| MLE     | Memory Limit Exceeded      | The program used more memory than the allowed limit. |
| RE      | Runtime Error              | The program terminated abnormally with a non-zero exit code. |
| OLE     | Output Limit Exceeded      | The program produced more output than the allowed limit. |
| CE      | Compilation Error          | The program failed to compile successfully. |
| ILE     | Idleness Limit Exceeded    | The program did not produce any output for too long, often indicating an infinite loop that does not consume CPU time. |
| JE      | Judgement Error            | The judgement process failed to produce a verdict. |

See the `arbiterx/verdicts.py` file for more details.

#### Exceptions
| Exception                              | Description |
|----------------------------------------|-------------|
| `CMDError`                             | Exception raised when there is an error in running a command. |
| `DockerDaemonError`                    | Exception raised when the Docker daemon is not running. |
| `ContainerCreateError`                 | Exception raised when there is an error in creating the container. |
| `ContainerCleanupError`                | Exception raised when there is an error in cleaning up the container. |
| `CgroupMountError`                     | Exception raised when the cgroup is not mounted. |
| `CgroupCreateError`                    | Exception raised when there is an error in creating the cgroup. |
| `CgroupCleanupError`                   | Exception raised when there is an error in cleaning up the cgroup. |
| `CgroupControllerReadError`            | Exception raised when there is an error in reading the `cgroup.controllers` file. |
| `CgroupControllerError`                | Exception raised when required controllers are not allowed in the cgroup (e.g., `cpu` and `memory` controllers are missing in `cgroup.controllers`). |
| `CgroupSubtreeControlError`            | Exception raised when required controllers are not set in the `cgroup.subtree_control` file. |
| `CgroupSubtreeControlReadError`        | Exception raised when there is an error in reading the `cgroup.subtree_control` file. |
| `CgroupSubtreeControlWriteError`       | Exception raised when there is an error in writing the `cgroup.subtree_control` file. |
| `CgroupSetLimitsError`                 | Exception raised when there is an error in setting the limits for the cgroup (e.g., writing `memory.max`, `memory.swap.max`, etc.). |
| `CompileError`                         | Exception raised when there is an error in compiling the code. |
| `RunError`                             | Exception raised when there is an error in running the code. |
| `TestQueueInitializationError`         | Exception raised when there is an error initializing the test queue. |
| `MemoryPeakReadError`                  | Exception raised when there is an error in reading peak memory usage. |
| `MemoryEventsReadError`                | Exception raised when there is an error in reading memory events. |
| `CPUStatReadError`                     | Exception raised when there is an error in reading CPU statistics. |
| `PIDSPeakReadError`                    | Exception raised when there is an error in reading the peak number of PIDs. |
| `EarlyExitError`                       | Exception raised when the program exits earlier than expected. |
| `ActualOutputCleanupError`             | Exception raised when there is an error in cleaning up the actual output. |

See the `arbiterx/exceptions.py` file for more details.

### Some useful parameters
- `disable_compile`: Disable compilation of the code. Useful when the code is already compiled or the code is in an interpreted language.
- `dry_run`: Pretty print the commands that will be executed.
```python
with PythonCodeExecutor(
        ...
        dry_run=True,
) as executor:
    for result in executor.run():
        ...
```

- `shuffle`: Randomly shuffle the test cases before running them.
```python
with CPPCodeExecutor(..) as executor:
    for result in executor.run(shuffle=True):
        ...
```
- `working_dir_in_container`: The working directory in the container. Default is `/app`.
```python
with CPPCodeExecutor(
        ...
        working_dir_in_container="/sandbox",
) as executor:
    for result in executor.run():
        ...
```
- `early_exit`: Exit the loop as soon as a verdict is not `AC`.
```python
with CPPCodeExecutor(
        ...
) as executor:
    for result in executor.run(early_exit=True):
        ...
```

- `lazy_container`: Create container on the first run. Default is `False` which creates when the context manager is created.
```python
with CPPCodeExecutor(
        ...
        lazy_container=True,
) as executor:
    for result in executor.run():
        ...
```

- `cgroup_mount_path`: The path where the cgroup is mounted on host. Default is `/sys/fs/cgroup`.
This is used when bind mounting the cgroup to the container.
```python
with CPPCodeExecutor(
        ...
        cgroup_mount_path="/some/custom/path",
) as executor:
    for result in executor.run():
        ...
```
