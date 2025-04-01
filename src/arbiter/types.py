from typing import TypedDict

from arbiter.verdicts import Verdict


class Constraints(TypedDict):
    time_limit: int  # in seconds
    memory_limit: int  # in MB
    memory_swap_limit: int  # in MB
    cpu_quota: int  # cgroup v2 compatible
    cpu_period: int  # cgroup v2 compatible


class MemoryEvents(TypedDict):
    low: int
    high: int
    max: int
    oom: int
    oom_kill: int
    oom_group_kill: int


class CPUStat(TypedDict):
    usage_usec: int
    user_usec: int
    system_usec: int
    nr_periods: int
    nr_throttled: int
    throttled_usec: int
    nr_bursts: int
    burst_usec: int


class Stats(TypedDict):
    memory_peak: int
    memory_events: MemoryEvents
    cpu_stat: CPUStat
    pids_peak: int

class TestResult(TypedDict):
    test_case: int
    exit_code: int
    stats: Stats
    verdict: Verdict
    verdict_label: str
    verdict_details: str
    input: str
    actual_output: str
    expected_output: str

