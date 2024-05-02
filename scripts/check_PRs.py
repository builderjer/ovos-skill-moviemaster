import os
from os.path import join, dirname, isfile
import json
import re
from typing import List, Optional

from github import Github
from github.Repository import Repository
import pccc


CONFIG_FILE = os.environ.get("PCCC_CONFIG_FILE")
if CONFIG_FILE and not isfile(CONFIG_FILE):
    print(f"Config file {CONFIG_FILE} not found.")
    exit(1)

TOKEN = os.getenv('GH_PAT') or os.getenv('GITHUB_TOKEN')
REPOSITORY = os.getenv('GITHUB_REPOSITORY')
PR_LABELS: dict = json.loads(os.getenv('PR_LABELS', '{}'))
SINGLE_PR = os.getenv('PR_NUMBER')
ERROR_ON_FAILURE = os.getenv('ERROR_ON_FAILURE', 'false').lower() == 'true'
if not PR_LABELS:
    PR_LABELS = json.loads(open(join(dirname(dirname(__file__)), "pr_labels.json")).read())

test_phase_cache = os.getenv('TEST_PHASE_CACHE', '')
print(f"TEST_PHASE_CACHE: {test_phase_cache}")
if not isfile(test_phase_cache):
    ongoing_test = False
    if test_phase_cache:
        print("The file specified in TEST_PHASE_FILE does not exist.")
else:
    with open(test_phase_cache, 'r') as f:
        content = f.read().strip("\n").strip()
        print(f"file content: {content}, eq: {content == 'testing'}")
        ongoing_test = content == "testing"


def get_scope(title):
    match = re.match(r"^[a-z]+\s*\((.+)\):", title)
    if match:
        return match.group(1)
    return None


def strip_scope(title):
    return re.sub(r"^([a-z]+)\s*\(([^)]+)\):", r"\1:", title)


def cc_type(desc: str) -> str:
    ccr = parse_cc(strip_scope(desc))
    if ccr:
        return ccr.header.get("type")

    return "unknown"


def cc_breaking(desc: str) -> bool:
    ccr = parse_cc(strip_scope(desc))
    if ccr:
        return ccr.breaking.get("flag") or ccr.breaking.get("token")

    return False


def cc_scope(desc: str) -> str:
    ccr = parse_cc(desc)
    if ccr:
        return ccr.header.get("scope")

    return get_scope(desc) or "unknown"


def parse_cc(desc: str) -> Optional[pccc.ConventionalCommitRunner]:
    ccr = pccc.ConventionalCommitRunner()
    ccr.options.load((f"-o{CONFIG_FILE}",) if CONFIG_FILE else None)
    ccr.raw = desc
    ccr.clean()
    try:
        ccr.parse()
        return ccr
    # no spec compliant format
    except Exception:
        return None


def check_cc_labels(desc: str) -> List[str]:

    labels = set()
    _type = cc_type(desc)
    _scope = cc_scope(desc)
    test_relevant_cc = ["feat", "fix", "refactor"]
    if _type == "unknown":
        return [PR_LABELS.get("need_cc", "CC missing")]
    if cc_breaking(desc):
        labels.add(PR_LABELS.get("breaking", "breaking change"))
    if _type == "release":
        labels.add("fix")
    elif _type in PR_LABELS:
        labels.add(PR_LABELS.get(_type))
    if _scope in PR_LABELS:
        labels.add(PR_LABELS.get(_scope))
    elif _scope != "unknown":
        labels.add(_scope)
    if ongoing_test and (any(t in test_relevant_cc for t in [_type, _scope]) or cc_breaking(desc)):
        labels.add("ongoing test")
        
    return list(labels)


def ensure_label_exists(repo: Repository, labels: List[str], color: str = 'ffffff'):
    for label_name in labels:
        if not any(label.name == label_name for label in repo.get_labels()):
            repo.create_label(label_name, color)

    # switch the strings to label objects
    for label in repo.get_labels():
        if label.name in labels:
            labels[labels.index(label.name)] = label


git = Github(TOKEN).get_repo(REPOSITORY)
open_pulls = git.get_pulls(state='open')
cc_missing = False


for pr in open_pulls:
    if SINGLE_PR and pr.number != int(SINGLE_PR):
        continue
    pr_description = f"{pr.title}\n{pr.body}"
    labels = check_cc_labels(pr_description)
    ensure_label_exists(git, labels)
    pr.set_labels(*labels)

    # clear the test flag if the PR adresses a release or doesn't get a release at all.
    if SINGLE_PR:
        if cc_type(pr_description) in ["release", "ci", "style", "test", "docs"] or \
                cc_scope(pr_description) == "release":
            ongoing_test = False
        if cc_type(pr_description) == "unknown":
            cc_missing = True

# nuke status check (if requested)
if (cc_missing or ongoing_test) and ERROR_ON_FAILURE:
    raise Exception(f"CC missing: {cc_missing}, ongoing test phase: {ongoing_test}")
