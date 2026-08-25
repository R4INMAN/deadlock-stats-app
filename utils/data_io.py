import json
import os
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")
HEROES_FILE = os.path.join(DATA_DIR, "heroes.json")
RANKS_FILE = os.path.join(DATA_DIR, "ranks.json")
RANK_TIERS_FILE = os.path.join(DATA_DIR, "rank_tiers.json")


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_matches():
    return _load(MATCHES_FILE, [])


def save_matches(matches):
    _save(MATCHES_FILE, matches)


def load_players():
    return _load(PLAYERS_FILE, {})


def save_players(players):
    _save(PLAYERS_FILE, players)


def load_heroes():
    return _load(HEROES_FILE, [])


def save_heroes(heroes):
    _save(HEROES_FILE, sorted(set(heroes)))


def load_ranks():
    return _load(RANKS_FILE, [])


def save_ranks(ranks):
    _save(RANKS_FILE, ranks)


def load_rank_tiers():
    return _load(RANK_TIERS_FILE, [])


def add_match(match_dict):
    matches = load_matches()
    matches.append(match_dict)
    save_matches(matches)
    
def update_match(match_id, new_match_dict):
    matches = load_matches()
    for i, m in enumerate(matches):
        if m["match_id"] == match_id:
            matches[i] = new_match_dict
            save_matches(matches)
            return True
    return False


def delete_match(match_id):
    matches = load_matches()
    new_matches = [m for m in matches if m["match_id"] != match_id]
    if len(new_matches) != len(matches):
        save_matches(new_matches)
        return True
    return False

def add_player(name, notes=""):
    players = load_players()
    if name not in players:
        players[name] = {"notes": notes, "reported_rank": None}
        save_players(players)
        return True
    return False


def add_hero(name):
    heroes = load_heroes()
    if name not in heroes:
        heroes.append(name)
        save_heroes(heroes)
        return True
    return False


def add_rank_entry(player, rank, entry_date=None):
    ranks = load_ranks()
    ranks.append({"player": player, "rank": rank, "date": entry_date or str(date.today())})
    save_ranks(ranks)


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
