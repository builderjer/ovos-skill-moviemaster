from os import environ, getcwd, urandom
from os.path import join, isfile
import sys
import subprocess
import json
import re
import argparse
import base64


parser = argparse.ArgumentParser()
parser.add_argument("--context", "-c", help="Path to the changelog context file")

release_group = parser.add_mutually_exclusive_group()
release_group.add_argument("--items", "-i", choices=["unreleased", "latest", "current"], help="Items to include in the changelog", default="full")
release_group.add_argument("--since", "-s", help="Include items since a specific version")

args = parser.parse_args()

if args.since == "0.0.0":
    args.since = None
    
PULL_LINK_PATTERN = r' \(\[#\d+\]\(https:\/\/github\.com\/.+?\/pull\/\d+\)\)'
CLIFF_WORKDIR = environ.get("GIT_CLIFF_WORKDIR", getcwd())
CLIFF_IGNORE_FILE = join(CLIFF_WORKDIR, ".cliffignore")
GIT_CLIFF_OUTPUT = environ.get("GIT_CLIFF_OUTPUT")
if GIT_CLIFF_OUTPUT:
    del environ["GIT_CLIFF_OUTPUT"]
GIT_CLIFF_PREPEND = environ.get("GIT_CLIFF_PREPEND")
if GIT_CLIFF_PREPEND:
    del environ["GIT_CLIFF_PREPEND"]

GITHUB_ACTION_OUTPUT = environ.get("GITHUB_OUTPUT")
if GIT_CLIFF_OUTPUT or GIT_CLIFF_PREPEND:
    GITHUB_ACTION_OUTPUT = None


def escape_control_characters(s):
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', lambda c: "\\u{0:04x}".format(ord(c.group())), s)


def strip_pull_request_links(text):
    return re.sub(PULL_LINK_PATTERN, '', text).strip()


def in_git_repo():
    try:
        subprocess.check_output(['git', '-C', CLIFF_WORKDIR, 'rev-parse'])
        return True
    except subprocess.CalledProcessError:
        return False


def is_tag(tag):
    try:
        subprocess.check_output(['git', '-C', CLIFF_WORKDIR, 'rev-parse', tag])
        return True
    except subprocess.CalledProcessError:
        return False


def valid_json(s):
    try:
        json.loads(escape_control_characters(s))
        return True
    except json.JSONDecodeError:
        return False


def run_cliff(get_context = False):
    command = ["git", "cliff"]
    mute = False

    if args.items == "unreleased":
        command.append("--unreleased")
    elif args.items == "latest":
        command.append("--latest")
    elif args.items == "current":
        command.append("--current")
    elif args.since:
        last_commit = subprocess.check_output(["git", "-C", CLIFF_WORKDIR, "log", "-1", "--pretty=format:%h"]).decode().strip()
        command.append(f"{args.since}..{last_commit}")

    if get_context:
        command.append("--context")
        mute = True
    elif GIT_CLIFF_OUTPUT:
        command.append("--output")
        command.append(GIT_CLIFF_OUTPUT)
    elif GIT_CLIFF_PREPEND:
        command.append("--prepend")
        command.append(GIT_CLIFF_PREPEND)

    process = subprocess.Popen(command, env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # interact with the subprocess's standard output and error streams
    stdout, stderr = process.communicate()

    if not mute:
        if stderr.strip():
            output = stderr.decode()
        else:
            output = stdout.decode()
        
        if GITHUB_ACTION_OUTPUT:
            delimiter = base64.b64encode(urandom(15)).decode('utf-8')
            with open(GITHUB_ACTION_OUTPUT, 'a') as f:
                f.write(f'changelog<<{delimiter}\n')
                f.write(f'{output}\n')
                f.write(f'{delimiter}\n')
        else:
            print(output)

    return stdout.decode().strip()

if not args.context or not isfile(args.context):
    CONTEXT = run_cliff(get_context=True)
else:
    with open(args.context, 'r') as f:
        CONTEXT = f.read()

if not valid_json(CONTEXT):
    raise Exception("You need to provide a valid changelog context (json)")
if not in_git_repo():
    raise Exception("You have to run this script in a git repository or provide a proper `GIT_CLIFF_WORKDIR` environment variable.")
elif args.since and not is_tag(args.since):
    raise Exception(f"The tag provided {args.since} doesn't exist.")
else:
    # empty the file
    with open(CLIFF_IGNORE_FILE, 'w') as f:
        f.write("")

escaped_json_string = escape_control_characters(CONTEXT)
changelog_context = json.loads(escaped_json_string)

for entry in changelog_context:
    last_commit = None
    for commit in entry.get('commits', []):

        message = commit['message']
        if not (last_commit and re.search(PULL_LINK_PATTERN, message)):
            last_commit = commit
            continue
        
        stripped_message = strip_pull_request_links(message)
        if stripped_message == last_commit['message'] and \
                commit.get('scope') == last_commit.get('scope'):
            # add to ignored commits (as the merge commit will be part of the changelog)
            with open(CLIFF_IGNORE_FILE, 'a') as f:
                f.write(f"{last_commit['id']}\n")
        last_commit = commit


run_cliff()

# delete the ignore file
subprocess.run(["rm", "-f", CLIFF_IGNORE_FILE])
