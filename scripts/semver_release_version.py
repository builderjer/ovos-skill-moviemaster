from os import getenv
from os.path import isfile
import re
from typing import SupportsInt, Optional, Union, List

from github import Github
from github.GitRelease import GitRelease
import semver
import argparse

"""
This script is supposed to parse a github release history and get latest (or first / last / next) 
release versions for the specified release type. (patch, minor, major, prerelease)
If no release type is specified, get the latest/.. release version.

You can make this relative to a specific version by providing a version or file to read the version from.
eg. `... --version 0.2.1 --latest --type alpha` will get the latest alpha release below version 0.2.1 
or  `... --file path/to/version.py --next` will get the next release version from the version file.

Options
    cycle                      # restrict the release type to the current cycle
                               # (i.e. if the current version is 2.1.2 and `--type patch`, it will only consider 2.1.x releases)

Args
    --type: str                # the release type to get the version for
    --file: str                # the file to read the version from
    --version: str             # the version to get the release for

    --save: str                # writes an ovos version file to the specified path (if the version is above the latest)
                                 if no path is provided and read from a file, the file will be overwritten
    --fsave: str               # force the ovos version file to be written even if the version is below the latest

    --alpha_marker: str        # marker for alpha releases, default is 'a'

Flags
    --last                     # get the last release of that release type in the current cycle
    --next                     # get the next release of the upcoming release type
    --first                    # get the first release of that release type in the current cycle
    --latest                   # get the latest version released
"""


def add_common_arguments(parser):
    parser.add_argument("--alpha_marker", default="a")
    parser.add_argument("--type", choices=["patch", "minor", "major", "alpha", "prerelease"])
    parser.add_argument("--save", nargs='?', const=True, default=False)
    parser.add_argument("--fsave", nargs='?', const=True, default=False)

    release_group = parser.add_mutually_exclusive_group()
    release_group.add_argument("--last", action='store_true')
    release_group.add_argument("--next", action='store_true')
    release_group.add_argument("--latest", action='store_true')
    release_group.add_argument("--first", action='store_true')

    input_group = parser.add_mutually_exclusive_group()
    #input_group.add_argument("--repo")
    input_group.add_argument("--file")
    input_group.add_argument("--version")


parser = argparse.ArgumentParser()
add_common_arguments(parser)

subparsers = parser.add_subparsers(dest="command")
cycle_parser = subparsers.add_parser("cycle")
add_common_arguments(cycle_parser)

args = parser.parse_args()

RELEASE_TYPE = args.type
ALPHA_MARKER = args.alpha_marker
REPOSITORY = getenv("GITHUB_REPOSITORY")
RESTRICT_TO_CYCLE = args.command == "cycle"

if REPOSITORY is None and not (args.file or args.version):
    parser.error("either set up an environmental variable `GITHUB_REPOSITORY` or pass --version or --file as arguments")

if RELEASE_TYPE == "alpha":
    RELEASE_TYPE = "prerelease"

    
