"""Prove the app can actually reach - and write to - its data store.

Run this after setting up secrets, and any time saving misbehaves. It answers the three
questions that matter, in order, and stops at the first one that fails:

  1. Are the secrets present and pointed somewhere sensible?
  2. Can we read the data branch, and does it hold what we expect?
  3. Can we write to it? (only with --write)

The read check is safe to run any time. The write check commits a small heartbeat file,
`data/_sync_check.json`, which records when a write was last proven to work - so it leaves a
useful trace rather than litter, and never touches match data.

    python scripts/check_sync.py
    python scripts/check_sync.py --write
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRACKED = [
    ("data/matches.json", "matches", list),
    ("data/players.json", "players", dict),
    ("data/heroes.json", "heroes", list),
    ("data/ranks.json", "rank entries", list),
]
HEARTBEAT = "data/_sync_check.json"


def main():
    from utils import github_sync

    write = "--write" in sys.argv

    print("1. Configuration")
    if not github_sync.configured():
        print("   FAIL  No github_token / github_repo found.")
        print("         Locally:  create .streamlit/secrets.toml (it is gitignored).")
        print("         Hosted:   share.streamlit.io -> your app -> Settings -> Secrets.")
        return 1

    target = github_sync.target()
    print(f"   ok    Writing to {target}")
    if target.endswith("@main"):
        print("   WARN  github_branch is 'main', the branch Streamlit deploys from.")
        print("         Every save will push to it and trigger a redeploy, rebooting the app")
        print("         under whoever is using it. Set github_branch = \"data\".")

    print("\n2. Reading")
    try:
        for path, label, expected in TRACKED:
            data, sha = github_sync.read_json(path, default=None)
            if data is None:
                print(f"   FAIL  {path} is missing from the branch.")
                return 1
            if not isinstance(data, expected):
                print(f"   FAIL  {path} is a {type(data).__name__}, expected {expected.__name__}.")
                return 1
            print(f"   ok    {len(data):>5} {label:<13} {path}  ({sha[:8]})")
    except github_sync.SyncError as exc:
        print(f"   FAIL  {exc}")
        return 1

    if not write:
        print("\nRead path is healthy. Re-run with --write to prove writes land too.")
        return 0

    print("\n3. Writing")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    try:
        result = github_sync.mutate(
            HEARTBEAT,
            lambda old: {"last_verified_utc": now, "checks": (old or {}).get("checks", 0) + 1},
            f"Verify app write access ({now})",
            default={},
        )
    except github_sync.SyncError as exc:
        print(f"   FAIL  {exc}")
        return 1

    print(f"   ok    Wrote {HEARTBEAT} - write #{result['checks']} at {now}")
    print(f"\nAll good. The app can read and write {target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
