"""One-off import: convert the legacy Google-Sheet CSV exports into the app's JSON data store."""
import csv
import json
import os

UPLOAD_DIR = "/mnt/user-data/uploads"
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT_DIR, exist_ok=True)

RANK_TIERS = ["Initiate", "Seeker", "Alchemist", "Arcanist", "Ritualist",
              "Emissary", "Archon", "Oracle", "Phantom", "Ascendant", "Eternus"]


def to_float(v, default=None):
    v = (v or "").strip().replace("%", "")
    if v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def to_bool(v):
    return (v or "").strip().upper() == "TRUE"


# ---------- lists.csv: valid players / heroes / ranks ----------
players_set, heroes_set = set(), set()
with open(os.path.join(UPLOAD_DIR, "Zack_deadlock_PUG_stats_-_lists.csv"), encoding="utf-8-sig") as fh:
    for row in csv.reader(fh):
        if len(row) > 0 and row[0].strip():
            players_set.add(row[0].strip())
        if len(row) > 1 and row[1].strip():
            heroes_set.add(row[1].strip())

# ---------- match_log.csv: source of truth for all match/player-game rows ----------
matches = {}
with open(os.path.join(UPLOAD_DIR, "Zack_deadlock_PUG_stats_-_match_log.csv"), encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        mid = row["Match ID"].strip()
        if not mid:
            continue
        m = matches.setdefault(mid, {
            "match_id": mid, "date": None, "game_length": row["Game Length"].strip(),
            "players": [], "bans": [], "first_picks": [],
        })
        slot = int(to_float(row["Draft Slot (for stats, ignore)"], 0)) or None
        m["players"].append({
            "team": row["Team"].strip(),
            "player": row["Player (dropdown)"].strip(),
            "hero": row["Hero (dropdown)"].strip(),
            "win": to_bool(row["Win?"]),
            "mvp": to_bool(row["MVP? (in-game)"]),
            "key_player": to_bool(row["Key player? (in-game)"]),
            "kp_pct": to_float(row["KP (%)"]),
            "kills": int(to_float(row["Kills"], 0)),
            "deaths": int(to_float(row["Deaths"], 0)),
            "assists": int(to_float(row["Assists"], 0)),
            "souls_k": to_float(row["Souls (k)"]),
            "plr_damage_k": to_float(row["PLR Damage (k)"]),
            "obj_damage_k": to_float(row["OBJ Damage (k)"]),
            "healing_k": to_float(row["Healing (k)"]),
            "draft_slot": slot,
        })
        ban = row["Bans"].strip()
        if ban:
            m["bans"].append(ban)
        fp = row["First Picks"].strip()
        if fp:
            m["first_picks"].append(fp)
        players_set.add(row["Player (dropdown)"].strip())
        heroes_set.add(row["Hero (dropdown)"].strip())

matches_list = sorted(matches.values(), key=lambda m: m["match_id"])
# drop incomplete rows (blank filler)
matches_list = [m for m in matches_list if m["players"] and all(p["player"] and p["hero"] for p in m["players"])]

# ---------- player_summary.csv: current reported rank + notes ----------
players_info = {p: {"notes": "", "reported_rank": None} for p in sorted(players_set) if p}
with open(os.path.join(UPLOAD_DIR, "Zack_deadlock_PUG_stats_-_player_summary.csv"), encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        name = row["Player Name"].strip()
        if not name:
            continue
        players_info.setdefault(name, {"notes": "", "reported_rank": None})
        rank = row["Reported Rank"].strip()
        players_info[name]["reported_rank"] = rank or None
        players_info[name]["notes"] = row.get("Notes and Comments", "").strip()

# ---------- build rank history seed (one entry per player, from reported rank) ----------
rank_history = []
for name, info in players_info.items():
    if info["reported_rank"]:
        rank_history.append({"player": name, "rank": info["reported_rank"], "date": "import"})

heroes_list = sorted(h for h in heroes_set if h)

with open(os.path.join(OUT_DIR, "matches.json"), "w") as f:
    json.dump(matches_list, f, indent=2)
with open(os.path.join(OUT_DIR, "players.json"), "w") as f:
    json.dump(players_info, f, indent=2)
with open(os.path.join(OUT_DIR, "heroes.json"), "w") as f:
    json.dump(heroes_list, f, indent=2)
with open(os.path.join(OUT_DIR, "ranks.json"), "w") as f:
    json.dump(rank_history, f, indent=2)
with open(os.path.join(OUT_DIR, "rank_tiers.json"), "w") as f:
    json.dump(RANK_TIERS, f, indent=2)

print(f"matches: {len(matches_list)}")
print(f"players: {len(players_info)}")
print(f"heroes: {len(heroes_list)}")
print(f"rank history seed rows: {len(rank_history)}")
