from os import getenv
import re

from github import Github
import semver

"""
Get the start of the release cycle for the current release type. (patch, minor, major)
(the release cycle starts with the end version of the last cylce)
If `LAST_RELEASE` is set, the last release will be returned.
If `FIRST_RELEASE` is set, the first release will be returned.
"""

GITHUB_REPOSITORY = getenv("GITHUB_REPOSITORY")
RELEASE_TYPE = getenv("RELEASE_TYPE")
FIRST_RELEASE = bool(getenv("FIRST_RELEASE"))
LAST_RELEASE = bool(getenv("LAST_RELEASE"))

if any(req is None for req in [GITHUB_REPOSITORY, RELEASE_TYPE]):
    raise ValueError("Missing required environment variable(s)")

repo = Github(getenv("GITHUB_TOKEN")).get_repo(GITHUB_REPOSITORY)
latest_version = None
start_cycle_id = 0

def get_semver(tag: str) -> semver.Version:
    # hack for v prefix
    tag = tag.lstrip("v").lstrip("V")

    # hack for alpha releases
    if re.match(r"[0-9]+\.[0-9]+\.[0-9]+a[0-9]+", tag):
        tag = re.sub(r"([0-9]+)(a[0-9]+)", r"\1-\2", tag)

    if not semver.Version.is_valid(tag):
        return None
    return semver.Version.parse(tag)


def in_cycle(v: semver.Version) -> bool:
    if RELEASE_TYPE == "patch":
        return v.patch == latest_version.patch and not \
                (v.minor < latest_version.minor) and not \
                (v.major < latest_version.major)
    elif RELEASE_TYPE == "minor":
        return v.minor == latest_version.minor and not \
                (v.major < latest_version.major)
    elif RELEASE_TYPE == "major":
        return v.major == latest_version.major


releases = repo.get_releases()
if not releases:
    raise Exception("No releases found")

for id, release in enumerate(releases):
    version = get_semver(release.tag_name)
    if id == 0:
        latest_version = version
        if LAST_RELEASE:
            break
        continue

    if not version:
        continue
    elif in_cycle(version):
        start_cycle_id = id

if latest_version is None:
    exit(0)
elif start_cycle_id < releases.totalCount - 1 and not \
        (FIRST_RELEASE or LAST_RELEASE):
    start_cycle_id += 1

print(releases[start_cycle_id].tag_name)
