import os
import json
from ovos_utils.bracket_expansion import expand_parentheses, expand_options
from ovos_skills_manager import SkillEntry


branch = os.getenv("BRANCH")
if not branch:
    raise ValueError("environment variable `BRANCH` not set")
repo = os.getenv("REPO")
if not repo:
    raise ValueError("environment variable `REPO` not set")
author = "builderjer"

url = f"https://github.com/{author}/{repo}@{branch}"

skill = SkillEntry.from_github_url(url)
tmp_skills = "/tmp/osm_installed_skills"
skill_folder = f"{tmp_skills}/{skill.uuid}"

BASE_FOLDER = os.getenv("BASE_FOLDER")
if not BASE_FOLDER:
    raise ValueError("environment variable `LOCALE_FOLDER` not set")
elif not os.path.exists(BASE_FOLDER):
    raise ValueError(f"environment variable `LOCALE_FOLDER` is not a folder: {BASE_FOLDER}")


desktop_dir = os.path.join(BASE_FOLDER, "res", "desktop")
android_ui = os.path.join(BASE_FOLDER, "ui", "+android")
os.makedirs(desktop_dir, exist_ok=True)

readme = os.path.join(BASE_FOLDER, "readme.md")
jsonf = os.path.join(desktop_dir, "skill.json")
desktopf = os.path.join(desktop_dir, f"{repo}.desktop")
skill_code = os.path.join(BASE_FOLDER, "__init__.py")

res_folder = os.path.join(BASE_FOLDER, "locale", "en-us")

def read_samples(path):
    samples = []
    with open(path) as fi:
        for _ in fi.read().split("\n"):
            if _ and not _.strip().startswith("#"):
                samples += expand_options(_)
    return samples

samples = []
for root, folders, files in os.walk(res_folder):
    for f in files:
        if f.endswith(".intent"):
            samples += read_samples(os.path.join(root, f))
skill._data["examples"] = list(set(samples))

has_android = os.path.exists(android_ui)
with open(skill_code) as f:
    has_homescreen = f"{repo}.{author}.home" in f.read()

if not os.path.exists(readme):
    with open(readme, "w") as f:
        f.write(skill.generate_readme())

if has_homescreen and not os.path.exists(desktopf):
    with open(desktopf, "w") as f:
        f.write(skill.desktop_file)

if not os.path.exists(jsonf):
    data = skill.json
    with open(jsonf, "w") as f:
        if not has_android or not has_homescreen:
            data.pop("android")
        if not has_homescreen:
            data.pop("desktop")
            data["desktopFile"] = False
else:
    with open(jsonf) as f:
        data = json.load(f)

# set dev branch
data["branch"] = "dev"

with open(jsonf, "w") as f:
    json.dump(data, f, indent=4)