class OVOSReleases(semver.Version):
    __history = []
    __github_token = None
    __repo = None
    __release = None
    __prefix = ""

    def __init__(self, major: SupportsInt = 0,
                       minor: SupportsInt = 0,
                       patch: SupportsInt = 0,
                       prerelease: Optional[Union[str, int]] = None,
                       build: Optional[Union[str, int]] = None,
                       release: Optional[GitRelease] = None):
        self.__release = release
        if isinstance(release, GitRelease):
            self.__prefix = re.match(r"^([a-zA-Z-\/\\]+)?", release.tag_name).group(1) or ""
            ver = self.parse(release.tag_name)
            major = ver.major
            minor = ver.minor
            patch = ver.patch
            prerelease = ver.prerelease
            build = ver.build

        super().__init__(major, minor, patch, prerelease, build)

    def __str__(self) -> str:
        return f"{self.__prefix}{super().__str__()}"
    
    def next(self, rtype: Optional[str], alpha_marker: str = ALPHA_MARKER)\
        -> "OVOSReleases":
        rtype = rtype or "prerelease"
        next_v = self.next_version(rtype, alpha_marker)
        return OVOSReleases(next_v.major, next_v.minor, next_v.patch, next_v.prerelease, next_v.build)
    
    def latest(self, rtype: Optional[str] = None) -> "OVOSReleases":
        if rtype and not self.history:
            raise ValueError("No release history")
        
        release_versions = self.filter_versions(rtype, RESTRICT_TO_CYCLE)

        latest_version = OVOSReleases(0, 0, 0)
        if rtype is None and (not self.history or not release_versions):
            latest_version = self
        elif release_versions:
            latest_version = max(release_versions)
        
        return latest_version
    
    def last(self, rtype: Optional[str] = None) -> "OVOSReleases":
        if not self.history:
            raise ValueError("No release history")
        
        release_versions = self.filter_versions(rtype, RESTRICT_TO_CYCLE)

        last_version = OVOSReleases(0, 0, 0)
        if release_versions:
            last_version = release_versions[min(1, len(release_versions) - 1)]
        
        return last_version

    def first(self, rtype: Optional[str] = None) -> "OVOSReleases":
        if not self.history:
            raise ValueError("No release history")
        
        release_versions = self.filter_versions(rtype, RESTRICT_TO_CYCLE)
        
        first_version = OVOSReleases(0, 0, 0)
        if release_versions:
            first_version = min(release_versions)
        
        return first_version
    
    @property
    def history(self) -> List["OVOSReleases"]:
        """
        Returns the release history of the github repository
        """
        return self.__history
    
    @property
    def released(self) -> bool:
        """
        Returns whether the release is already released
        """
        return self.__release is not None
    
    @property
    def tag(self) -> str:
        """
        Returns the tag of the release
        """
        if not self.released:
            return None
        return self.__release.tag_name
    
    @property
    def etag(self) -> str:
        """
        Returns the etag (MD5 hash of the content) of the release
        """
        if not self.released:
            return None
        return self.__release.etag
    
    @property
    def release_url(self) -> str:
        """
        Returns the url of the release
        """
        if not self.released:
            return None
        return self.__release.url
    
    @property
    def tarball_url(self) -> str:
        """
        Returns the tarball url of the release
        """
        if not self.released:
            return None
        return self.__release.tarball_url
    
    @property
    def title(self) -> str:
        """
        Returns the release title
        """
        if not self.released:
            return None
        return self.__release.title
    
    @property
    def body(self) -> str:
        """
        Returns the release description
        """
        if not self.released:
            return None
        return self.__release.body

    @classmethod
    def from_file(cls, path: str) -> Optional["OVOSReleases"]:
        with open(path, "r") as f:
            data = f.read()
            data = re.search(r"# START_VERSION_BLOCK(.*?)# END_VERSION_BLOCK", data, re.DOTALL)
            if data:
                data = data.group(1)
                data = re.findall(r"VERSION_(\w+) = (\d+)", data)
                data = {k: int(v) for k, v in data}
                if data["ALPHA"]:
                    data["ALPHA"] = f"{ALPHA_MARKER}.{data['ALPHA']}"
                else:
                    data["ALPHA"] = None
                return cls(data["MAJOR"], data["MINOR"], data["BUILD"], data["ALPHA"])
    
    @classmethod
    def from_repo(cls, repo: Optional[str], token: Optional[str] = None) -> "OVOSReleases":
        cls.__github_token = token
        cls.__repo = repo

        releases = []
        if repo:
            git = Github(token).get_repo(repo)
            releases = git.get_releases()
        if not releases:
            return OVOSReleases(0, 0, 0)
        
        cls.__history = [OVOSReleases(release=release) for release in releases
                         if OVOSReleases.parse(release.tag_name) is not None]
        return cls.__history[0]
    
    @classmethod
    def from_list(cls, history: List[str]) -> "OVOSReleases":
        cls.__history = [cls.parse(tag) for tag in history]
        return cls.__history[0]

    def to_file(self, path: str) -> None:
        """
        Saves the version to the specified file using
        the ovos version format specification
        """
        with open(path, "w") as f:
            f.write(f"""# START_VERSION_BLOCK
VERSION_MAJOR = {self.major}
VERSION_MINOR = {self.minor}
VERSION_BUILD = {self.patch}
VERSION_ALPHA = {self.prerelease.replace(ALPHA_MARKER, '').replace('.', '') if self.prerelease else 0}
# END_VERSION_BLOCK
""")
            
    def to_pypi_format(self) -> str:
        return f"{self.__prefix}{self.major}.{self.minor}.{self.patch}{self.prerelease.replace('.', '') if self.prerelease else ''}"
            
    @staticmethod
    def parse(tag: str) -> semver.Version:
        # remove prefix from tag
        tag = re.sub(r"^([a-zA-Z-\/\\]+)?", "", tag)

        # hack for alpha releases
        if re.match(rf"[0-9]+\.[0-9]+\.[0-9]+{ALPHA_MARKER}[0-9]+", tag):
            tag = re.sub(rf"([0-9]+){ALPHA_MARKER}([0-9]+)", rf"\1-{ALPHA_MARKER}.\2", tag)

        if not semver.Version.is_valid(tag):
            return None
        
        ver = semver.Version.parse(tag)
        return OVOSReleases(ver.major, ver.minor, ver.patch, ver.prerelease, ver.build)
    
    def get(self, version: Optional[str], file: Optional[str]) -> "OVOSReleases":
        if version:
            version = OVOSReleases.parse(version)
            for v in self.history:
                if v.compare(version) == 0:
                    return v
            return version
        elif file:
            version = OVOSReleases.from_file(file)
            for v in self.history:
                if v.compare(version) == 0:
                    return v
            return version
    
    def filter_versions(self, release_type: Optional[str] = None, cycle_only: bool = False) -> List[semver.Version]:
        """
        Returns the release versions of the specified release type

        If cycle only restrict versions to the given cycle
        (i.e. if self is 2.1.2, it will return all 2.1.x releases if release_type is patch,
        normally: 2.1.2 (latest), 2.1.1 (last/first), depending on the release history)
        """

        if release_type:
            release_type = release_type.lower()
        filtered_versions = []
        if release_type == 'major':
            filtered_versions = [v for v in self.history 
                                 if v <= self
                                 and v.major != 0 
                                 and v.minor == 0 
                                 and v.patch == 0 
                                 and v.prerelease is None]
            if cycle_only:
                filtered_versions = filter(lambda v: v.major == self.major, filtered_versions)
        elif release_type == 'minor':
            filtered_versions = [v for v in self.history
                                 if v <= self
                                 and v.minor != 0 
                                 and v.patch == 0 
                                 and v.prerelease is None]
            if cycle_only:
                filtered_versions = filter(lambda v: v.major == self.major, filtered_versions)
        elif release_type == 'patch':
            filtered_versions = [v for v in self.history 
                                 if v <= self and v.patch != 0 and v.prerelease is None]
            if cycle_only:
                filtered_versions = filter(lambda v: v.major == self.major and v.minor == self.minor, filtered_versions)
        elif release_type in ["prerelease", "alpha"]:
            filtered_versions = [v for v in self.history
                                 if v <= self and v.prerelease is not None]
            if cycle_only:
                filtered_versions = filter(lambda v: v.major == self.major and v.minor == self.minor and v.patch == self.patch, filtered_versions)
        elif release_type is None:
            filtered_versions = [v for v in self.history if v <= self]
            if cycle_only:
                filtered_versions = filter(lambda v: v.major == self.major, filtered_versions)
        else:
            raise ValueError('Invalid release type')
        
        return sorted(filtered_versions, reverse=True)


# instanciate the class	history
releases = OVOSReleases.from_repo(REPOSITORY, getenv("GH_PAT") or getenv("GITHUB_TOKEN"))
# if version or file is provided, get the version from the repository history or use the provided version
if args.version or args.file:
    base = releases.get(args.version, args.file)
else:
    base = releases.latest()

# output handling
if (args.save is True or args.fsave is True) and not args.file:
    arg = "--save"
    if args.fsave:
        arg = "--fsave"
    raise ValueError(f"No file specified to save the version to (ie {arg} /path/to/version.py)")

if args.first:
    version = base.first(RELEASE_TYPE)
elif args.last:
    version = base.last(RELEASE_TYPE)
elif args.next:
    version = base.next(RELEASE_TYPE)
elif args.latest:
    version = base.latest(RELEASE_TYPE)
else:
    version = base

if (args.save or args.fsave) and version is not None:
    file = args.file or args.save or args.fsave
    if (version > base or args.fsave) or \
            all( arg is False for arg in [args.first, args.last, args.next] ): 
        version.to_file(file)

if version is not None:
    print(version.to_pypi_format())
