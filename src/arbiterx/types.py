from typing import TypedDict

from arbiterx.verdicts import Verdict


class Constraints(TypedDict):
    """
    Information about the limitations imposed on a program's execution:
    Args:
        time_limit: The maximum allowed execution time in seconds.
        memory_limit: The maximum allowed memory usage in megabytes (MB).
        memory_swap_limit: The maximum allowed swap memory usage in MB.
        cpu_quota: A value related to CPU usage limits, compatible with cgroup v2.
        cpu_period: A value related to CPU usage periods, compatible with cgroup v2.

    """
    time_limit: int  # in seconds
    memory_limit: int  # in MB
    memory_swap_limit: int  # in MB
    cpu_quota: int  # cgroup v2 compatible
    cpu_period: int  # cgroup v2 compatible


class MemoryEvents(TypedDict):
    """
     It represents various memory-related events that occurred during program execution:
     Args:
         low: a counter of low memory events.
         high: a counter of high memory events.
         max: a counter of max memory events.
         oom: a counter of out-of-memory events.
         oom_kill: a counter of processes killed due to out-of-memory conditions.
         oom_group_kill: a counter of process groups killed due to out-of-memory conditions.

    """
    low: int
    high: int
    max: int
    oom: int
    oom_kill: int
    oom_group_kill: int


class CPUStat(TypedDict):
    """
    It contains statistics about CPU usage:
    Args:
        usage_usec: Total CPU usage in microseconds.
        user_usec: CPU usage in user mode in microseconds.
        system_usec: CPU usage in system mode in microseconds.
        nr_periods: The number of CPU periods.
        nr_throttled: The number of times CPU usage was throttled.
        throttled_usec: The total time CPU usage was throttled in microseconds.
        nr_bursts: The number of cpu bursts.
        burst_usec: the total time cpu burst in microseconds.

    """
    usage_usec: int
    user_usec: int
    system_usec: int
    nr_periods: int
    nr_throttled: int
    throttled_usec: int
    nr_bursts: int
    burst_usec: int


class Stats(TypedDict):
    """
    It aggregates memory, CPU, and process-related statistics:
    Args:
        memory_peak: The peak memory usage in MB.
        memory_events: A MemoryEvents dictionary containing memory event statistics.
        cpu_stat: A CPUStat dictionary containing CPU usage statistics.
        pids_peak: The peak number of processes (PIDs) used.

    """
    memory_peak: int
    memory_events: MemoryEvents
    cpu_stat: CPUStat
    pids_peak: int

class TestResult(TypedDict):
    """
    It stores the results of a single test case:
    Args:
        test_case: The test case number.
        exit_code: The exit code of the executed program.
        stats: A Stats dictionary containing execution statistics.
        verdict: A Verdict enum indicating the outcome of the test (e.g., "Accepted," "Wrong Answer," "Time Limit Exceeded").
        verdict_label: A string representation of the verdict.
        verdict_details: A string providing additional details about the verdict.
        input: The input provided to the test case.
        actual_output: The actual output produced by the program.
        expected_output: The expected output for the test case.
    """
    test_case: int
    exit_code: int
    stats: Stats
    verdict: Verdict
    verdict_label: str
    verdict_details: str
    input: str
    actual_output: str
    expected_output: str