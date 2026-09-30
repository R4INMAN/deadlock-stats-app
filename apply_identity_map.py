"""Re-key the data store on player identity instead of on nickname.

    python apply_identity_map.py --dry-run     # report what would change
    python apply_identity_map.py               # write it

Reads data/identity_proposal.json (see build_identity_map.py) and rewrites three files:

  players.json  keyed by player_key, each record carrying display_name, account_ids and the
                nicknames that person has been recorded under
  matches.json  every player row gains player_key; the typed `player` string stays as it was
  ranks.json    every entry gains player_key alongside the name it was logged against

The player_key is the person's primary Steam account_id, or their nickname when we have never
seen them in a match the API has. Nicknames are not account ids and never collide with one:
every temporary key in our data is non-numeric.

Nothing reads a key for meaning - it is an opaque handle - so a player who later turns up in an
imported match can be re-keyed by rerunning this, and a player who changes their alias needs no
migration at all, which is the entire point. Their display_name changes in one record and every
match, rank and leaderboard row follows.

The old `player` string is kept rather than replaced. It is what someone actually typed on the
night, it is the only evidence if a key is ever assigned wrongly, and it costs nothing.
"""
import argparse
import collections
import json
import os
import sys

from utils import data_io

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROPOSAL_FILE = os.path.join(ROOT_DIR, "data", "identity_proposal.json")

# Where one account was recorded under two nicknames, which display name to keep. Merging is
# automatic - two nicknames resolving to one account are one person by definition - but which
# of their names is current is not something the data can answer.
#
# 1128930437 played once as `ophianoi` and once as `glyde`. Recorded as ophianoi pending a
# check with the group; see the note at the top of IDEAS.md.
PREFERRED_DISPLAY_NAME = {
    "1128930437": "ophianoi",
}


def player_keys(proposal, players, matches):
    """(nickname -> player_key, player_key -> [nicknames]) over everyone we know about."""
    resolved = proposal["players"]
    key_of = {}
    for nickname, entry in resolved.items():
        # account_ids is ordered by how many games voted for it, so the first is the primary.
        key_of[nickname] = entry["account_ids"][0] if entry["account_ids"] else nickname

    # Everyone the proposal never saw: players who only appear in matches the API does not
    # have, plus registered players who have never played a game. Their nickname is the key.
    known = {p["player"] for m in matches for p in m["players"]} | set(players)
    for nickname in known - set(key_of):
        key_of[nickname] = nickname

    by_key = collections.defaultdict(list)
    for nickname, key in key_of.items():
        by_key[key].append(nickname)
    return key_of, dict(by_key)


def build_players(players, by_key, games_played):
    """The re-keyed players.json."""
    out = {}
    for key, nicknames in sorted(by_key.items()):
        # Most-played nickname wins the display slot, so a merge keeps the name the group
        # actually uses rather than whichever sorted first.
        preferred = PREFERRED_DISPLAY_NAME.get(key)
        display = preferred if preferred in nicknames else max(
            nicknames, key=lambda n: (games_played.get(n, 0), n)
        )
        # Notes and reported rank were held per nickname. On a merge the non-empty one wins;
        # two non-empty notes get joined rather than one being dropped on the floor.
        notes = [players.get(n, {}).get("notes") for n in sorted(nicknames)]
        notes = [n for n in notes if n]
        ranks = [players.get(n, {}).get("reported_rank") for n in nicknames]
        ranks = [r for r in ranks if r]
        out[key] = {
            "display_name": display,
            "account_ids": [key] if key.isdigit() else [],
            "aliases": sorted(nicknames),
            "notes": " / ".join(notes),
            "reported_rank": ranks[0] if ranks else None,
        }
    return out


def add_alt_accounts(out, proposal, key_of):
    """Fold every player's non-primary account into their record."""
    for nickname, entry in proposal["players"].items():
        key = key_of[nickname]
        if key not in out:
            continue
        for account_id in entry["account_ids"]:
            if account_id not in out[key]["account_ids"]:
                out[key]["account_ids"].append(account_id)


def stamp(matches, ranks, key_of):
    """Add player_key to every match player row and every rank entry. Returns (n, n, missing)."""
    missing = set()
    match_rows = 0
    for match in matches:
        for row in match["players"]:
            key = key_of.get(row["player"])
            if key is None:
                missing.add(row["player"])
                continue
            row["player_key"] = key
            match_rows += 1
    rank_rows = 0
    for entry in ranks:
        key = key_of.get(entry["player"])
        if key is None:
            missing.add(entry["player"])
            continue
        entry["player_key"] = key
        rank_rows += 1
    return match_rows, rank_rows, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    # Only the write is refused against a configured app: a whole-file rewrite cannot detect a
    # concurrent edit, so it would drop whatever landed while this was running. A dry run reads
    # and reports, which is safe anywhere - and against a configured app it reads the live data
    # branch, which is the copy that actually matters.
    if data_io.github_sync.configured() and not args.dry_run:
        sys.exit(
            "This rewrites whole files, which the app's write path deliberately cannot do, so "
            "it only writes against a checkout. Move .streamlit/secrets.toml aside, run it, "
            "review the diff, and commit."
        )
    if not os.path.exists(PROPOSAL_FILE):
        sys.exit("No data/identity_proposal.json - run build_identity_map.py first.")

    with open(PROPOSAL_FILE, encoding="utf-8") as fh:
        proposal = json.load(fh)
    matches = data_io.load_matches()
    players = data_io.load_players()
    ranks = data_io.load_ranks()

    games_played = collections.Counter(p["player"] for m in matches for p in m["players"])
    key_of, by_key = player_keys(proposal, players, matches)
    new_players = build_players(players, by_key, games_played)
    add_alt_accounts(new_players, proposal, key_of)
    match_rows, rank_rows, missing = stamp(matches, ranks, key_of)

    merges = {k: v for k, v in by_key.items() if len(v) > 1}
    temporary = [k for k in new_players if not k.isdigit()]
    with_alts = [k for k, v in new_players.items() if len(v["account_ids"]) > 1]

    print(f"{len(players)} player records -> {len(new_players)} keyed by identity")
    print(f"  {len(new_players) - len(temporary):3d} keyed by Steam account id")
    print(f"  {len(temporary):3d} keyed by nickname for now (never seen in an API match)")
    print(f"  {len(with_alts):3d} carrying more than one account")
    print(f"  {match_rows} match rows and {rank_rows} rank entries stamped")

    if merges:
        print("\nNicknames merged into one player:")
        for key, nicknames in merges.items():
            print(f"  {key}: {', '.join(sorted(nicknames))} -> {new_players[key]['display_name']}")
    if missing:
        print(f"\nNo key for: {', '.join(sorted(missing))} (left unstamped)")

    if args.dry_run:
        print("\nDry run - nothing written.")
        return 0

    data_io.save_matches(matches)
    data_io._save_local(data_io.PLAYERS_FILE, new_players)
    data_io._save_local(data_io.RANKS_FILE, ranks)
    print("\nWrote players.json, matches.json and ranks.json. Review the diff before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
