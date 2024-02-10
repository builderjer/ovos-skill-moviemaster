import fileinput
import os


version_file = os.getenv("VERSION_FILE")
if not os.path.isfile(version_file):
    raise ValueError(f"environment variable `VERSION_FILE` is not a file: {version_file}")

alpha_var_name = "VERSION_ALPHA"

for line in fileinput.input(version_file, inplace=True):
    if line.startswith(alpha_var_name):
        print(f"{alpha_var_name} = 0")
    else:
        print(line.rstrip('\n'))
