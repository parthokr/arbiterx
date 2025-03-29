import logging
import os
import subprocess
import uuid
from abc import ABC, abstractmethod
from typing import Optional, TypedDict, Iterator

from rich.console import Console
from rich.logging import RichHandler
from rich.syntax import Syntax


class Constraints(TypedDict):
    time_limit: int  # in seconds
    memory_limit: int  # in MB
    memory_swap_limit: int  # in MB
    cpu_quota: int  # cgroup v2 compatible
    cpu_period: int  # cgroup v2 compatible


def setup_logger(name: str, level: str, log_file: Optional[str] = None):
    """Set up a logger with optional file logging and rich console output."""

    logger = logging.getLogger(name)

    # Convert string level to logging level (e.g., "DEBUG" → logging.DEBUG)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Formatter for file logs (plain text)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )

    # Rich handler for beautiful console logs
    console_handler = RichHandler(rich_tracebacks=True,
                                  show_time=True,
                                  show_level=True,
                                  show_path=True)
    console_handler.setLevel(log_level)

    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


class BaseCodeExecutor(ABC):
    def __init__(
            self,
            docker_image: str,
            user: str,
            non_root_user: str,
            src: str,
            constraints: Constraints,
            working_dir_in_container: str,
            container_name: Optional[str] = uuid.uuid4().hex,
            disable_compile: bool = False,
            lazy_container: bool = False,
            early_exit: bool = False,
            dry_run: bool = False,
    ):
        """
        Base class for code execution


        :param docker_image: Docker image to use for running the code
        :param user: Root user in the container to create and manage the cgroups
        :param non_root_user: Non-root user in the container to compile and run the code
        :param src: Source code directory. Expected to have a source file, input and output directories
        :param constraints: Constraints for the code execution (time, memory, etc.)
        :param working_dir_in_container: Working directory in the container where the code will be copied, compiled and run
        :param container_name: Name of the container. This will be auto-generated if not provided (default: uuid).
        :param disable_compile: Disable compilation of the code. Useful when the code is already compiled or interpreted.
        :param lazy_container: If True, the container will not be created immediately. It will be created when the first test is run.
        :param early_exit: If True, tests will stop as soon as one of the tests fails.
        :param dry_run: If True, the commands will be printed instead of running them.
        """
        self.dry_run = dry_run
        self.console = Console()

        if self.dry_run:
            self.console.print(f"[bold red]{'=' * 30}\
            Running in Dry Run mode\
            {'=' * 30}[/bold red]")

        log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.logger = setup_logger(self.__class__.__name__, log_level)

        self._check_docker_daemon()

        self.docker_image = docker_image
        self.user = user
        self.non_root_user = non_root_user
        self.src = src
        self.constraints = constraints
        self.working_dir_in_container = working_dir_in_container
        self.container_name = container_name
        self.disable_compile = disable_compile
        self.lazy_container = lazy_container
        self.container_id: Optional[str] = None
        self.early_exit = early_exit

        self._is_compiled: bool = False

        if not self.lazy_container:
            self._create_container()

    @staticmethod
    def format_cmd(cmd: list[str], debug: bool = False) -> str:
        """
        Format a command list to a string.
        If debug is True, the command will be returned as a string without escaping.

        :param cmd: Command as a list
        :param debug: If True, return the command as a string without escaping
        :return: Formatted command as a string
        """
        if debug:
            return " ".join(cmd)
        return " \\\n    ".join(cmd)

    def _check_docker_daemon(self):
        """Check if docker daemon is running"""
        self.logger.info("Checking docker daemon")
        try:
            cmd = ["docker", "info"]

            self.logger.debug(BaseCodeExecutor.format_cmd(cmd, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(BaseCodeExecutor.format_cmd(cmd), lexer="bash",
                           theme="monokai"))
                return
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = proc.communicate()
            if proc.returncode == 0:
                self.logger.info("Docker daemon is running")
            else:
                self.logger.error("Docker daemon is not running")
                self.logger.error(stderr)
                raise ValueError("Docker daemon is not running")

        except subprocess.CalledProcessError:
            self.logger.error("Docker daemon is not running")
            raise ValueError("Docker daemon is not running")

    def __enter__(self):
        if not self.disable_compile:
            self._compile()
        self._prepare_cgroup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup_container()

    def _create_container(self):
        self.logger.info("Creating container")

        # Build the docker command as a list
        docker_command = [
            "docker", "run",
            "--rm",
            "--interactive",
            "--tty",
            "--detach",
            "--mount",
            f"type=bind,source={self.src},target={self.working_dir_in_container}",
            "--workdir", self.working_dir_in_container,
            "--user", f"{self.user}",
            "--cgroupns", "private",
            "--privileged",
            "--memory", f"{self.constraints['memory_limit'] + 100}m",
            "--memory-swap", f"{self.constraints['memory_limit'] + \
                                self.constraints['memory_swap_limit'] + 100}m",
            "--name", self.container_name,
            self.docker_image,
            "sleep", "infinity"
        ]

        self.logger.debug(BaseCodeExecutor.format_cmd(docker_command, debug=True))

        if self.dry_run:
            # Print the command as a string for dry run
            self.console.print(
                Syntax(BaseCodeExecutor.format_cmd(docker_command), "bash",
                       theme="monokai"))
            return

        # Run the docker command using subprocess
        try:
            proc = subprocess.run(docker_command, capture_output=True, text=True,
                                  check=True)
            self.container_id = proc.stdout.strip()
            self.logger.info(f"Container created successfully: {self.container_id}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating container: {e.stderr}")
            raise ValueError("Error creating container")

    def _cleanup_container(self):
        self.logger.info(f"Stopping container")
        _cleanup_container_command = [
            "docker", "stop", self.container_id
        ]

        if self.dry_run:
            self.console.print(
                Syntax(BaseCodeExecutor.format_cmd(
                    _cleanup_container_command[:-1] + ["<container_id>"]),
                    "bash", theme="monokai"))
            return
        if self.container_id:
            self.logger.debug(
                BaseCodeExecutor.format_cmd(_cleanup_container_command, debug=True))
            subprocess.run(_cleanup_container_command)

    def _create_cgroup(self, identifier: str):
        try:
            self.logger.info(f"Creating cgroup for {identifier}")
            cgroup_command = [
                "docker", "exec",
                self.container_name,
                "mkdir", f"/sys/fs/cgroup/{identifier}"
            ]

            self.logger.debug(BaseCodeExecutor.format_cmd(cgroup_command, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(BaseCodeExecutor.format_cmd(cgroup_command), "bash",
                           theme="monokai"))
                return

            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)
            _, stderr = proc.communicate()
            exit_code = proc.returncode
            if exit_code == 0:
                self.logger.info(f"Cgroup for {identifier} created successfully")
            else:
                self.logger.error(f"Error creating cgroup for {identifier}")
                self.logger.error(stderr)
                raise ValueError(f"Error creating cgroup for {identifier}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating cgroup for {identifier}: {e.stderr}")
            raise ValueError(f"Error creating cgroup for {identifier}")

    def _prepare_cgroup(self) -> None:
        """
        This method prepares the cgroup for the container.
        There are several steps involved:
        1. Check if cgroup exists (specifically cgroup v2)
        2. Prepare the parent cgroup (for the container)
        3. Move all the processes to the parent cgroup
        4. Add cpu and memory to the subtree control at the root hierarchy

        :return: None
        """

        try:
            # check if cgroup exists
            self.logger.info("Checking if cgroup exists")
            cgroup_command = [
                "docker",
                "exec",
                self.container_name,
                "bash",
                "-c",
                "mount | grep cgroup"
            ]

            self.logger.debug(BaseCodeExecutor.format_cmd(cgroup_command, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(BaseCodeExecutor.format_cmd(cgroup_command), "bash",
                           theme="monokai"))
                return

            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            stdout, _ = proc.communicate()
            self.logger.debug(f"stdout: {stdout}")
            if "cgroup2" in stdout:
                self.logger.info("Cgroup exists")
            else:
                self.logger.error("Cgroup does not exist")
                raise ValueError("Cgroup does not exist")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking cgroup: {e.stderr}")
            raise ValueError("Error checking cgroup")


        try:
            self._create_cgroup("parent")
            self.logger.info("Preparing parent cgroup")
            cgroup_command = [
                "docker",
                "exec",
                self.container_name,
                "bash", "-c",
                "for pid in $(cat /sys/fs/cgroup/cgroup.procs); \
                do echo $pid > /sys/fs/cgroup/parent/cgroup.procs 2> /dev/null; done; \
                echo +cpu +memory > /sys/fs/cgroup/cgroup.subtree_control"
            ]

            self.logger.debug(BaseCodeExecutor.format_cmd(cgroup_command, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(BaseCodeExecutor.format_cmd(cgroup_command), "bash",
                           theme="monokai"))
                return

            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)
            stdout, stderr = proc.communicate()
            self.logger.debug(f"stdout: {stdout}")
            exit_code = proc.returncode
            if exit_code == 0:
                self.logger.info("Cgroup prepared successfully")

                # cat /sys/fs/cgroup/cgroup.subtree_control
                _cmd = [
                    "docker",
                    "exec",
                    self.container_name,
                    "cat", "/sys/fs/cgroup/cgroup.subtree_control"
                ]
                self.logger.debug(BaseCodeExecutor.format_cmd(_cmd, debug=True))
                proc = subprocess.Popen(_cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
                stdout, stderr = proc.communicate()
                self.logger.debug(f"stdout: {stdout}")

            else:
                self.logger.error("Error preparing cgroup")
                self.logger.error(stderr)
                raise ValueError("Error preparing cgroup")


        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error preparing cgroup: {e.stderr}")
            raise ValueError("Error preparing cgroup")

    def _set_limits(self, identifier: str):
        """
        Set limits for the cgroup.

        :param identifier: Identifier for the cgroup
        :return: None
        """
        try:
            self.logger.info(f"Setting limits for {identifier}")
            memory_limit = self.constraints.get("memory_limit", 256)
            time_limit = self.constraints.get("time_limit", 1)

            memory_limit = memory_limit * 1024 * 1024  # Convert to bytes

            cgroup_command = [
                "docker", "exec",
                self.container_name,
                "bash", "-c",
                f"echo {memory_limit} > /sys/fs/cgroup/{identifier}/memory.max",
                "&&",
                f"echo {self.constraints['memory_swap_limit']} > /sys/fs/cgroup/{identifier}/memory.swap.max",
                "&&",
                f"echo \"{self.constraints['cpu_quota']} {self.constraints['cpu_period']}\" > /sys/fs/cgroup/{identifier}/cpu.max",
            ]

            self.logger.debug(BaseCodeExecutor.format_cmd(cgroup_command, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(BaseCodeExecutor.format_cmd(cgroup_command), "bash",
                           theme="monokai"))
                return

            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)
            _, stderr = proc.communicate()
            exit_code = proc.returncode
            if exit_code == 0:
                self.logger.info(f"Limits set for {identifier}")
            else:
                self.logger.error(f"Error setting limits for {identifier}")
                self.logger.error(stderr)
                raise ValueError(f"Error setting limits for {identifier}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error setting limits for {identifier}: {e.stderr}")
            raise ValueError(f"Error setting limits for {identifier}")

    @abstractmethod
    def get_compile_command(self, src: str) -> str:
        """
        Get the command to compile the code.
        This will be ignored if `disable_compile` is True.

        :param src: Source code directory
        :return: String representing the compile command
        """
        pass

    @abstractmethod
    def get_run_command(self, src: str) -> str:
        """
        Get the command to run the code.
        This will be executed for each test case.

        :param src: Source code directory
        :return: String representing the run command
        """
        pass

    def _compile(self) -> None:
        """
        Compile the code using the provided compile command (from `get_compile_command`).
        This will be called only if `disable_compile` is False.

        :return: None
        """

        if self.disable_compile:
            raise ValueError("Compilation is disabled")
        self.logger.info(f"Compiling code")
        compile_command = self.get_compile_command(self.working_dir_in_container)
        cmd = [
            "docker",
            "exec",
            "--workdir", self.working_dir_in_container,
            self.container_name, "bash", "-c",
            f"su - {self.non_root_user} -c '{compile_command}'"
        ]

        self.logger.debug(BaseCodeExecutor.format_cmd(cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(BaseCodeExecutor.format_cmd(cmd), "bash", theme="monokai"))
            return

        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)

        stdout, stderr = proc.communicate()
        exit_code = proc.returncode
        if exit_code == 0:
            self._is_compiled = True
            self.logger.info("Compilation successful")
        else:
            self.logger.error("Compilation failed")
        print(stdout)
        print(stderr)
        print(f'Exit code: {exit_code}')

    def _get_stats(self, identifier: str):
        """
        Get the stats for the cgroup (memory peak, memory events, cpu stat).
        :param identifier:
        :return:
        """

        memory_peak_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/memory.peak"
        ]

        self.logger.debug(BaseCodeExecutor.format_cmd(memory_peak_cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(BaseCodeExecutor.format_cmd(memory_peak_cmd), "bash", theme="monokai"))
            return

        memory_peak = subprocess.run(memory_peak_cmd, capture_output=True, text=True)
        self.logger.debug(f"Memory peak: {memory_peak.stdout}")

        memory_events_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/memory.events"
        ]

        memory_events = subprocess.run(memory_events_cmd, capture_output=True, text=True)
        self.logger.info(f"Memory events: {memory_events.stdout}")

        cpu_stat_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/cpu.stat"
        ]

        cpu_stat = subprocess.run(cpu_stat_cmd, capture_output=True, text=True)
        self.logger.info(f"CPU stat: {cpu_stat.stdout}")

    def _run(self,
             test_case: int = 1,
             input_file: str | None = None,
             timeout: int | None = None
             ) -> tuple[str, str, int]:
        """
        Run a single test case with the provided run command (from `get_run_command`).
        This will be called for each test case.

        :param test_case: Test case number
        :param input_file: Input file for the test case (optional).
                        By default, it will look for input/input{test_case}.txt
        :param timeout: Timeout for running the command (from `get_run_command`).
                        This will be used as a fallback mechanism.
                        By default, it will be 5 times the time limit from constraints.
        :return: Tuple of stdout, stderr, exit_code
        """

        self._create_cgroup(f"test{test_case}")
        self._set_limits(f"test{test_case}")

        self.logger.info(f"[Test {test_case}] Running")
        run_command = self.get_run_command(self.working_dir_in_container)

        _input_file = f"{self.working_dir_in_container}/input/input{test_case}.txt"
        if input_file:
            _input_file = input_file

        if not timeout:
            timeout = self.constraints.get("time_limit", 1) * 5

        cmd = f"timeout {timeout} {run_command} < {_input_file}"

        docker_cmd = [
            "docker", "exec",
            "--workdir", self.working_dir_in_container,
            self.container_name, "bash", "-c",
            f"echo $$ > /sys/fs/cgroup/test{test_case}/cgroup.procs && su - {self.non_root_user} -c '{cmd}'"
        ]

        self.logger.debug(BaseCodeExecutor.format_cmd(docker_cmd, debug=True))

        if self.dry_run:
            self.console.print(Syntax(BaseCodeExecutor.format_cmd(docker_cmd),
                                      "bash",
                                      theme="monokai"))
            return "<stdout>", "<stderr>", 0

        self.logger.info(f"Running command: {' '.join(docker_cmd)}")
        proc = subprocess.Popen(docker_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)

        stdout, stderr = proc.communicate()
        exit_code = proc.returncode

        self.logger.info(f"Output: {stdout}")
        self.logger.error(f"Error: {stderr}")

        self.logger.info(f"Exit code: {exit_code}")

        memory_peak_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/test{test_case}/memory.peak"
        ]

        memory_peak = subprocess.run(memory_peak_cmd, capture_output=True, text=True)
        self.logger.info(f"Memory peak: {memory_peak.stdout}")

        memory_events_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/test{test_case}/memory.events"
        ]

        memory_events = subprocess.run(memory_events_cmd, capture_output=True, text=True)
        self.logger.info(f"Memory events: {memory_events.stdout}")

        cpu_stat_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/test{test_case}/cpu.stat"
        ]

        cpu_stat = subprocess.run(cpu_stat_cmd, capture_output=True, text=True)
        self.logger.info(f"CPU stat: {cpu_stat.stdout}")

        return stdout, stderr, exit_code

    def run(self,
            input_prefix: str = "input",
            output_prefix: str = "output",
            timeout: int | None = None) -> Iterator[tuple[str, str, int]]:
        """
        Run all the test cases. This will yield the results for each test case.
        All the test cases will be run in sequence as per the input and output files in
        the `input` and `output` directories.

        :param input_prefix: Prefix for the input files (default: input)
        :param output_prefix: Prefix for the output files (default: output)
        :param timeout: Optional timeout for running command for each test case.
                        This timeout is not essentially the time limit for the code
                        execution. It is the time limit for running command
                        (e.g., `timeout 5 <command from get_run_command>`)
                        for each test case and thus acts as a fallback mechanism.
                        Hence, it should be set to a value higher than the time limit
                        for the code execution otherwise the test cases will fail
                        prematurely.

        :return: Iterator of tuples containing stdout, stderr, exit_code
        """
        tests = os.listdir(f"{self.src}/input")
        self.logger.info(f"Running {len(tests)} tests")
        for i in range(1, len(tests) + 1):
            yield self._run(i,
                            f"{self.working_dir_in_container}/input/{input_prefix}{i}.txt",
                            timeout=timeout)


class CPPCodeExecutor(BaseCodeExecutor):
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
            user="root",
            non_root_user="partho",
            container_name="test",
            src="/Users/parthokr/Documents/Projects/python-packages/base-code-executor/data/submission12",
            constraints=constraints,
            working_dir_in_container="/app",
            disable_compile=False,
            lazy_container=False,
            early_exit=False,
            dry_run=False,
    ) as executor:
        # executor.compile()
        # executor.execute()
        for result in executor.run():
            stdout, stderr, exit_code = result
            # stdout = stdout.strip()[0:100]
            # stderr = stderr.strip()[0:100]
            print(f"stdout: \n{stdout}")
            print(f"stderr: \n{stderr}")
            print(f"exit_code: {exit_code}")
