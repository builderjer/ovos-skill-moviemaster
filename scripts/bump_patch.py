import fileinput
import os


version_file = os.getenv("VERSION_FILE")
if not os.path.isfile(version_file):
    raise ValueError(f"environment variable `VERSION_FILE` is not a file: {version_file}")

version_var_name = "VERSION_BUILD"
alpha_var_name = "VERSION_ALPHA"

with open(version_file, "r", encoding="utf-8") as v:
    for line in v.readlines():
        if line.startswith(version_var_name):
            version = int(line.split("=")[-1])
            new_version = int(version) + 1

for line in fileinput.input(version_file, inplace=True):
    if line.startswith(version_var_name):
        print(f"{version_var_name} = {new_version}")
    elif line.startswith(alpha_var_name):
        print(f"{alpha_var_name} = 0")
    else:
        print(line.rstrip('\n'))
