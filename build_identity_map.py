"""Propose a `nickname -> Steam account_id` map by matching rosters against the API.

    python build_identity_map.py            # writes data/identity_proposal.json

We key players by nickname; the Deadlock API keys them by `account_id` and returns no name at
all. So the map cannot be looked up - it has to be inferred once, and the lever is
co-occurrence: a player who appears in matches {3, 9, 14} is the account that appears in
matches {3, 9, 14}. Across the API-visible matches most people have a match-set nobody else
shares, and fall out uniquely.

Why similarity rather than exact set equality. Our rosters are hand-typed, so a few of them
disagree with the API - a sub who was never recorded, a wrong pick in the dropdown. Requiring
an exact match makes one bad row anywhere in a 43-game career disqualify that player against
every account, which is precisely backwards: the people with the most games, whose identity is
least in doubt, are the ones most likely to carry a typo somewhere. Jaccard overlap degrades
gracefully instead, and the residual disagreements are reported rather than hidden - each one
is a match worth looking at by hand.

Two kinds of player cannot be resolved here, and are not guesses to make:

  - Someone who has only ever played in the same matches as someone else. Their match-sets are
    identical, so no amount of arithmetic separates them; the proposal lists the candidates and
    a human picks. This is most of the residue, and it is all low-game-count players.
  - Someone who appears only in the matches the API never ingested. There is no account_id to
    find. They get a `local:` key and can be upgraded the first time they turn up in an
    imported match.

This script only proposes. It does not touch players.json or matches.json - review
data/identity_proposal.json, fill in the `unresolved` entries, then apply it.
"""
import collections
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from utils import data_io

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT_DIR, "data", ".api_match_cache.json")
PROPOSAL_FILE = os.path.join(ROOT_DIR, "data", "identity_proposal.json")

METADATA_URL = "https://api.deadlock-api.com/v1/matches/{}/metadata"
# The default urllib/requests User-Agent is refused with a 403; any real one is fine. Easy to
# misread as the API having died.
HEADERS = {"User-Agent": "deadlock-stats-app/1.0 (PUG stats)"}
WORKERS = 4
TIMEOUT = 25

# A proposal is taken as settled when it overlaps this well and beats its runner-up by this
# much. Both matter: a lone high score means little when a second account scores the same.
CONFIDENT_OVERLAP = 0.8
CONFIDENT_MARGIN = 0.3
PROBABLE_MARGIN = 0.15


def fetch_account_ids(match_ids):
    """{match_id: [account_id, ...] or None}, cached on disk so re-runs are cheap.

    A miss is cached too. Our custom lobbies are not in the API's database and never will be,
    and an uncached miss costs a timeout on every re-run.
    """
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as fh:
            cache = json.load(fh)

    todo = [m for m in match_ids if m not in cache]
    if todo:
        print(f"Fetching {len(todo)} match{'es' if len(todo) != 1 else ''} from the API...")

        def one(match_id):
            try:
                r = requests.get(METADATA_URL.format(match_id), headers=HEADERS, timeout=TIMEOUT)
                if r.status_code != 200:
                    return match_id, None
                info = r.json().get("match_info", {})
                ids = [p.get("account_id") for p in info.get("players", [])]
                return match_id, [i for i in ids if i] or None
            except (requests.RequestException, ValueError):
                return match_id, None

        with ThreadPoolExecutor(WORKERS) as pool:
            for match_id, ids in pool.map(one, todo):
                cache[match_id] = ids
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=1)

    return {m: cache.get(m) for m in match_ids}


def match_sets(matches, api):
    """(nickname -> match ids, account_id -> match ids), over the API-visible matches only."""
    names, accounts = collections.defaultdict(set), collections.defaultdict(set)
    for match in matches:
        ids = api.get(match["match_id"])
        if not ids:
            continue
        for player in match["players"]:
            names[player["player"]].add(match["match_id"])
        for account_id in ids:
            accounts[str(account_id)].add(match["match_id"])
    return names, accounts


def jaccard(a, b):
    return len(a & b) / len(a | b)


