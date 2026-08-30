"""Durable storage for `data/*.json`, against the GitHub contents API.

Streamlit Community Cloud hands an app an ephemeral disk. The container is built by cloning
the repo, and it is thrown away on every restart, redeploy, and sleep. A match written to the
local filesystem therefore lives only until that container dies, at which point the app
silently reverts to whatever is committed - which is how three logged matches were lost
on 8/27.

So writes go to the repo itself. Three design points are worth stating, because two of them
were got wrong on the first attempt:

**Writes target their own branch, and default to it.** Pushing to the branch Streamlit deploys
from triggers a redeploy, so saving a match would reboot the app underneath whoever was using
it. Writes go to `DEFAULT_BRANCH` unless `github_branch` overrides it - the default lives here
rather than in a dashboard so that the repo explains the app's behaviour, and so a wiped or
forgotten secret degrades to the safe option instead of the dangerous one.

**Writes are operations, not file overwrites.** `mutate` re-reads the file immediately before
writing and re-applies the caller's change to *that* copy, then PUTs conditionally on the blob
sha it just read. If somebody else wrote in between, GitHub rejects the PUT and the whole
cycle runs again against the newer file. Because the operations are keyed by match id they
commute, so two people adding different matches at the same moment both survive - where a
read-then-overwrite would keep only the second one.

**Failures raise.** The first version returned a bare `False` on every error, and the caller
never checked it, so a save that never left the machine still printed "Match saved!" and threw
confetti. Anything that can lose data is an exception here.
"""
import base64
import json
import threading
import time

import requests
import streamlit as st

API_ROOT = "https://api.github.com"
TIMEOUT = 15

# Where writes go when secrets don't say. This is deliberately NOT the deployed branch: an
# app that falls back to writing the branch it is served from reboots itself on every save,
# and that default would be invisible in the repo - somebody would have to know a dashboard
# setting existed to predict the app's behaviour. Defaulting here instead means the code is
# the source of truth and a missing or wiped secret degrades to the safe option.
DEFAULT_BRANCH = "data"

# Branch names that are somebody's deployment. Writing to one is legal but nearly always a
# mistake, so the app says so loudly and the setup script refuses outright.
DEPLOY_BRANCH_NAMES = frozenset({"main", "master"})

# One writer at a time within this process. Streamlit serves every viewer from a single
# container, so without this two people hitting Save together would race between the read and
# the PUT and burn a conflict retry each. The API's sha check is still what makes the write
# safe - this just keeps the common case from needing the retry at all.
_write_lock = threading.Lock()


class SyncNotConfigured(Exception):
    """No usable github_token / github_repo in secrets - callers fall back to local files."""


class SyncError(Exception):
    """The write did not land. Never swallow this: the data is not saved."""


def _config():
    """(token, repo, branch) from Streamlit secrets, or None if unusable.

    Reading secrets raises rather than returning empty when no secrets file exists at all,
    which is the normal state of a local checkout, so this is deliberately forgiving - an
    unconfigured app is expected and falls back to plain local files.
    """
    try:
        token = st.secrets["github_token"]
        repo = st.secrets["github_repo"]
        branch = st.secrets.get("github_branch", DEFAULT_BRANCH)
    except Exception:
        return None
    if not token or not repo:
        return None
    return str(token), str(repo), str(branch)


def configured():
    return _config() is not None


def target():
    """'owner/repo@branch' for display, or None. Never includes the token."""
    cfg = _config()
    if not cfg:
        return None
    _, repo, branch = cfg
    return f"{repo}@{branch}"


def writes_to_deploy_branch():
    """True when saves would push to the branch the app is served from.

    Streamlit Cloud redeploys on any push to the deployed branch, so this configuration makes
    every logged match reboot the app under whoever is using it - and rewrites the code the
    running container was built from while it is running.
    """
    cfg = _config()
    return bool(cfg) and cfg[2] in DEPLOY_BRANCH_NAMES


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _contents_url(repo, path):
    return f"{API_ROOT}/repos/{repo}/contents/{path}"


