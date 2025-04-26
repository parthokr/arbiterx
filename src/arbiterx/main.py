import os
import random
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from collections import deque
from typing import Literal, Optional, Iterator

from rich.console import Console
from rich.syntax import Syntax

from arbiterx.exceptions import (CMDError, DockerDaemonError,
                                 ContainerCreateError, ContainerCleanupError,
                                 CgroupMountError, CgroupCreateError,
                                 CgroupCleanupError, CgroupControllerError,
                                 CgroupSubtreeControlError,
                                 CgroupSubtreeControlWriteError,
                                 CgroupSetLimitsError, CompileError, InvalidVolumeError,
                                 TestQueueInitializationError,
                                 MemoryPeakReadError, MemoryEventsReadError,
                                 CPUStatReadError, PIDSPeakReadError,
                                 ActualOutputCleanupError, EarlyExitError)
from arbiterx.logger import setup_logger
from arbiterx.types import Constraints, TestResult
from arbiterx.types import MemoryEvents, CPUStat, Stats
from arbiterx.verdicts import Verdict


class CodeExecutor(ABC):
    def __init__(
            self,
            docker_image: str,
            src: str,
            constraints: Constraints,
            volume: str | None = None,
            src_in_volume: str | None = None,
            working_dir_in_container: str = "/app",
            user: str = "nobody",
            cgroup_mount_path: str = "/sys/fs/cgroup",
            container_name: Optional[str] = uuid.uuid4().hex,
            disable_compile: bool = False,
            lazy_container: bool = False,
            dry_run: bool = False,
    ):
        """
        Base class for code execution

        Args:
            docker_image (str): Docker image to use for running the code
            src (str): Source code directory. Expected to have a source file,
                        input and expected output directories.
                        `src` will be mounted in the container at `working_dir_in_container`
                        as a bind mount. 
            constraints (Constraints): Constraints for the code execution.
            volume (str | None): Docker volume where source and test files are stored.
                                This may be used if `arbiterx` is intended to be run
                                in a container. The volume will be mounted in the container
                                for the image `docker_image` at `working_dir_in_container`.
                                Defaults to None.
            src_in_volume (str | None): Path to the test relaetd files in the volume.
                                If you have no volume specified, then skip this.
                                Otherwise an error may be raised.
                                Defaults to None.
            working_dir_in_container (str): Working directory in the container.
            user (str, optional): Non-root user in the container to compile and
                                    run the code. Defaults to "nobody".
            cgroup_mount_path (str, optional): Path to mount the cgroup in the
                                                container. Defaults to "/sys/fs/cgroup".
            container_name (Optional[str], optional): Name of the container.
                                                        Defaults to uuid.
            disable_compile (bool, optional): Disable compilation of the code.
                                                Defaults to False.
            lazy_container (bool, optional): If True, the container will not be
                                                created immediately. It will be created
                                                when the first test is run.
                                                Defaults to False.
            dry_run (bool, optional): If True, the commands will be printed instead of
                                        running them.
        """
        self.id = uuid.uuid4().hex  # Unique identifier for cgroup

        self.dry_run = dry_run
        self.console = Console()

        if self.dry_run:
            self.console.print(f"[bold red]{'=' * 30}\
            Running in Dry Run mode\
            {'=' * 30}[/bold red]")

        log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.logger = setup_logger("arbiterx", log_level)

        self._check_docker_daemon()

        self.docker_image = docker_image
        self.user = user
        self.src = src
        self.constraints = constraints
        self.volume = volume
        self.src_in_volume = src_in_volume
        self.working_dir_in_container = working_dir_in_container
        self.cgroup_mount_path = cgroup_mount_path
        self.container_name = container_name
        self.disable_compile = disable_compile
        self.lazy_container = lazy_container
        self.container_id: Optional[str] = None

        self._is_compiled: bool = False

    @staticmethod
    def format_cmd(cmd: list[str], debug: bool = False) -> str:
        """Formats a command list to a string for logging/display.

        Args:
            cmd: Command as a list of strings.
            debug: If True, the command is returned as a string without escaping.

        Returns:
            Formatted command as a string.
        """
        if debug:
            return " ".join(cmd)
        return " \\\n    ".join(cmd)

    def _check_docker_daemon(self):
        """Checks if the Docker daemon is running.

        Raises:
            DockerDaemonError: If the Docker daemon is not running.
        """
        self.logger.info("Checking docker daemon")
        cmd = ["docker", "info"]

        self.logger.debug(CodeExecutor.format_cmd(cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cmd), lexer="bash",
                       theme="monokai"))
            return

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = proc.communicate()
            if proc.returncode == 0:
                self.logger.info("Docker daemon is running")
            else:
                self.logger.error("Docker daemon is not running")
                self.logger.error(stderr)
                raise DockerDaemonError("Docker daemon is not running")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Docker daemon is not running: {e.stderr}")
            raise CMDError(f"Docker daemon is not running: {e.with_traceback(e.__traceback__)}")

    def __enter__(self):
        """Enters the context, creating the container and setting up cgroups.

        Returns:
            self: The CodeExecutor instance.
        """
        self.logger.debug("Entering context")
        self._check_mount_type()

        if not self.lazy_container:
            self._create_container()

        self._check_cgroup_mount()
        self._check_cgroup_controllers()
        try:
            self._check_cgroup_subtree_control()
        except CgroupSubtreeControlError:
            self._set_subtree_control()

        if not self.disable_compile:
            self._compile()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exits the context, cleaning up the container and cgroups.
        Args:
            exc_type: Exception type.
            exc_val: Exception value.
            exc_tb: Exception traceback.
        """
        self.logger.debug("Exiting context")
        self._cleanup_container()

    def _check_mount_type(self):
        if self.volume is None:
            if not os.path.exists(self.src):
                raise FileNotFoundError(f"Source directory {self.src} does not exist")
            if not os.path.isdir(self.src):
                raise NotADirectoryError(f"Source {self.src} is not a directory")
            if not os.access(self.src, os.R_OK):
                raise PermissionError(f"Source {self.src} is not readable")
            if not os.access(self.src, os.W_OK):
                raise PermissionError(f"Source {self.src} is not writable")
        
        if self.volume is not None:
            if "/" in self.volume:
                raise InvalidVolumeError("Volume name cannot contain '/'")


    def _create_container(self):
        """Creates a Docker container with the specified constraints.

        Raises:
            ContainerCreateError: If there is an error creating the container.
        """
        self.logger.info("Creating container")

        # Build the docker command as a list
        docker_command = [
            "docker", "run",
            "--rm",
            "--interactive",
            "--tty",
            "--detach",
            "--mount",
            f"type=bind,source={self.src},target={self.working_dir_in_container}" if self.volume is None else f"type=volume,source={self.volume},target={self.working_dir_in_container}",
            "--mount",
            f"type=bind,source={self.cgroup_mount_path},target={self.cgroup_mount_path}",
            "--cgroupns", "host",
            "--workdir", self.working_dir_in_container,
            "--user", "0:0",  # Run as root (but we will run user code as non-root user)
            "--memory", f"{self.constraints['memory_limit'] + 100}m",
            "--memory-swap", f"{self.constraints['memory_limit'] + \
                                self.constraints['memory_swap_limit'] + 100}m",
            "--name", self.container_name,
            self.docker_image,
            "sleep", "infinity"
        ]

        self.logger.debug(CodeExecutor.format_cmd(docker_command, debug=True))

        if self.dry_run:
            # Print the command as a string for dry run
            self.console.print(
                Syntax(CodeExecutor.format_cmd(docker_command), "bash",
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
            raise ContainerCreateError(f"Error creating container")

    def _cleanup_container(self):
        """Cleans up the Docker container.

        Raises:
            ContainerCleanupError: If there is an error cleaning up the container.
        """
        self.logger.info(f"Cleaning up container: {self.container_name}")
        # stop the container using the container id
        _cleanup_container_command = [
            "docker", "container", "stop", self.container_id
        ]

        if self.dry_run:
            # create a demo command for dry run using the container name
            _cleanup_container_command_demo = [
                "docker", "container", "stop", self.container_name
            ]
            self.console.print(
                Syntax(CodeExecutor.format_cmd(
                    _cleanup_container_command_demo, debug=True),
                    "bash", theme="monokai"))
            return
        try:
            if self.container_id:
                self.logger.debug(
                    CodeExecutor.format_cmd(_cleanup_container_command, debug=True))
                subprocess.run(_cleanup_container_command)
                self.logger.info(f"Container stopped successfully")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error stopping container: {e.stderr}")
            raise ContainerCleanupError("Error stopping container")

    def _check_cgroup_mount(self):
        """Check if cgroup2 is mounted.

        Raises:
            CgroupMountError: If cgroup is not mounted.
        """
        self.logger.info("Checking cgroup")
        cgroup_command = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            "mount | grep cgroup"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return
        try:
            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            stdout, _ = proc.communicate()
            self.logger.debug(f"stdout: {stdout}")
            if "cgroup2" in stdout:
                self.logger.info("Cgroup exists")
            else:
                self.logger.error("Cgroup mount not found")
                raise CgroupMountError("Cgroup mount not found")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking cgroup: {e.stderr}")
            raise CMDError(f"Error checking cgroup: {e.with_traceback(e.__traceback__)}")

    def _check_cgroup_controllers(self):
        """Check if the parent cgroup allows the required controllers (cpu, memory, etc.)

        Raises:
            CgroupControllerError: If the required controllers are not allowed.
        """
        self.logger.info("Checking cgroup controllers")
        cgroup_command = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            "cat /sys/fs/cgroup/cgroup.controllers"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return

        try:
            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            stdout, _ = proc.communicate()
            self.logger.debug(f"stdout: {stdout}")
            if "cpu" in stdout and "memory" in stdout:
                self.logger.info("Required controllers are allowed")
            else:
                self.logger.error("Required controllers are not allowed")
                raise CgroupControllerError("Required controllers are not allowed")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking cgroup controllers: {e.stderr}")
            raise CMDError(f"Error checking cgroup controllers: {e.with_traceback(e.__traceback__)}")

    def _set_subtree_control(self):
        """Set the required controllers in the cgroup subtree.

        Raises:
            CgroupSubtreeControlWriteError: If there is an error in setting the
                                            required controllers in the cgroup subtree.
        """
        self.logger.info("Setting cgroup subtree control")
        cgroup_command = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            "echo '+cpu +memory' > /sys/fs/cgroup/cgroup.subtree_control"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return

        try:
            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            _, stderr = proc.communicate()
            exit_code = proc.returncode
            if exit_code == 0:
                self.logger.info("Cgroup subtree control set successfully")
            else:
                self.logger.error("Error setting cgroup subtree control")
                raise CgroupSubtreeControlWriteError(
                    "Error setting cgroup subtree control")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error setting cgroup subtree control: {e.stderr}")
            raise CMDError(
                f"Error setting cgroup subtree control: {e.with_traceback(e.__traceback__)}")

    def _check_cgroup_subtree_control(self):
        """Check if required controllers are allowed in the cgroup subtree.
        If not allowed, set the required controllers in the cgroup subtree.

        Raises:
            CgroupSubtreeControlError: If the required controllers are not allowed.
        """

        self.logger.info("Checking cgroup subtree control")
        cgroup_command = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            "cat /sys/fs/cgroup/cgroup.subtree_control"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            # artificially raise an error
            raise CgroupSubtreeControlError(
                "Required controllers are not allowed in the cgroup subtree")

        try:
            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            stdout, _ = proc.communicate()
            self.logger.debug(f"stdout: {stdout}")
            if "cpu" in stdout and "memory" in stdout:
                self.logger.info(
                    "Required controllers are allowed in the cgroup subtree")
            else:
                self.logger.error(
                    "Required controllers are not allowed in the cgroup subtree")
                raise CgroupSubtreeControlError(
                    "Required controllers are not allowed in the cgroup subtree")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking cgroup subtree control: {e.stderr}")
            raise CMDError(
                f"Error checking cgroup subtree control: {e.with_traceback(e.__traceback__)}")

    def _create_cgroup(self, identifier: str):
        """Create a cgroup for the given identifier.

        Args:
            identifier (str): Identifier for the cgroup.

        Raises:
            CgroupCreateError: If there is an error creating the cgroup.
        """

        self.logger.info(f"Creating cgroup for {identifier}")
        cgroup_command = [
            "docker", "exec",
            self.container_name,
            "mkdir", f"/sys/fs/cgroup/{identifier}"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return
        try:
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
                raise CgroupCreateError(f"Error creating cgroup for {identifier}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating cgroup for {identifier}: {e.stderr}")
            raise CMDError(
                f"Error creating cgroup for {identifier}: {e.with_traceback(e.__traceback__)}")

    def _cleanup_cgroup(self, identifier: str):
        """Clean up the cgroup for the given identifier.

        Args:
            identifier (str): Identifier for the cgroup.

        Raises:
            CgroupCleanupError: If there is an error cleaning up the cgroup.
        """
        self.logger.info(f"Cleaning up cgroup for {identifier}")
        cgroup_command = [
            "docker", "exec",
            self.container_name,
            "rmdir", f"/sys/fs/cgroup/{identifier}"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return
        try:
            proc = subprocess.Popen(cgroup_command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)
            _, stderr = proc.communicate()
            exit_code = proc.returncode
            if exit_code == 0:
                self.logger.info(f"Cgroup for {identifier} cleaned up successfully")
            else:
                self.logger.error(f"Error cleaning up cgroup for {identifier}")
                self.logger.error(stderr)
                raise CgroupCleanupError(f"Error cleaning up cgroup for {identifier}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error cleaning up cgroup for {identifier}: {e.stderr}")
            raise CMDError(
                f"Error cleaning up cgroup for {identifier}: {e.with_traceback(e.__traceback__)}")

    def _set_limits(self, identifier: str):
        """Set limits for the cgroup.

        Args:
            identifier (str): Identifier for the cgroup.

        Raises:
            CgroupSetLimitsError: If there is an error setting the limits.
        """
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

        self.logger.debug(CodeExecutor.format_cmd(cgroup_command, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cgroup_command), "bash",
                       theme="monokai"))
            return

        try:
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
                raise CgroupSetLimitsError(f"Error setting limits for {identifier}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error setting limits for {identifier}: {e.stderr}")
            raise CMDError(
                f"Error setting limits for {identifier}: {e.with_traceback(e.__traceback__)}")

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
            raise CompileError("Compilation is disabled")

        try:
            self.logger.info(f"Compiling code")
            compile_command = self.get_compile_command(self.working_dir_in_container)
            cmd = [
                "docker",
                "exec",
                "--workdir", self.working_dir_in_container,
                self.container_name, "bash", "-c",
                f"su - {self.user} -c '{compile_command}'"
            ]

            self.logger.debug(CodeExecutor.format_cmd(cmd, debug=True))

            if self.dry_run:
                self.console.print(
                    Syntax(CodeExecutor.format_cmd(cmd), "bash", theme="monokai"))
                return

            proc = subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)

            stdout, stderr = proc.communicate()
            exit_code = proc.returncode
            self.logger.debug(f'Compile stdout: {stdout}')
            self.logger.debug(f'Compile stderr: {stderr}')
            self.logger.debug(f'Compile exit code: {exit_code}')

            if exit_code == 0:
                self._is_compiled = True
                self.logger.info("Compilation successful")
            else:
                self.logger.error("Compilation failed")
                raise CompileError(stderr)

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error compiling code: {e.stderr}")
            raise CMDError(f"Error compiling code: {e.with_traceback(e.__traceback__)}")

    def _get_memory_peak(self, identifier: str) -> int:
        """
        Get the memory stats for the cgroup (memory peak, memory events).

        Args:
            identifier: Identifier for the cgroup

        Returns:
            int: Memory peak in bytes

        Raises:
            CMDError: If there is an error in getting memory stats
        """

        memory_peak_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/memory.peak"
        ]

        self.logger.debug(CodeExecutor.format_cmd(memory_peak_cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(memory_peak_cmd), "bash",
                       theme="monokai"))
            return

        try:
            memory_peak = subprocess.Popen(memory_peak_cmd,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           text=True)
            stdout, stderr = memory_peak.communicate()
            exit_code = memory_peak.returncode
            self.logger.debug(f"Memory peak: {stdout}")
            self.logger.debug(f"Memory peak stderr: {stderr}")
            self.logger.debug(f"Memory peak exit code: {exit_code}")

            if exit_code != 0:
                raise MemoryPeakReadError(f"Error getting memory peak: {stderr}")

            return int(stdout)

        except OSError as e:
            self.logger.error(f"Error getting memory peak: {e}")
            raise CMDError(f"Error getting memory peak: {e.with_traceback(e.__traceback__)}")

        except subprocess.SubprocessError as e:
            self.logger.error(f"Error running subprocess: {e}")
            raise CMDError(f"Error running subprocess: {e.with_traceback(e.__traceback__)}")

    def _get_memory_events(self, identifier: str) -> MemoryEvents:
        """
        Get the memory events for the cgroup.

        Args:
            identifier: Identifier for the cgroup

        Returns:
            MemoryEvents: Memory events as a dictionary

        Raises:
            CMDError: If there is an error in getting memory events
        """

        memory_events_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/memory.events"
        ]

        self.logger.debug(CodeExecutor.format_cmd(memory_events_cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(memory_events_cmd), "bash",
                       theme="monokai"))
            return

        try:
            memory_events = subprocess.Popen(memory_events_cmd,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE,
                                             text=True)
            stdout, stderr = memory_events.communicate()
            exit_code = memory_events.returncode
            self.logger.debug(f"Memory events: {stdout}")
            self.logger.debug(f"Memory events stderr: {stderr}")
            self.logger.debug(f"Memory events exit code: {exit_code}")

            if exit_code != 0:
                raise MemoryEventsReadError(f"Error getting memory events: {stderr}")

            _low = _high = _max = _oom = _oom_kill = _oom_group_kill = 0

            for line in stdout.splitlines():
                key, value = line.split()
                if key == "low":
                    _low = int(value)
                elif key == "high":
                    _high = int(value)
                elif key == "max":
                    _max = int(value)
                elif key == "oom":
                    _oom = int(value)
                elif key == "oom_kill":
                    _oom_kill = int(value)
                elif key == "oom_group_kill":
                    _oom_group_kill = int(value)

            return MemoryEvents(low=_low, high=_high, max=_max, oom=_oom,
                                oom_kill=_oom_kill, oom_group_kill=_oom_group_kill)
        except OSError as e:
            self.logger.error(f"Error getting memory events: {e}")
            raise CMDError(f"Error getting memory events: {e.with_traceback(e.__traceback__)}")

        except subprocess.SubprocessError as e:
            self.logger.error(f"Error running subprocess: {e}")
            raise CMDError(f"Error running subprocess: {e.with_traceback(e.__traceback__)}")

    def _get_cpu_stat(self, identifier: str) -> CPUStat:
        """
        Get the CPU stats for the cgroup.

        Args:
            identifier: Identifier for the cgroup

        Returns:
            CPUStat: CPU stats as a dictionary

        Raises:
            CPUStatReadError: If there is an error in reading cpu.stat
            CMDError: If there is an error in running the subprocess
        """

        cpu_stat_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/cpu.stat"
        ]

        self.logger.debug(CodeExecutor.format_cmd(cpu_stat_cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(cpu_stat_cmd), "bash",
                       theme="monokai"))
            return

        try:
            cpu_stat = subprocess.Popen(cpu_stat_cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
            stdout, stderr = cpu_stat.communicate()
            exit_code = cpu_stat.returncode
            self.logger.debug(f"CPU stat: {stdout}")
            self.logger.debug(f"CPU stat stderr: {stderr}")
            self.logger.debug(f"CPU stat exit code: {exit_code}")

            if exit_code != 0:
                raise CPUStatReadError(f"Error getting CPU stat: {stderr}")

            usage_usec = user_usec = system_usec = nr_periods = nr_throttled = \
                throttled_usec = nr_bursts = burst_usec = 0

            for line in stdout.splitlines():
                key, value = line.split()
                if key == "usage_usec":
                    usage_usec = int(value)
                elif key == "user_usec":
                    user_usec = int(value)
                elif key == "system_usec":
                    system_usec = int(value)
                elif key == "nr_periods":
                    nr_periods = int(value)
                elif key == "nr_throttled":
                    nr_throttled = int(value)
                elif key == "throttled_usec":
                    throttled_usec = int(value)
                elif key == "nr_bursts":
                    nr_bursts = int(value)
                elif key == "burst_usec":
                    burst_usec = int(value)

            return CPUStat(usage_usec=usage_usec, user_usec=user_usec,
                           system_usec=system_usec, nr_periods=nr_periods,
                           nr_throttled=nr_throttled, throttled_usec=throttled_usec,
                           nr_bursts=nr_bursts, burst_usec=burst_usec)

        except OSError as e:
            self.logger.error(f"Error getting CPU stat: {e}")
            raise CMDError(f"Error getting CPU stat: {e.with_traceback(e.__traceback__)}")
        except subprocess.SubprocessError as e:
            self.logger.error(f"Error running subprocess: {e}")
            raise CMDError(f"Error running subprocess: {e.with_traceback(e.__traceback__)}")

    def _get_pids_peak(self, identifier: str) -> int:
        """
        Get the peak number of processes spawned by the cgroup.

        Args:
            identifier: Identifier for the cgroup

        Returns:
            int: Peak number of processes

        Raises:
            CMDError: If there is an error in getting the peak number of processes
        """
        pids_peak_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash", "-c",
            f"cat /sys/fs/cgroup/{identifier}/pids.peak"
        ]

        self.logger.debug(CodeExecutor.format_cmd(pids_peak_cmd, debug=True))

        if self.dry_run:
            self.console.print(
                Syntax(CodeExecutor.format_cmd(pids_peak_cmd), "bash",
                       theme="monokai"))
            return

        try:
            pids_peak = subprocess.Popen(pids_peak_cmd,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         text=True)
            stdout, stderr = pids_peak.communicate()
            exit_code = pids_peak.returncode
            self.logger.debug(f"Pids peak: {stdout}")
            self.logger.debug(f"Pids peak stderr: {stderr}")
            self.logger.debug(f"Pids peak exit code: {exit_code}")

            if exit_code != 0:
                raise PIDSPeakReadError(f"Error getting pids peak: {stderr}")

            return int(stdout)

        except OSError as e:
            self.logger.error(f"Error getting pids peak: {e}")
            raise CMDError(f"Error getting pids peak: {e.with_traceback(e.__traceback__)}")

        except subprocess.SubprocessError as e:
            self.logger.error(f"Error running subprocess: {e}")
            raise CMDError(f"Error running subprocess: {e.with_traceback(e.__traceback__)}")

    def _get_stats(self, identifier: str) -> Stats:
        """
        Get the stats for the cgroup (memory peak, memory events, cpu stat).

        Args:
            identifier: Identifier for the cgroup

        Returns:
            Stats: Stats as a dictionary
        """

        memory_peak = self._get_memory_peak(identifier)
        memory_events = self._get_memory_events(identifier)
        cpu_stat = self._get_cpu_stat(identifier)
        pids_peak = self._get_pids_peak(identifier)

        return Stats(memory_peak=memory_peak, memory_events=memory_events,
                     cpu_stat=cpu_stat, pids_peak=pids_peak)

    def _cleanup_actual_output(self, actual_output_file: str) -> None:
        """
        Clean up the actual output file.

        Args:
            actual_output_file: Path to the actual output file

        Returns:
            None
        """
        self.logger.info(f"Cleaning up actual output file: {actual_output_file}")
        try:
            os.remove(actual_output_file)
            self.logger.info(f"Actual output file cleaned up successfully")
        except OSError as e:
            self.logger.error(f"Error cleaning up actual output file: {e}")
            raise ActualOutputCleanupError(
                f"Error cleaning up actual output file: {e.with_traceback(e.__traceback__)}")

    def _run(self,
             index: int,
             input_file_on_host: str | None,
             expected_output_file_on_host: str | None,
             input_file_on_container: str | None,
             expected_output_file_on_container: str | None,
             actual_output_file: str | None,
             timeout: int | None,
             checker: str | None = None,
             max_output_size: int = 1024 * 1024,  # 1 MB
             read_chunk_size: int = 1024,  # 1 KB
             ) -> TestResult:
        """
        Run a single test case with the provided run command (from `get_run_command`).
        This will be called for each test case.
        TODO: Add Args
        """
        cgroup_identifier = f"{self.id}_test{index}"
        try:
            self._create_cgroup(cgroup_identifier)
        except CgroupCreateError as e:
            raise e

        try:
            self._set_limits(cgroup_identifier)
        except CgroupSetLimitsError as e:
            raise e

        self.logger.info(f"[Test {index}] Running")
        run_command = self.get_run_command(self._resolve_path("container"))

        if not timeout:
            timeout = self.constraints.get("time_limit", 1) * 5

        cmd = f"timeout {timeout} {run_command} < {input_file_on_container}"

        docker_cmd = [
            "docker", "exec",
            "--workdir", self.working_dir_in_container,
            self.container_name, "bash", "-c",
            f"echo $$ > /sys/fs/cgroup/{cgroup_identifier}/cgroup.procs && su - {self.user} -c '{cmd}'"
        ]

        self.logger.debug(CodeExecutor.format_cmd(docker_cmd, debug=True))

        if self.dry_run:
            self.console.print(Syntax(CodeExecutor.format_cmd(docker_cmd),
                                      "bash",
                                      theme="monokai"))
            return TestResult(
                verdict=Verdict.AC.name
            )

        try:
            total_output_size = 0
            ole = False
            with open(actual_output_file, "w") as f:
                proc = subprocess.Popen(docker_cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)

                for chunk in iter(lambda: proc.stdout.read(read_chunk_size), ''):
                    total_output_size += len(chunk)
                    if total_output_size > max_output_size:
                        proc.kill()
                        ole = True
                    f.write(chunk)
                proc.wait()

                stderr = proc.stderr.read()
                exit_code = proc.returncode
                stats = self._get_stats(cgroup_identifier)

                self.logger.debug(f"Error: {stderr}")
                self.logger.debug(f"Exit code: {exit_code}")
                self.logger.debug(f"Stats for test {index}: {stats}")

            if ole:
                return TestResult(
                    test_case=index,
                    exit_code=exit_code,
                    stats=stats,
                    verdict=Verdict.OLE.name,
                    verdict_label=Verdict.OLE.label,
                    verdict_details=Verdict.OLE.details,
                    input="",
                    actual_output="",
                    expected_output=""
                )

            result = self._evaluate(index,
                                    input_file_on_host,
                                    expected_output_file_on_host,
                                    actual_output_file,
                                    stderr,
                                    exit_code,
                                    stats,
                                    checker_executable_path=checker)
            return result

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running command: {e.stderr}")
            raise CMDError(f"Error running command: {e.with_traceback(e.__traceback__)}")
        finally:
            try:
                self._cleanup_cgroup(cgroup_identifier)
                self._cleanup_actual_output(actual_output_file)
            except (CgroupCleanupError, ActualOutputCleanupError) as e:
                self.logger.error(f"Error cleaning up: {e}")
                raise e

    def _resolve_path(self, where: Literal["host", "container"]) -> str:
        match where:
            case "host":
                return self.src
            case "container":
                if self.volume is None:
                    return self.working_dir_in_container
                if self.src_in_volume:
                    return os.path.join(self.working_dir_in_container, self.src_in_volume)
                return self.working_dir_in_container

    def _initialize_queue(self, shuffle: bool = False, input_prefix: str = "input",
                          output_prefix: str = "output") -> deque[
        tuple[int, str, str, str, str]]:
        """Initialize the queue with the test cases.

        Args:
            shuffle: If True, shuffle the test cases. Default: False

        Returns:
            deque: Queue of test cases as tuples of (test_idx, input_file, expected_output_file)
        """
        try:
            self.logger.info("Initializing queue")
            k = len(os.listdir(f"{self._resolve_path('host')}/input"))
            self.logger.info(f"Total test cases: {k}")

            build_input_file_on_host = lambda \
                    i: f"{self._resolve_path('host')}/input/{input_prefix}{i}.txt"
            build_input_file_on_container = lambda \
                    i: f"{self._resolve_path('container')}/input/{input_prefix}{i}.txt"
            build_output_file_on_host = lambda \
                    i: f"{self._resolve_path('host')}/output/{output_prefix}{i}.txt"
            build_output_file_on_container = lambda \
                    i: f"{self._resolve_path('container')}/output/{output_prefix}{i}.txt"

            tests = [(i,
                      build_input_file_on_host(i),
                      build_output_file_on_host(i),
                      build_input_file_on_container(i),
                      build_output_file_on_container(i))
                     for i in range(1, k + 1)]

            if shuffle:
                random.shuffle(tests)

            self.logger.debug(f"Tests: {tests}")

            return deque(tests)
        except Exception as e:
            self.logger.error(f"Error initializing test cases: {e}")
            raise TestQueueInitializationError(
                f"Error initializing test cases: {e.with_traceback(e.__traceback__)}")

    def _evaluate(self,
                  index: int,
                  input_file: str,
                  expected_output_file: str,
                  actual_output_file: str,
                  stderr: str,
                  exit_code: int,
                  stats: Stats,
                  checker_executable_path: str | None) -> TestResult:
        """
        Evaluate the output of the code with the expected output.

        Args:
            TODO: Add Args

        Returns:
            TestResult: Test result object

        """
        self.logger.info(f"[Test {index}] Evaluating")

        with open(input_file, "r") as f:
            stdin = f.read()

        with open(expected_output_file, "r") as f:
            expected_output = f.read()

        with open(actual_output_file, "r") as f:
            actual_output = f.read()

        def _build_test_result(verdict: Verdict) -> TestResult:
            return TestResult(
                test_case=index,
                exit_code=exit_code,
                stats=stats,
                verdict=verdict.name,
                verdict_label=verdict.label,
                verdict_details=verdict.details,
                input=stdin,
                actual_output=actual_output,
                expected_output=expected_output,
            )

        match exit_code:
            case 0:
                # Exit code 0 means the code ran successfully
                # Check if the code ran within the time limit
                if stats["cpu_stat"]["usage_usec"] > self.constraints[
                    "time_limit"] * 1_000_000:
                    return _build_test_result(Verdict.TLE)

                if checker_executable_path:
                    # Use the checker executable to compare the output
                    cmd = [
                        os.path.join(self._resolve_path("host"), checker_executable_path),
                        input_file,
                        actual_output_file,
                        expected_output_file
                    ]
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True)
                        if proc.returncode == 0:
                            return _build_test_result(Verdict.AC)
                        else:
                            return _build_test_result(Verdict.WA)
                    except subprocess.CalledProcessError:
                        return _build_test_result(Verdict.RE)
                else:
                    # Compare the output directly
                    if actual_output.strip() == expected_output.strip():
                        return _build_test_result(Verdict.AC)
                    else:
                        return _build_test_result(Verdict.WA)
            case 2:
                # Often caused by Misuse of shell builtins
                return _build_test_result(Verdict.RE)
            case 3:
                # Often caused by Internal error (memory corruption, etc.)
                return _build_test_result(Verdict.RE)
            case 124:
                # This is often caused by timeout
                # This indicates Idleness Limit Exceeded (ILE)
                return _build_test_result(Verdict.ILE)
            case 137:
                # Often caused by Out of Memory (OOM)
                # Consider checking memory events
                if stats["memory_events"]["oom"] > 0:
                    return _build_test_result(Verdict.MLE)
                else:
                    return _build_test_result(Verdict.RE)
            case 139:
                # Often caused by Segmentation Fault (SIGSEGV)
                # or Memory Error
                return _build_test_result(Verdict.RE)
            case _:
                # Fall back to RE
                return _build_test_result(Verdict.RE)

    def run(self,
            input_prefix: str = "input",
            output_prefix: str = "output",
            shuffle: bool = False,
            early_exit: bool = True,
            checker: str | None = None,
            timeout: int | None = None) -> Iterator[TestResult]:
        """
        Run all the test cases. This will yield the results for each test case.
        Order of the test cases can be shuffled by setting `shuffle` to True.
        Default behavior is to run the test cases in order.

        Args:
            input_prefix: Prefix for the input files (default: input)
            output_prefix: Prefix for the output files (default: output)
            shuffle: If True, shuffle the test cases. Default: False
            early_exit: If True, tests will stop as soon as one of the tests fails.
                        Default: False
            checker: Path to the checker executable (if any)
            timeout: Optional timeout for running command for each test case.
                        This timeout is not essentially the time limit for the code
                        execution. It is the time limit for running command
                        (e.g., `timeout 5 <command from get_run_command>`)
                        for each test case and thus acts as a fallback mechanism.
                        Hence, it should be set to a value higher than the time limit
                        for the code execution otherwise the test cases will fail
                        prematurely.

        Returns:
            Iterator: Iterator of tuples containing stdout, stderr, exit_code
        """
        tests = self._initialize_queue(input_prefix=input_prefix,
                                       output_prefix=output_prefix,
                                       shuffle=shuffle)
        self.logger.info(f"Running {len(tests)} tests")
        # Create a directory `actual` on host to store the actual output
        try:
            actual_output_dir = f"{self.src}/actual"
            os.makedirs(actual_output_dir, exist_ok=True)
            ac_count = 0
            k = len(tests)
            while tests:
                idx, input_file_on_host, expected_output_file_on_host, \
                    input_file_on_container, expected_output_file_on_container = tests.popleft()
                actual_output_path = f"{actual_output_dir}/output{idx}.txt"
                result = \
                    self._run(index=idx,
                              input_file_on_host=input_file_on_host,
                              expected_output_file_on_host=expected_output_file_on_host,
                              input_file_on_container=input_file_on_container,
                              expected_output_file_on_container=expected_output_file_on_container,
                              actual_output_file=actual_output_path,
                              timeout=timeout,
                              checker=checker)
                yield result
                self.logger.info(f"[Test {idx}] verdict: {result['verdict']}")
                if result["verdict"] != Verdict.AC.name and early_exit:
                    raise EarlyExitError(f"Test {idx} failed")

            if ac_count == k:
                self.logger.info("All test cases passed")
        except EarlyExitError as e:
            self.logger.error(f"Early exit: {e}")
            raise e
        except Exception as e:
            self.logger.error(f"Error running tests: {e}")
            raise RuntimeError(f"Error running tests: {e.with_traceback(e.__traceback__)}")
        finally:
            # Remove the actual output directory
            try:
                shutil.rmtree(actual_output_dir)
            except OSError as e:
                self.logger.error(f"Error cleaning up actual output directory: {e}")
                raise ActualOutputCleanupError(
                    f"Error cleaning up actual output directory: {e.with_traceback(e.__traceback__)}")
