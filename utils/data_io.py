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

_cache = {}
_cache_lock = threading.Lock()
_last_load_error = None


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
    GitHub outage degrades the app to stale-but-readable rather than blank. `last_load_error`
    exposes that state for the UI to say so out loud - silently showing stale data is how you
    get someone re-entering a match that already exists.
    """
    global _last_load_error

    if not github_sync.configured():
        return _load_local(path, default)

    now = time.time()
    with _cache_lock:
        cached = _cache.get(path)
        if cached and now - cached[1] < CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[0])

    try:
        data, _ = github_sync.read_json(_repo_path(path), default)
    except github_sync.SyncError as exc:
        _last_load_error = str(exc)
        return _load_local(path, default)

    _last_load_error = None
    with _cache_lock:
        _cache[path] = (data, now)
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
    """Why the most recent remote read fell back to the committed copy, or None."""
    return _last_load_error


def storage_status():
    """(mode, detail) for the UI: how this app is storing data right now."""
    if not github_sync.configured():
        return "local", f"Local files under {DATA_DIR}"
    if _last_load_error:
        return "degraded", _last_load_error
    return "remote", github_sync.target()


def invalidate_cache():
    with _cache_lock:
        _cache.clear()


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
    """Matches in chronological order (ascending match ID).

    Sorting here rather than at each call site means everything downstream that treats list
    position as time - the rolling draft-participation timeline especially - gets a real
    chronological axis for free.
    """
    matches = _load(MATCHES_FILE, [])
    return sorted(matches, key=lambda m: match_sort_key(m.get("match_id")))


def load_players():
    return _load(PLAYERS_FILE, {})


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

    This is the whole-file write that the app deliberately no longer does - it cannot detect a
    concurrent edit, so running it against live data would silently drop whatever landed while
    the script was working. `backfill_match_dates.py` uses it correctly: offline, against a
    checkout, with the result reviewed and committed by hand.
    """
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


def add_player(name, notes=""):
    """Register a player. Returns False if already known; raises SyncError if it didn't save."""
    added = {"hit": False}

    def op(players):
        added["hit"] = name not in players
        if not added["hit"]:
            return players
        return {**players, name: {"notes": notes, "reported_rank": None}}

    _mutate(PLAYERS_FILE, op, f"Add player {name}", {})
    return added["hit"]


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


def add_rank_entry(player, rank, entry_date=None):
    """Append a rank observation. Raises SyncError if it didn't save."""
    entry = {"player": player, "rank": rank, "date": entry_date or str(date.today())}
    _mutate(RANKS_FILE, lambda ranks: list(ranks) + [entry], f"Rank {player} as {rank}", [])
    return True


# ---------------------------------------------------------------- derived

def current_rank(player, ranks=None):
    """Most recent rank entry for a player, or None."""
    ranks = ranks if ranks is not None else load_ranks()
    entries = [r for r in ranks if r["player"] == player]
    if not entries:
        return None

    # 'import' sorts first alphabetically before real dates in most cases; fall back safely
    def sort_key(r):
        return (r["date"] == "import", r["date"])

    entries.sort(key=sort_key)
    return entries[-1]["rank"]


def next_match_id(matches=None):
    matches = matches if matches is not None else load_matches()
    ids = [int(m["match_id"]) for m in matches if str(m["match_id"]).isdigit()]
    return str(max(ids) + 1) if ids else "1"
