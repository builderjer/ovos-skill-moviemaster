import json
import os

BASE_FOLDER = os.getenv("BASE_FOLDER")
if not BASE_FOLDER:
    raise ValueError("environment variable `LOCALE_FOLDER` not set")
elif not os.path.exists(BASE_FOLDER):
    raise ValueError(f"environment variable `LOCALE_FOLDER` is not a folder: {BASE_FOLDER}")
VERSION_FILE = os.getenv("VERSION_FILE")
if not os.path.isfile(VERSION_FILE):
    raise ValueError(f"environment variable `VERSION_FILE` is not a file: {VERSION_FILE}")

def get_version():
    """ Find the version of the package"""
    major, minor, build, alpha = (None, None, None, None)
    with open(VERSION_FILE) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version

desktop_dir = os.path.join(BASE_FOLDER, "res", "desktop")
jsonf = os.path.join(desktop_dir, "skill.json")

with open(jsonf) as f:
    data = json.load(f)

data["branch"] = "v" + get_version()

with open(jsonf, "w") as f:
    json.dump(data, f, indent=4)
