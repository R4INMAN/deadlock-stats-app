"""Propose a `nickname -> Steam account_id` map by matching box scores against the API.

    python build_identity_map.py            # writes data/identity_proposal.json

We key players by nickname; the Deadlock API keys them by `account_id` and returns no name at
all. So the map cannot be looked up - it has to be inferred once, from the only thing the two
sides share: the numbers.

For a match the API has, we know the twelve rows we typed and it knows the twelve rows it
recorded, and they are the same twelve games of Deadlock. A line of 4/5/2 on Mina is unique
within a lobby almost every time - 99% of API stat lines are, across our history - so lining
the two rosters up against each other identifies each player individually, in a single match,
with no reference to anything else they have ever played. That matters for the one-game
guests, who are exactly the people a co-occurrence approach cannot separate: if two of them
only ever played in the same match, their careers are identical and nothing distinguishes
them, but their box scores still do.

Scoring is deliberately loose, because our rows are hand-typed and a few carry a typo. An
exact K/D/A wins outright; a hero match plus a near-miss K/D/A also clears the bar; net worth
against our recorded souls breaks what is left. Pairings that clear nothing are dropped rather
than guessed - four of 576 across our history.

Each match casts one vote per player, and the votes are aggregated at the end. Two things fall
out of that which a single match could not tell you:

  - **Alt accounts.** Nine of our regulars vote overwhelmingly for one account and a handful of
    times for another. That is not noise to be smoothed away, it is a second Steam account, and
    it is why a player owns a *list* of account_ids rather than one. Miss this and every game
    played on the alt silently detaches from its player.
  - **Alias changes.** An account that votes for two different nicknames is one person we have
    been recording as two people. There is one in our history.

This script only proposes. It does not touch players.json or matches.json - review
data/identity_proposal.json, then apply it.
"""
import collections
import json
import os
import sys

from utils import data_io, deadlock_api

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT_DIR, "data", ".api_match_cache.json")
PROPOSAL_FILE = os.path.join(ROOT_DIR, "data", "identity_proposal.json")

# A pairing is only allowed to vote if it clears this. The scale below is built so that an
# exact K/D/A alone clears it, and so does the right hero with a K/D/A off by one or two - but
# a hero match on its own never does, since six players a side means heroes repeat across the
# lobby far more often than stat lines do.
MIN_PAIR_SCORE = 6.0

# Below this share of a player's votes, an account is reported for review rather than adopted.
# A real alt shows up across several games; a single stray vote is more likely one bad pairing.
ALT_ADOPT_SHARE = 0.10


def pair_score(ours, theirs):
    """How strongly one of our rows and one API row look like the same player-game."""
    score = 0.0

    off = (abs(ours["kills"] - theirs["kills"])
           + abs(ours["deaths"] - theirs["deaths"])
           + abs(ours["assists"] - theirs["assists"]))
    score += 6.0 if off == 0 else max(0.0, 3.0 - off)

    if deadlock_api.our_hero_name_matches(ours["hero"], theirs["hero_id"]):
        score += 4.0

    # Our souls are recorded in thousands, the API's net worth in ones.
    if ours.get("souls_k") is not None and theirs.get("net_worth"):
        score += max(0.0, 2.0 - abs(ours["souls_k"] - theirs["net_worth"] / 1000.0))

    return score


def pair_up(our_rows, their_rows):
    """Best one-to-one pairing of our roster against theirs, as (our row, their row).

    Greedy from the highest-scoring pair down. An optimal assignment would cost a dependency
    and change nothing: a correct pairing scores near the ceiling while its rivals sit far
    below, so no ordering of these choices reaches a different answer.
    """
    ranked = sorted(
        ((pair_score(o, t), i, j) for i, o in enumerate(our_rows) for j, t in enumerate(their_rows)),
        key=lambda x: x[0],
        reverse=True,
    )
    used_ours, used_theirs, out = set(), set(), []
    for score, i, j in ranked:
        if i in used_ours or j in used_theirs:
            continue
        used_ours.add(i)
        used_theirs.add(j)
        if score >= MIN_PAIR_SCORE:
            out.append((our_rows[i], their_rows[j]))
    return out


