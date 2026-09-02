"""Loading and saving the JSON data store.

Where the data actually lives depends on configuration. With `github_token` / `github_repo` in
Streamlit secrets - the hosted app - the data branch in the repo is the source of truth, and
every edit is a commit there (see `utils/github_sync.py` for why). With no secrets - a plain
local checkout - the files under `data/` are read and written directly, so `streamlit run`
works offline with no token and no network.

Reads are cached in-process. The alternative is a GitHub round trip per widget interaction,
since Streamlit re-runs the whole script on every click, and `matches.json` is 440KB. The
cache is dropped the moment a write lands, so the app never shows a viewer their own edit
missing; the TTL only bounds how long an edit made *outside* the app (a hand commit to the
data branch) takes to show up.
"""
import copy
import json
import os
import threading
import time
from datetime import date

from utils import github_sync

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
HERO_PORTRAIT_DIR = os.path.join(ROOT_DIR, "assets", "heroes")

MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")
HEROES_FILE = os.path.join(DATA_DIR, "heroes.json")
RANKS_FILE = os.path.join(DATA_DIR, "ranks.json")
RANK_TIERS_FILE = os.path.join(DATA_DIR, "rank_tiers.json")
HERO_VISUALS_FILE = os.path.join(DATA_DIR, "hero_visuals.json")

CACHE_TTL_SECONDS = 300

# How long a failed remote read is remembered before trying again. Without it an outage costs a
# fresh request per file per script re-run - and Streamlit re-runs the whole script on every
# click, across four files, at a 15s timeout each, so a page would hang for a minute instead of
# rendering. Short enough that recovery is quick, long enough that the app stays usable.
FAILURE_TTL_SECONDS = 30

_cache = {}
_stale = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- storage plumbing

def _repo_path(path):
    """Absolute local path -> the repo-relative path the contents API wants."""
    return os.path.relpath(path, ROOT_DIR).replace(os.sep, "/")


