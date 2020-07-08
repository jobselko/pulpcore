# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --travis pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

import argparse
import json
import os
import textwrap
from collections import defaultdict
from pathlib import Path

from git import Repo
from redminelib import Redmine
from redminelib.exceptions import ResourceAttrError


REDMINE_URL = "https://pulp.plan.io"
REDMINE_QUERY_URL = f"{REDMINE_URL}/issues?set_filter=1&status_id=*&issue_id="


def validate_redmine_data(redmine_query_url, redmine_issues):
    """Validate redmine milestone."""
    redmine = Redmine("https://pulp.plan.io")
    project_set = set()
    stats = defaultdict(list)
    for issue in redmine_issues:
        redmine_issue = redmine.issue.get(int(issue))

        project_name = redmine_issue.project.name
        project_set.update([project_name])
        stats[f"project_{project_name.lower().replace(' ', '_')}"].append(issue)

        status = redmine_issue.status.name
        if "CLOSE" not in status and status != "MODIFIED":
            stats["status_not_modified"].append(issue)

        try:
            milestone = redmine_issue.fixed_version.name
            milestone_id = redmine_issue.fixed_version.id
            stats[f"milestone_{milestone}"].append(issue)
        except ResourceAttrError:
            stats["without_milestone"].append(issue)

    print(f"\n\nRedmine stats: {json.dumps(stats, indent=2)}")
    error_messages = []
    if stats.get("status_not_modified"):
        error_messages.append(f"One or more issues are not MODIFIED {stats['status_not_modified']}")
    if stats.get("without_milestone"):
        error_messages.append(
            f"One or more issues are not associated with a milestone {stats['without_milestone']}"
        )
    if len(project_set) > 1:
        error_messages.append(f"Issues with different projects - {project_set}")
    if error_messages:
        error_messages.append(f"Verify at {redmine_query_url}")
        raise RuntimeError("\n".join(error_messages))

    return f"{REDMINE_URL}/versions/{milestone_id}.json"


release_path = os.path.dirname(os.path.abspath(__file__))
plugin_path = release_path
if ".travis" in release_path:
    plugin_path = os.path.dirname(release_path)

version = {}
plugin_name = "pulpcore"
with open(f"{plugin_path}/{plugin_name}/__init__.py") as fp:
    version_line = [line for line in fp.readlines() if "__version__" in line][0]
    exec(version_line, version)
release_version = version["__version__"].replace(".dev", "")

issues_to_close = []
for filename in Path(f"{plugin_path}/CHANGES").rglob("*"):
    if filename.stem.isdigit():
        issue = filename.stem
        issue_url = f"{REDMINE_URL}/issues/{issue}.json"
        issues_to_close.append(issue)

issues = ",".join(issues_to_close)
redmine_final_query = f"{REDMINE_QUERY_URL}{issues}"
milestone_url = validate_redmine_data(redmine_final_query, issues_to_close)

helper = textwrap.dedent(
    """\
        Start the release process.

        Example:
            setup.py on plugin before script:
                version="2.0.dev"
                requirements = ["pulpcore>=3.4"]


            $ python .travis/realease.py minor 4.0 4.1

            setup.py on plugin after script:
                version="2.1.dev"
                requirements = ["pulpcore>=4.0,<4.1"]

    """
)
parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description=helper)

parser.add_argument(
    "release_type", type=str, help="Whether the release should be major, minor or patch.",
)

parser.add_argument(
    "--lower", type=str, required=False, help="Lower bound of pulpcore requirement.",
)

parser.add_argument(
    "--upper", type=str, required=False, help="Upper bound of pulpcore requirement.",
)

args = parser.parse_args()

release_type = args.release_type

if "pulpcore" not in release_path:
    lower_pulpcore_version = args.lower
    upper_pulpcore_version = args.upper

print("\n\nHave you checked the output of: $towncrier --version x.y.z --draft")
print(f"\n\nRepo path: {plugin_path}")
repo = Repo(plugin_path)
git = repo.git

git.checkout("HEAD", b=f"release_{release_version}")

# First commit: changelog
os.system(f"towncrier --yes --version {release_version}")
git.add("CHANGES.rst")
git.add("CHANGES/*")
git.commit("-m", f"Building changelog for {release_version}\n\n[noissue]")

# Second commit: release version
with open(f"{plugin_path}/requirements.txt", "rt") as setup_file:
    setup_lines = setup_file.readlines()

with open(f"{plugin_path}/requirements.txt", "wt") as setup_file:
    for line in setup_lines:
        if "pulpcore" in line and "pulpcore" not in release_path:
            line = f"pulpcore>={lower_pulpcore_version},<{upper_pulpcore_version}\n"

        setup_file.write(line)

os.system("bump2version release --allow-dirty")

git.add(f"{plugin_path}/{plugin_name}/__init__.py")
git.add(f"{plugin_path}/setup.py")
git.add(f"{plugin_path}/requirements.txt")
git.add(f"{plugin_path}/.bumpversion.cfg")
git.commit(
    "-m",
    f"Releasing {release_version}\n\nRedmineQuery: {redmine_final_query}\n"
    f"RedmineMilestone: {milestone_url}\n[noissue]",
)

sha = repo.head.object.hexsha
short_sha = git.rev_parse(sha, short=7)

# Third commit: bump to .dev
with open(f"{plugin_path}/requirements.txt", "wt") as setup_file:
    for line in setup_lines:
        if "pulpcore" in line and "pulpcore" not in release_path:
            line = f"pulpcore>={lower_pulpcore_version}\n"

        setup_file.write(line)

os.system(f"bump2version {release_type} --allow-dirty")

version = {}
with open(f"{plugin_path}/{plugin_name}/__init__.py") as fp:
    version_line = [line for line in fp.readlines() if "__version__" in line][0]
    exec(version_line, version)
new_dev_version = version["__version__"]


git.add(f"{plugin_path}/{plugin_name}/__init__.py")
git.add(f"{plugin_path}/setup.py")
git.add(f"{plugin_path}/requirements.txt")
git.add(f"{plugin_path}/.bumpversion.cfg")
git.commit("-m", f"Bump to {new_dev_version}\n\n[noissue]")

print(f"\n\nRedmine query of issues to close:\n{redmine_final_query}")
print(f"Release commit == {short_sha}")
print(f"All changes were committed on branch: release_{release_version}")