def collect_votes(matches, api):
    """(nickname -> Counter of account_ids, account_id -> Counter of nicknames, rows dropped)."""
    by_name = collections.defaultdict(collections.Counter)
    by_account = collections.defaultdict(collections.Counter)
    paired = considered = 0

    for match in matches:
        their_rows = api.get(match["match_id"])
        if not their_rows:
            continue
        considered += len(match["players"])
        for ours, theirs in pair_up(match["players"], their_rows):
            paired += 1
            name, account_id = ours["player"], str(theirs["account_id"])
            by_name[name][account_id] += 1
            by_account[account_id][name] += 1

    return by_name, by_account, considered - paired


def build(matches, api):
    """The whole proposal, as the dict written to disk."""
    by_name, by_account, dropped = collect_votes(matches, api)

    players, review = {}, {}
    for name, counts in sorted(by_name.items()):
        total = sum(counts.values())
        ranked = counts.most_common()
        adopted = [a for a, n in ranked if n / total >= ALT_ADOPT_SHARE]
        thin = [{"account_id": a, "votes": n} for a, n in ranked if a not in adopted]
        players[name] = {
            "account_ids": adopted,
            "games_matched": total,
            "votes": {a: n for a, n in ranked},
        }
        if thin:
            # Too few votes to adopt outright: either a genuine alt played once, or one
            # mis-paired row. Cheap to confirm by eye, expensive to get silently wrong.
            review[name] = {"adopted": adopted, "too_thin_to_adopt": thin}

    # One account answering to two nicknames is one person recorded as two - an alias change we
    # never noticed. Worth surfacing loudly: it is the exact failure this whole change exists
    # to end, and merging them is a decision only a human should make.
    aliases = {
        account_id: dict(names.most_common())
        for account_id, names in by_account.items() if len(names) > 1
    }

    all_names = {p["player"] for m in matches for p in m["players"]}
    return {
        "_readme": "Review `alias_conflicts` first - each is one account recorded under two "
                   "nicknames. Then `review`, where an account had too few votes to adopt as "
                   "an alt. `local_only` players have never appeared in a match the API has, "
                   "so no account_id exists for them yet.",
        "players": players,
        "alias_conflicts": aliases,
        "review": review,
        "local_only": sorted(all_names - set(by_name)),
        "_stats": {"rows_dropped_as_unmatchable": dropped},
    }


def main():
    matches = data_io.load_matches()
    api = deadlock_api.match_players_cached([m["match_id"] for m in matches], CACHE_FILE)
    visible = sum(1 for v in api.values() if v)
    print(f"{visible}/{len(matches)} matches are in the API; {len(matches) - visible} are "
          f"custom lobbies it never ingested.\n")

    out = build(matches, api)
    with open(PROPOSAL_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    players = out["players"]
    with_alts = [n for n, p in players.items() if len(p["account_ids"]) > 1]
    print(f"  {len(players):3d} nicknames resolved to an account")
    print(f"  {len(with_alts):3d} of them on more than one account")
    print(f"  {len(out['local_only']):3d} local only  (never in an API match, no account_id exists)")
    print(f"  {out['_stats']['rows_dropped_as_unmatchable']:3d} rows too unlike anything to pair")

    if with_alts:
        print("\nPlayers on more than one account:")
        for name in sorted(with_alts, key=lambda n: -players[n]["games_matched"]):
            votes = ", ".join(f"{a} x{n}" for a, n in players[name]["votes"].items())
            print(f"  {name:24s} {votes}")

    if out["alias_conflicts"]:
        print("\nOne account, two nicknames - the same person recorded twice:")
        for account_id, names in out["alias_conflicts"].items():
            shown = ", ".join(f"{n} x{c}" for n, c in names.items())
            print(f"  account {account_id}: {shown}")

    if out["review"]:
        print(f"\n{len(out['review'])} player(s) have an account with too few votes to adopt; "
              f"see `review` in the proposal.")

    print(f"\nWrote {os.path.relpath(PROPOSAL_FILE, ROOT_DIR)}. Nothing else was modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