def solve(names, accounts):
    """Greedy one-to-one assignment by overlap, highest-scoring pair first.

    Greedy rather than a full optimal assignment because the score gaps here are not close: a
    real pairing sits near 1.0 with its runner-up well below, so the order pairs are taken in
    does not change the answer. It also keeps every decision explainable as its own number,
    which is what a human reviewing the borderline ones actually needs.

    Returns {nickname: (account_id, overlap, margin over the runner-up)}.
    """
    scored = sorted(
        (jaccard(s, t), name, account_id)
        for name, s in names.items()
        for account_id, t in accounts.items()
        if s & t
    )
    scored.reverse()

    best, runner_up = collections.defaultdict(float), collections.defaultdict(float)
    for score, name, _ in scored:
        if score > best[name]:
            runner_up[name], best[name] = best[name], score
        elif score > runner_up[name]:
            runner_up[name] = score

    assigned, taken = {}, set()
    for score, name, account_id in scored:
        if name in assigned or account_id in taken:
            continue
        assigned[name] = (account_id, score, score - runner_up[name])
        taken.add(account_id)
    return assigned


def confidence(overlap, margin):
    if overlap >= CONFIDENT_OVERLAP and margin >= CONFIDENT_MARGIN:
        return "confident"
    return "probable" if margin >= PROBABLE_MARGIN else "unresolved"


def build(matches, api):
    """The whole proposal, as the dict written to disk."""
    names, accounts = match_sets(matches, api)
    assigned = solve(names, accounts)

    proposals, unresolved = {}, {}
    for name in sorted(names):
        account_id, overlap, margin = assigned.get(name, (None, 0.0, 0.0))
        kind = confidence(overlap, margin) if account_id else "unresolved"
        ours = names[name]
        theirs = accounts.get(account_id, set()) if account_id else set()
        entry = {
            "account_id": account_id,
            "games_seen": len(ours),
            "overlap": round(overlap, 3),
            "margin": round(margin, 3),
            # Where the two disagree: ours-without-theirs is a match we credited to this player
            # that the account was not in, and vice versa. Each one is a roster worth checking.
            "we_have_they_dont": sorted(ours - theirs),
            "they_have_we_dont": sorted(theirs - ours),
        }
        if kind == "unresolved":
            # Blank the greedy pick. It won the tie-break by iteration order rather than by
            # evidence, and left in place it reads like an answer - the one thing a reviewer
            # must not take on trust here.
            entry["account_id"] = None
            ranked = sorted(
                (round(jaccard(ours, t), 3), a) for a, t in accounts.items() if ours & t
            )
            entry["candidates"] = [
                {"account_id": a, "overlap": s} for s, a in ranked[::-1][:5]
            ]
            unresolved[name] = entry
        else:
            entry["confidence"] = kind
            proposals[name] = entry

    all_names = {p["player"] for m in matches for p in m["players"]}
    return {
        "_readme": "Review `unresolved` and fill in each `account_id` by hand, then apply. "
                   "Entries with a non-empty `we_have_they_dont` are worth checking even when "
                   "confident: each is a match whose roster disagrees with the API.",
        "proposals": proposals,
        "unresolved": unresolved,
        # Everyone who only ever appears in matches the API does not have. No account_id exists
        # to find, so they stay locally keyed until an imported match turns one up.
        "local_only": sorted(all_names - set(names)),
    }


def main():
    matches = data_io.load_matches()
    api = fetch_account_ids([m["match_id"] for m in matches])
    visible = sum(1 for v in api.values() if v)
    print(f"{visible}/{len(matches)} matches are in the API; {len(matches) - visible} are "
          f"custom lobbies it never ingested.\n")

    out = build(matches, api)
    with open(PROPOSAL_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    proposals, unresolved = out["proposals"], out["unresolved"]
    confident = sum(1 for p in proposals.values() if p["confidence"] == "confident")
    print(f"  {confident:3d} confident")
    print(f"  {len(proposals) - confident:3d} probable    (worth a glance)")
    print(f"  {len(unresolved):3d} unresolved  (needs a human - candidates listed)")
    print(f"  {len(out['local_only']):3d} local only  (never in an API match, no account_id exists)")

    disagreements = {n: p for n, p in proposals.items() if p["we_have_they_dont"]}
    if disagreements:
        print("\nRoster disagreements - our entry vs. the API, worth checking by hand:")
        for name, p in sorted(disagreements.items(), key=lambda kv: -len(kv[1]["we_have_they_dont"])):
            ids = ", ".join(p["we_have_they_dont"])
            print(f"  {name:24s} overlap {p['overlap']:.2f}  match {ids}")

    print(f"\nWrote {os.path.relpath(PROPOSAL_FILE, ROOT_DIR)}. Nothing else was modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
