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
    pass

class TestQueueInitializationError(Exception):
    pass

class MemoryPeakReadError(Exception):
    pass

class MemoryEventsReadError(Exception):
    pass

class CPUStatReadError(Exception):
    pass

class PIDSPeakReadError(Exception):
    pass

class EarlyExitError(Exception):
    pass

class ActualOutputCleanupError(Exception):
    pass
