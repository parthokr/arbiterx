class CMDError(Exception):
    """
    Exception raised when there is an error in running a command.
    """
    pass


class DockerDaemonError(Exception):
    """
    Exception raised when docker daemon is not running.
    """
    pass


class ContainerCreateError(Exception):
    """
    Exception raised when there is an error in creating the container.
    """
    pass


class ContainerCleanupError(Exception):
    """
    Exception raised when there is an error in cleaning up the container.
    """
    pass


class CgroupMountError(Exception):
    """
    Exception raised when cgroup is not mounted.
    """
    pass


class CgroupCreateError(Exception):
    """
    Exception raised when there is an error in creating the cgroup.
    """
    pass


class CgroupCleanupError(Exception):
    """
    Exception raised when there is an error in cleaning up the cgroup.
    """
    pass


class CgroupControllerReadError(Exception):
    """
    Exception raised when there is an error in reading the `cgroup.controllers` file.
    """
    pass


class CgroupControllerError(Exception):
    """
    Exception raised when required controllers are not allowed in the cgroup.
    For example if `cpu` and `memory` controllers are not present in the
    `cgroup.controllers` file.
    """
    pass


class CgroupSubtreeControlError(Exception):
    """
    Exception raised when required controllers are not set in the
    `cgroup.subtree_control` file.
    """
    pass


class CgroupSubtreeControlReadError(Exception):
    """
    Exception raised when there is an error in reading the `cgroup.subtree_control` file.
    """
    pass


class CgroupSubtreeControlWriteError(Exception):
    """
    Exception raised when there is an error in writing the `cgroup.subtree_control` file.
    """
    pass


class CgroupSetLimitsError(Exception):
    """
    Exception raised when there is an error in setting the limits for the cgroup.
    Specifically, when there is an error in writing the `memory.max`, `memory.swap.max` etc.
    """
    pass


class CompileError(Exception):
    """
    Exception raised when there is an error in compiling the code.
    """
    pass


class RunError(Exception):
    """
    Exception raised when there is an error in running the code.
    """
    pass

class TestQueueInitializationError(Exception):
    """
    Exception raised when there is an error in initializing the test queue.
    """
    pass

class MemoryPeakReadError(Exception):
    """
    Exception raised when there is an error in reading the `memory.peak` file.
    """
    pass

class MemoryEventsReadError(Exception):
    """
    Exception raised when there is an error in reading the `memory.events` file.
    """
    pass

class CPUStatReadError(Exception):
    """
    Exception raised when there is an error in reading the `cpustat` file.
    """
    pass

class PIDSPeakReadError(Exception):
    """
    Exception raised when there is an error in reading the `pid` file.
    """
    pass

class EarlyExitError(Exception):
    """
    Exception raised when there is an error in executing an Early Exit command.
    """
    pass

class ActualOutputCleanupError(Exception):
    """
    Exception raised when there is an error in cleaning up the actual output.
    """
    pass