def _request(method, url, token, **kwargs):
    try:
        return requests.request(method, url, headers=_headers(token), timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise SyncError(f"Could not reach GitHub: {exc}") from exc


def read_json(path, default=None):
    """(data, sha) for a JSON file on the data branch.

    A missing file is not an error - it comes back as (default, None), and a later PUT with
    sha=None creates it. A missing *branch* is an error, because that is a misconfiguration
    rather than a first write, and silently creating the branch would hide a typo in secrets.
    """
    cfg = _config()
    if not cfg:
        raise SyncNotConfigured("No github_token / github_repo in secrets.")
    token, repo, branch = cfg

    resp = _request("GET", _contents_url(repo, path), token, params={"ref": branch})

    if resp.status_code == 404:
        # Distinguish "file not there yet" from "branch not there at all".
        branch_resp = _request("GET", f"{API_ROOT}/repos/{repo}/branches/{branch}", token)
        if branch_resp.status_code == 404:
            raise SyncError(
                f"Branch '{branch}' does not exist in {repo}. Create it (or fix github_branch "
                f"in secrets) before the app can save."
            )
        return default, None

    if resp.status_code in (401, 403):
        raise SyncError(_auth_hint(resp, repo))
    if resp.status_code != 200:
        raise SyncError(f"GitHub returned {resp.status_code} reading {path}: {resp.text[:200]}")

    payload = resp.json()
    try:
        text = base64.b64decode(payload["content"]).decode("utf-8")
        return json.loads(text), payload["sha"]
    except (KeyError, ValueError) as exc:
        raise SyncError(f"{path} on branch '{branch}' is not readable JSON: {exc}") from exc


def _auth_hint(resp, repo):
    """403 has two very different causes and the fix differs, so say which one this is."""
    if resp.headers.get("X-RateLimit-Remaining") == "0":
        return "GitHub API rate limit exhausted. Wait for the limit to reset and try again."
    return (
        f"GitHub refused the token for {repo} ({resp.status_code}). The token needs "
        f"'Contents: Read and write' on that repository, and fine-grained tokens expire - "
        f"check both in github.com/settings/personal-access-tokens."
    )


def mutate(path, op, message, default=None, max_attempts=5):
    """Apply `op` to the JSON at `path` and commit the result. Returns the written data.

    `op` takes the file's current contents and returns the new contents. It may be called more
    than once - every conflict retry re-runs it against a freshly pulled copy - so it must be a
    pure function of what it is handed and must not mutate its argument in place. Raising from
    `op` aborts the write with nothing committed, which is how callers reject a duplicate match
    id after seeing the real current data.
    """
    cfg = _config()
    if not cfg:
        raise SyncNotConfigured("No github_token / github_repo in secrets.")
    token, repo, branch = cfg

    with _write_lock:
        for attempt in range(max_attempts):
            current, sha = read_json(path, default)
            updated = op(current)

            body = {
                "message": message,
                "content": base64.b64encode(
                    (json.dumps(updated, indent=2) + "\n").encode("utf-8")
                ).decode("ascii"),
                "branch": branch,
            }
            if sha:
                body["sha"] = sha

            resp = _request("PUT", _contents_url(repo, path), token, data=json.dumps(body))

            if resp.status_code in (200, 201):
                return updated

            # 409 is the documented conflict; 422 comes back when the sha we sent has already
            # been superseded. Both mean "someone wrote first" - re-read and replay the op.
            if resp.status_code in (409, 422):
                if attempt < max_attempts - 1:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise SyncError(
                    f"Gave up writing {path} after {max_attempts} attempts - somebody else "
                    f"keeps saving at the same moment. Nothing was lost; try again."
                )

            if resp.status_code in (401, 403):
                raise SyncError(_auth_hint(resp, repo))
            raise SyncError(
                f"GitHub returned {resp.status_code} writing {path}: {resp.text[:200]}"
            )

        # Unreachable: the loop either returns or raises. Here so a future edit to the retry
        # conditions cannot turn "gave up" into "silently returned None".
        raise SyncError(f"Gave up writing {path} after {max_attempts} attempts.")
