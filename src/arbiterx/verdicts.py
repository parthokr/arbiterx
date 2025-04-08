from enum import Enum


class Verdict(Enum):
    """
     The Verdict enum defines a set of possible outcomes for a program's execution during a coding competition or automated testing.
     Each outcome is represented by an enum member (e.g., AC, WA).
     Each enum member is associated with a tuple containing a human-readable label and a detailed description of the verdict.

    """
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

    """
     The __init__ method of the enum is automatically called when each enum member is created.
     It assigns the label and details to the corresponding instance variables.
    """

    def __init__(self, label, details):
        self.label = label
        self.details = details


"""
 The __str__ method defines how the enum member should be represented as a string.
"""

    def __str__(self):
        return self.name

"""
The get_details method provides a way to retrieve the detailed description of the verdict.
"""
    def get_details(self):
        return self.details
"""
 It demonstrates how to create a dictionary with a Verdict enum member and how to access its label and details.
"""
if __name__ == "__main__":
    d = {
        "verdict": Verdict.AC,
    }
    print(d)