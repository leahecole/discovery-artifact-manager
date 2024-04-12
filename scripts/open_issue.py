# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import subprocess
import sys
import time
from typing import Optional



REPO_NAME = "leahecole/discovery-artifact-manager" #TODO(coleleah): update
GIT_USER_NAME = "leahecole" #TODO(coleleah): update
GIT_USER_EMAIL = "6719667+leahecole@users.noreply.github.com." #TODO(coleleah): update
ISSUE_BODY = "Automatically created by the update_disco script." #TODO(coleleah): update
MAIN_TOKEN_ENV = "GITHUB_TOKEN"
ISSUE_TITLE = "Test issue" #TODO update

# TODO(coleleah): update
def main() -> None:
    """
    TODO update docstring
    """
    logging.basicConfig(level=logging.INFO)
    if has_changes():
        print("Git changes detected. Opening pull request ...")
        github_token: Optional[str] = setup()
        open_issue(github_token)
        print("Complete.")
    else:
        print("No git changes. Bailing.")


# TODO(coleleah): could be used with Seth's thing? 
def has_changes() -> bool:
    # """Determine if there are local changes

    # Returns:
    #     bool -- True if there are local changes, or False otherwise
    # """
    # result: subprocess.CompletedProcess = subprocess.run(
    #     ["git", "status", "-s"], capture_output=True
    # )
    # return str(result.stdout, "utf-8").strip() != ""
    return True

# TODO(coleleah): update
def setup() -> Optional[str]:
    """Ensure the right environment for creating a pull request

    Returns:
        Optional[str] -- The github token, or None if not provided
    """
    ensure_git_identity()
    github_token: Optional[str] = os.getenv(MAIN_TOKEN_ENV)
    username: str = ensure_github_username()
    # fork_repo_name: str = REPO_NAME.replace("googleapis/", f"{username}/")
    # ensure_github_fork(fork_repo_name)
    # ensure_git_remote(github_token, username, fork_repo_name)
    return github_token

# TODO(coleleah): update if needed
def ensure_git_identity() -> None:
    """Ensure that the git identity (name and email) is set"""
    result: subprocess.CompletedProcess
    result = subprocess.run(
        ["git", "config", "--get", "user.name"], capture_output=True
    )
    if result.returncode != 0:
        logging.info(f"Setting git user.name to {GIT_USER_NAME}")
        subprocess.run(["git", "config", "--local", "user.name", GIT_USER_NAME])
    result = subprocess.run(
        ["git", "config", "--get", "user.email"], capture_output=True
    )
    if result.returncode != 0:
        logging.info(f"Setting git user.email to {GIT_USER_EMAIL}")
        subprocess.run(["git", "config", "--local", "user.email", GIT_USER_EMAIL])

# TODO(coleleah): update if needed

def ensure_github_username() -> str:
    """Get the current GitHub user name, ensuring it exists

    Returns:
        str -- The GitHub user name
    """
    result: subprocess.CompletedProcess = subprocess.run(
        ["gh", "api", "/user", "--jq=.login"], capture_output=True
    )
    username: str = str(result.stdout, "utf-8").strip()
    if len(username) == 0:
        sys.exit(
            "Unable to determine GitHub username; you need to be logged in using gh"
        )
    logging.info(f"Detected GitHub username: {username}")
    return username


def open_issue(github_token: Optional[str]) -> None:
    """Actually open the issue

    Arguments:
        github_token {Optional[str]} -- The github token, if provided
    """
    issue_number: str = create_issue()
    logging.info(f"Opened issue {issue_number}")





# TODO(coleleah): update
def create_issue() -> str:
    """Creates an issue and waits for it to appear in the API

    Returns:
        str -- The issue number as a string
    """
    logging.info("Creating issue.")
    result: subprocess.CompletedProcess
    # TODO - properly assign
    result = subprocess.run(
        [
            "gh",
            "issue",
            "create",
            "--title",
            ISSUE_TITLE,
            "--body",
            ISSUE_BODY,
        ],
        capture_output=True,
        check=True,
    )
    issue_number: str = str(result.stdout, "utf-8").splitlines()[-1].split("/")[-1]
    logging.info(f"Issue number is {issue_number}.")
    for count in range(5):
        result = subprocess.run(
            ["gh", "issue", "view", issue_number, "--repo", REPO_NAME, "--json=number"]
        )
        if result.returncode == 0:
            logging.info("Confirmed existence of new issue.")
            break
        logging.info("Couldn't confirm pull request yet ...")
        time.sleep(count + 1)
    time.sleep(5)
    return issue_number


if __name__ == "__main__":
    main()
