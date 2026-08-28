import base64
import json
import requests
import streamlit as st


def _config():
    try:
        return st.secrets["github_token"], st.secrets["github_repo"], st.secrets.get("github_branch", "main")
    except Exception:
        return None, None, None


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def pull_file(repo_relative_path):
    """Fetch a file's content from the GitHub repo. Returns text, or None if unavailable/not configured."""
    token, repo, branch = _config()
    if not token:
        return None
    url = f"https://api.github.com/repos/{repo}/contents/{repo_relative_path}"
    try:
        resp = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
        if resp.status_code != 200:
            return None
        return base64.b64decode(resp.json()["content"]).decode("utf-8")
    except Exception:
        return None


def push_file(repo_relative_path, content_str, commit_message):
    """Create or update a file in the GitHub repo. Best-effort; returns True/False."""
    token, repo, branch = _config()
    if not token:
        return False
    url = f"https://api.github.com/repos/{repo}/contents/{repo_relative_path}"
    try:
        get_resp = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=10)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(url, headers=_headers(token), data=json.dumps(payload), timeout=10)
        return put_resp.status_code in (200, 201)
    except Exception:
        return False