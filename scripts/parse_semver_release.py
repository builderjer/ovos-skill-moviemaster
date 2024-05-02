import re
from os import environ, devnull
from os.path import isfile
import sys

import pccc
import semver

"""
translates a conventional commit title/message into a semver version
"""


CONFIG_FILE = environ.get("PCCC_CONFIG_FILE")
if CONFIG_FILE and not isfile(CONFIG_FILE):
    print(f"Config file {CONFIG_FILE} not found.")
    exit(1)


def get_scope(title):
    match = re.match(r"^[a-z]+\s*\((.+)\):", title)
    if match:
        return match.group(1)
    return None


def strip_scope(title):
    if get_scope(title) != "release":
        return re.sub(r"^([a-z]+)\s*\(([^)]+)\):", r"\1:", title)
    return title


def get_version():
    # note: this is a PEP 440 compliant version, so alpha versions come in "1.0.0a1"
    version = environ.get("VERSION", "") or \
            environ.get("RELEASE_VERSION", "") or \
            environ.get("PREVIOUS_VERSION", "")
    match = re.match(r"(\d+\.\d+\.\d+)([aA-zZ].*)", version)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    else:
        return version


def semver_from_cc():
    ccr = pccc.ConventionalCommitRunner()
    if CONFIG_FILE is None:
        # Redirect stdout to null
        original_stdout = sys.stdout
        sys.stdout = open(devnull, 'w')

    ccr.options.load((f"-o{CONFIG_FILE}",) if CONFIG_FILE else None)

    if CONFIG_FILE is None:
        # Restore original stdout
        sys.stdout = original_stdout

    ccr.raw = f"{TITLE}\n{BODY}"
    ccr.clean()
    try:
        ccr.parse()
    # no spec compliant format
    except Exception:
        print("No semver release.")
        exit(0)

    if ccr.breaking.get("flag") or ccr.breaking.get("token"):
        return "major"
    # commits that gets added to a release (special case)
    elif ccr.header.get("type") == "release" or \
            ccr.header.get("scope") == "release":
        return "release"
    elif ccr.header.get("type") == "feat":
        return "minor"
    elif ccr.header.get("type") in ["fix", "refactor"]:
        return "patch"
    elif ccr.header.get("type") not in ["ci", "docs", "style", "test"]:
        return "alpha"
    else:
        print("No semver release.")
        exit(0)

def semver_from_version():
    try:
        version = semver.VersionInfo.parse(VERSION)
    except ValueError:
        print("No semver release.")
        exit(0)
    
    if version.prerelease:
        return "alpha"
    elif version.patch != 0:
        return "patch"
    elif version.minor != 0:
        return "minor"
    elif version.major != 0:
        return "major"

TITLE = strip_scope(environ.get("TITLE", ""))
BODY = environ.get("BODY")
VERSION = get_version()

if VERSION:
    release = semver_from_version()
elif TITLE:
    release = semver_from_cc()
else:
    print("No semver release.")
    exit(0)

print(release)