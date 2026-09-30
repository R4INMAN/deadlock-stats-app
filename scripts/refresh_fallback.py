"""Refresh main's copy of `data/*.json` from the live data branch.

`main` carries its own copy of the data files. It is the seed for local development and the
copy the app serves if GitHub is unreachable, so it drifts behind the `data` branch as matches
are logged. This pulls the live files down onto your working tree so the gap can be closed with
an ordinary pull request.

It copies files, deliberately, rather than merging `data` into `main`. The data branch has its
own history - a commit per logged match, plus the `_sync_check.json` heartbeat - and merging it
would drag all of that onto `main` and put the heartbeat back on a branch that should not carry
it. Only the four data files move, and the heartbeat is left where it belongs.

This writes to your working tree and nothing else: no commit, no push. Review the diff and open
a PR the usual way.

    python scripts/refresh_fallback.py            # show what would change
    python scripts/refresh_fallback.py --write    # write it
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")

# The files the app actually writes. `data/_sync_check.json` is intentionally absent: it is the
# write-access heartbeat and belongs only to the data branch. The vendored assets on `main`
# (rank_tiers, hero_visuals, palette) are absent for the opposite reason - they are refreshed
# from the game's own API by fetch_deadlock_assets.py and never live on the data branch.
TRACKED = [
    ("data/matches.json", "matches", list),
    ("data/players.json", "players", dict),
    ("data/heroes.json", "heroes", list),
    ("data/ranks.json", "rank entries", list),
]


def _local(path):
    """Current on-disk contents of a repo-relative path, or None if it isn't there."""
    full = os.path.join(ROOT_DIR, path.replace("/", os.sep))
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    """Write with the same formatting `data_io._save_local` uses, so diffs stay minimal."""
    full = os.path.join(ROOT_DIR, path.replace("/", os.sep))
    with open(full, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    from utils import github_sync

    write = "--write" in sys.argv

    print("1. Configuration")
    if not github_sync.configured():
        print("   FAIL  No github_token / github_repo found.")
        print("         This reads the data branch over the API, so it needs the same secrets")
        print("         the app uses. See 'Configuring it' in the README.")
        return 1
    print(f"   ok    Reading {github_sync.target()}")

    print("\n2. Comparing")
    changes = []
    try:
        for path, label, expected in TRACKED:
            remote, _ = github_sync.read_json(path, default=None)
            if remote is None:
                print(f"   FAIL  {path} is missing from the branch.")
                return 1
            if not isinstance(remote, expected):
                print(f"   FAIL  {path} is a {type(remote).__name__}, expected {expected.__name__}.")
                return 1

            local = _local(path)
            if local == remote:
                print(f"   ok    {path:<22} in sync ({len(remote)} {label})")
                continue

            delta = len(remote) - (len(local) if local is not None else 0)
            sign = f"+{delta}" if delta > 0 else str(delta)
            print(f"   diff  {path:<22} {len(remote)} {label} on the branch ({sign})")
            changes.append((path, remote))
    except github_sync.SyncError as exc:
        print(f"   FAIL  {exc}")
        return 1

    if not changes:
        print("\nThe fallback already matches the data branch. Nothing to do.")
        return 0

    if not write:
        print(f"\n{len(changes)} file(s) behind. Re-run with --write to update your working tree.")
        return 0

    print("\n3. Writing")
    for path, remote in changes:
        _write(path, remote)
        print(f"   ok    Wrote {path}")

    print("\nWorking tree updated. Review `git diff`, then commit on a branch and open a PR.")
    print("Do not merge the data branch into main - copying these files is the whole job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