def _load_local(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_local(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load(path, default):
    """Current contents, from the data branch when configured, else from disk.

    If the remote read fails on a configured app the committed copy is served instead, so a
    GitHub outage degrades the app to stale-but-readable rather than blank. The failure is
    recorded per file rather than in one global: a page loads four of these, and a later success
    on `players.json` must not clear the warning that `matches.json` is stale - silently showing
    stale data is how you get someone re-entering a match that already exists.
    """
    if not github_sync.configured():
        return _load_local(path, default)

    now = time.time()
    with _cache_lock:
        cached = _cache.get(path)
        if cached and now - cached[1] < CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[0])
        failed = _stale.get(path)
        if failed and now - failed[1] < FAILURE_TTL_SECONDS:
            return _load_local(path, default)

    try:
        data, _ = github_sync.read_json(_repo_path(path), default)
    except github_sync.SyncError as exc:
        with _cache_lock:
            _stale[path] = (str(exc), now)
        return _load_local(path, default)

    with _cache_lock:
        _cache[path] = (data, now)
        _stale.pop(path, None)
    return copy.deepcopy(data)


def _mutate(path, op, message, default):
    """Apply `op` to a file's contents and persist the result.

    `op` may be re-run against freshly pulled data if someone else writes first, so it must not
    modify what it is handed. On a configured app nothing is written to the local disk: the
    container's copy is a throwaway clone, and keeping it in step would only dirty a developer's
    working tree for no gain. The in-process cache is what keeps this container current.
    """
    if not github_sync.configured():
        updated = op(_load_local(path, default))
        _save_local(path, updated)
        return updated

    updated = github_sync.mutate(_repo_path(path), op, message, default)
    with _cache_lock:
        _cache[path] = (updated, time.time())
    return updated


def last_load_error():
    """Which files are being served stale and why, or None if everything is live."""
    with _cache_lock:
        if not _stale:
            return None
        names = ", ".join(sorted(os.path.basename(p) for p in _stale))
        newest_reason = max(_stale.values(), key=lambda v: v[1])[0]
        return f"{names} - {newest_reason}"


def storage_status():
    """(mode, detail) for the UI: how this app is storing data right now."""
    if not github_sync.configured():
        return "local", f"Local files under {DATA_DIR}"
    error = last_load_error()
    if error:
        return "degraded", error
    return "remote", github_sync.target()


def invalidate_cache():
    with _cache_lock:
        _cache.clear()
        _stale.clear()


# ---------------------------------------------------------------- reads

def match_sort_key(match_id):
    """Numeric ordering for Deadlock match IDs.

    The game assigns these sequentially, so numeric order is chronological order. They're
    stored as strings, and sorting them as strings breaks the moment an ID gains a digit:
    '100905275' sorts below '99935534' lexically, burying the newest match at the bottom
    of every "recent" list. Non-numeric IDs sort last rather than raising.
    """
    s = str(match_id)
    return (0, int(s)) if s.isdigit() else (1, 0)


def load_matches():
    """Matches in chronological order (ascending match ID), under current display names.

    Sorting here rather than at each call site means everything downstream that treats list
    position as time - the rolling draft-participation timeline especially - gets a real
    chronological axis for free.

    Resolving names here is the same bargain. Each player row stores a `player_key` - the
    person - and the nickname that was typed on the night. Names are looked up from the key on
    the way out, so someone who changes their alias changes it in one record and every page
    follows: stats, chemistry, leaderboards, rank history. Nothing downstream knows this
    happened, which is why none of it had to change.

    A row with no key, or a key no longer in players.json, keeps the nickname it was stored
    with. Losing a player's name should degrade to the old behaviour, not to a blank column.
    """
    matches = _load(MATCHES_FILE, [])
    matches = sorted(matches, key=lambda m: match_sort_key(m.get("match_id")))
    names = display_names()
    for match in matches:
        for row in match.get("players", []):
            row["player"] = names.get(row.get("player_key"), row.get("player"))
    return matches


def load_players():
    """The player store, keyed by player_key: a Steam account id, or a nickname until we see one."""
    return _load(PLAYERS_FILE, {})


def display_names(players=None):
    """{player_key: current display name}."""
    players = players if players is not None else load_players()
    return {key: rec.get("display_name", key) for key, rec in players.items()}


def players_by_name(players=None):
    """{display name: record}, for the pages that present players as names rather than keys.

    Two records can only collide here if two people are genuinely using the same display name,
    which is a thing to fix in the data rather than to paper over, so the later key wins and
    the duplicate is visible on the page.
    """
    players = players if players is not None else load_players()
    return {rec.get("display_name", key): {**rec, "player_key": key}
            for key, rec in players.items()}


def key_for_account(account_id, players=None):
    """The player who owns a Steam account id, or None if we have never seen it.

    Checks every id a player owns, not just the primary: eight of our regulars have an alt,
    and a game played on one is still a game played by them.
    """
    players = players if players is not None else load_players()
    account_id = str(account_id)
    for key, rec in players.items():
        if account_id in rec.get("account_ids", []):
            return key
    return None


def load_heroes():
    return _load(HEROES_FILE, [])


def load_ranks():
    return _load(RANKS_FILE, [])


# The two below are vendored assets rather than user data: they are refreshed by
# `fetch_deadlock_assets.py`, versioned alongside the code that reads them, and never written
# by the app. Reading them locally keeps them in step with the deployed release, and saves two
# API round trips on every cold container.
def load_rank_tiers():
    return _load_local(RANK_TIERS_FILE, [])


def load_hero_visuals():
    """Per-hero official color + icon filenames, vendored by fetch_deadlock_assets.py."""
    return _load_local(HERO_VISUALS_FILE, {})


def hero_portrait_path(portrait_name):
    """Absolute path to a hero's portrait, or None if it has not been fetched."""
    if not portrait_name:
        return None
    path = os.path.join(HERO_PORTRAIT_DIR, portrait_name)
    return path if os.path.exists(path) else None


def save_matches(matches):
    """Overwrite matches.json on the local disk. Offline maintenance scripts only.

    This is the whole-file write the app deliberately no longer does: it cannot detect a
    concurrent edit, so against live data it would drop whatever landed while the script was
    working. `backfill_match_dates.py` uses it correctly - offline, against a checkout, with the
    result reviewed and committed by hand.

    It refuses to run when sync is configured rather than quietly writing the local fallback,
    because that failure looks exactly like success: the script prints "Filled 35" and the app
    never sees any of it. Unset the secrets to work on a checkout, or write through
    `add_match` / `update_match` so the edit reaches the data branch.
    """
    if github_sync.configured():
        raise RuntimeError(
            f"save_matches() writes the local fallback copy, but this checkout is configured to "
            f"sync with {github_sync.target()} - so the change would not reach the app and the "
            f"script would report success anyway. Either move .streamlit/secrets.toml aside to "
            f"work against local files, or use add_match()/update_match(), which write through "
            f"to the data branch."
        )
    _save_local(MATCHES_FILE, matches)


# ---------------------------------------------------------------- writes

def add_match(match_dict):
    """Append a match. Raises ValueError if the ID is already taken, SyncError if it didn't save."""
    match_id = str(match_dict["match_id"])

    def op(matches):
        if any(str(m.get("match_id")) == match_id for m in matches):
            raise ValueError(f"Match {match_id} already exists.")
        return list(matches) + [match_dict]

    _mutate(MATCHES_FILE, op, f"Add match {match_id}", [])
    return True


def update_match(match_id, new_match_dict):
    """Replace a match by ID. Returns False if no such match; raises SyncError if it didn't save."""
    match_id = str(match_id)
    found = {"hit": False}

    def op(matches):
        found["hit"] = False  # reset: a conflict retry re-runs this against newer data
        out = []
        for m in matches:
            if str(m.get("match_id")) == match_id:
                found["hit"] = True
                out.append(new_match_dict)
            else:
                out.append(m)
        return out

    _mutate(MATCHES_FILE, op, f"Update match {match_id}", [])
    return found["hit"]


def delete_match(match_id):
    """Remove a match by ID. Returns False if no such match; raises SyncError if it didn't save."""
    match_id = str(match_id)
    found = {"hit": False}

    def op(matches):
        kept = [m for m in matches if str(m.get("match_id")) != match_id]
        found["hit"] = len(kept) != len(matches)
        return kept

    _mutate(MATCHES_FILE, op, f"Delete match {match_id}", [])
    return found["hit"]


def add_player(name, notes="", account_id=None):
    """Register a player. Returns False if already known; raises SyncError if it didn't save.

    Keyed by `account_id` when the caller has one - the match importer does, since it learns a
    person's account before it ever learns their name - and by nickname when it does not. A
    nickname key is a placeholder: it is what someone typed, and it is replaced by the account
    id the first time that person shows up in an imported match.
    """
    key = str(account_id) if account_id else name
    added = {"hit": False}

    def op(players):
        taken = key in players or any(
            rec.get("display_name") == name for rec in players.values()
        )
        added["hit"] = not taken
        if not added["hit"]:
            return players
        record = {
            "display_name": name,
            "account_ids": [str(account_id)] if account_id else [],
            "aliases": [name],
            "notes": notes,
            "reported_rank": None,
        }
        return {**players, key: record}

    _mutate(PLAYERS_FILE, op, f"Add player {name}", {})
    return added["hit"]


def rename_player(player_key, new_name):
    """Change a player's display name. Returns False if the key is unknown.

    The whole point of the re-keying: this touches one field. Every match row, rank entry,
    leaderboard position and chemistry pair follows from it, because none of them ever stored
    the name in the first place. The old name is kept as an alias so it stays searchable and so
    nobody wonders later who a historical row belonged to.
    """
    found = {"hit": False}

    def op(players):
        found["hit"] = player_key in players
        if not found["hit"]:
            return players
        record = dict(players[player_key])
        old = record.get("display_name")
        record["display_name"] = new_name
        record["aliases"] = sorted(set(record.get("aliases", [])) | {old, new_name} - {None})
        return {**players, player_key: record}

    _mutate(PLAYERS_FILE, op, f"Rename {player_key} to {new_name}", {})
    return found["hit"]


def link_account(player_key, account_id):
    """Attach a Steam account id to a player, re-keying them if they had no id before.

    A player first seen in a match the API does not have is keyed by nickname. When they later
    turn up in an imported match we finally learn their account, and this is where the
    placeholder key is retired - which means rewriting the match and rank rows that point at
    it, since a key is only useful while everything agrees on it.
    """
    account_id = str(account_id)
    new_key = account_id if not str(player_key).isdigit() else player_key

    def op(players):
        if player_key not in players:
            return players
        record = dict(players[player_key])
        if account_id not in record.get("account_ids", []):
            record["account_ids"] = list(record.get("account_ids", [])) + [account_id]
        out = {k: v for k, v in players.items() if k != player_key}
        out[new_key] = record
        return out

    _mutate(PLAYERS_FILE, op, f"Link account {account_id} to {player_key}", {})

    if new_key != player_key:
        _repoint(player_key, new_key)
    return new_key


def _repoint(old_key, new_key):
    """Move every match row and rank entry from one player_key to another."""
    def move_matches(matches):
        out = []
        for match in matches:
            rows = [{**r, "player_key": new_key} if r.get("player_key") == old_key else r
                    for r in match.get("players", [])]
            out.append({**match, "players": rows})
        return out

    def move_ranks(ranks):
        return [{**r, "player_key": new_key} if r.get("player_key") == old_key else r
                for r in ranks]

    _mutate(MATCHES_FILE, move_matches, f"Re-key {old_key} as {new_key}", [])
    _mutate(RANKS_FILE, move_ranks, f"Re-key {old_key} as {new_key}", [])


def add_hero(name):
    """Register a hero. Returns False if already known; raises SyncError if it didn't save."""
    added = {"hit": False}

    def op(heroes):
        added["hit"] = name not in heroes
        if not added["hit"]:
            return heroes
        return sorted(set(heroes) | {name})

    _mutate(HEROES_FILE, op, f"Add hero {name}", [])
    return added["hit"]


def add_rank_entry(player_key, rank, entry_date=None, display_name=None):
    """Append a rank observation against a player_key. Raises SyncError if it didn't save.

    The name is written alongside the key for the same reason match rows keep theirs: it is
    what the person was called when the rank was logged, and it makes the raw file readable.
    Nothing reads it back.
    """
    entry = {
        "player_key": player_key,
        "player": display_name or player_key,
        "rank": rank,
        "date": entry_date or str(date.today()),
    }
    _mutate(RANKS_FILE, lambda ranks: list(ranks) + [entry], f"Rank {entry['player']} as {rank}", [])
    return True


# ---------------------------------------------------------------- derived

def current_rank(player_key, ranks=None):
    """Most recent rank entry for a player, or None."""
    ranks = ranks if ranks is not None else load_ranks()
    entries = [r for r in ranks if r.get("player_key", r.get("player")) == player_key]
    if not entries:
        return None

    # The seeded rows are dated 'import' rather than a real date, and they are the oldest thing
    # we have on anyone - so they sort first and every real date sorts after. Sorting them last
    # instead pins a player to their seeded rank forever: the newest entry is read off the end,
    # and 'import' would always be the end. It has never shown up because no one has logged a
    # rank for a seeded player yet, and all 42 of them are seeded.
    def sort_key(r):
        return (r["date"] != "import", r["date"])

    entries.sort(key=sort_key)
    return entries[-1]["rank"]


def next_match_id(matches=None):
    matches = matches if matches is not None else load_matches()
    ids = [int(m["match_id"]) for m in matches if str(m["match_id"]).isdigit()]
    return str(max(ids) + 1) if ids else "1"
