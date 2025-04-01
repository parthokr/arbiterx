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
