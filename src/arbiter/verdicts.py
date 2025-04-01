from enum import Enum


class Verdict(Enum):
    AC = (
        "Accepted",
        "The program ran successfully and produced the correct output.",
    )
    WA = ("Wrong Answer", "The program ran successfully but produced incorrect output.")
    TLE = (
        "Time Limit Exceeded",
        "The program took longer than the allowed execution time.",
    )
    MLE = (
        "Memory Limit Exceeded",
        "The program used more memory than the allowed limit.",
    )
    RE = (
        "Runtime Error",
        "The program terminated abnormally with a non-zero exit code.",
    )
    OLE = (
        "Output Limit Exceeded",
        "The program produced more output than the allowed limit.",
    )
    CE = ("Compilation Error", "The program failed to compile successfully.")
    ILE = ("Idleness Limit Exceeded", "The program did not produce any output for too \
            long, often indicating an infinite loop that does not consume CPU time.")
    JE = ("Judgement Error", "The judgement process failed to produce a verdict.")

    def __init__(self, label, details):
        self.label = label
        self.details = details

    def __str__(self):
        return self.name

    def get_details(self):
        return self.details

if __name__ == "__main__":
    d = {
        "verdict": Verdict.AC,
    }
    print(d)
