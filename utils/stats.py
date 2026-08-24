import pandas as pd


def _game_length_minutes(s):
    if not s or ":" not in str(s):
        return None
    try:
        mm, ss = str(s).split(":")
        return int(mm) + int(ss) / 60
    except ValueError:
        return None


def matches_to_rows_df(matches):
    """Flatten matches -> one row per player-per-game, with match-level fields joined in."""
    rows = []
    for m in matches:
        length_min = _game_length_minutes(m.get("game_length"))
        for p in m["players"]:
            row = dict(p)
            row["match_id"] = m["match_id"]
            row["date"] = m.get("date")
            row["game_length"] = m.get("game_length")
            row["game_length_min"] = length_min
            row["souls_per_min"] = (p["souls_k"] / length_min) if (p.get("souls_k") is not None and length_min) else None
            row["obj_dmg_per_min"] = (p["obj_damage_k"] / length_min) if (p.get("obj_damage_k") is not None and length_min) else None
            rows.append(row)
    return pd.DataFrame(rows)


def matches_summary_df(matches):
    """One row per match: match_id, length, winning side, mvp(s), key players."""
    rows = []
    for m in matches:
        players = m["players"]
        winners = [p["team"] for p in players if p["win"]]
        win_side = winners[0] if winners else None
        mvps = [p["player"] for p in players if p.get("mvp")]
        keys = [p["player"] for p in players if p.get("key_player")]
        rows.append({
            "match_id": m["match_id"],
            "date": m.get("date"),
            "game_length": m.get("game_length"),
            "win_side": win_side,
            "mvps": ", ".join(mvps),
            "key_players": ", ".join(keys),
            "num_players": len(players),
        })
    return pd.DataFrame(rows)


def side_win_rates(df):
    if df.empty:
        return pd.DataFrame(columns=["team", "games", "wins", "win_rate"])
    g = df.groupby("team").agg(games=("win", "size"), wins=("win", "sum")).reset_index()
    g["win_rate"] = g["wins"] / g["games"]
    return g.sort_values("team")


def player_summary_table(df):
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("player").agg(
        games=("win", "size"),
        wins=("win", "sum"),
        avg_kp_pct=("kp_pct", "mean"),
        avg_souls_per_min=("souls_per_min", "mean"),
        avg_obj_dmg_per_min=("obj_dmg_per_min", "mean"),
        avg_kills=("kills", "mean"),
        avg_deaths=("deaths", "mean"),
        avg_assists=("assists", "mean"),
        mvp_count=("mvp", "sum"),
        key_player_count=("key_player", "sum"),
        hero_variety=("hero", "nunique"),
    ).reset_index()
    g["win_rate"] = g["wins"] / g["games"]
    g["award_rate"] = (g["mvp_count"] + g["key_player_count"]) / g["games"]
    most_played = df.groupby(["player", "hero"]).size().reset_index(name="n")
    most_played = most_played.sort_values("n", ascending=False).drop_duplicates("player")
    most_played = most_played.rename(columns={"hero": "most_played_hero", "n": "most_played_hero_games"})
    g = g.merge(most_played[["player", "most_played_hero", "most_played_hero_games"]], on="player", how="left")
    return g.sort_values("win_rate", ascending=False)


def player_detail(df, player, total_matches):
    pdf = df[df["player"] == player]
    if pdf.empty:
        return None
    games = len(pdf)
    hero_breakdown = pdf.groupby("hero").agg(
        games=("win", "size"), wins=("win", "sum"),
        avg_kp_pct=("kp_pct", "mean"), mvp_count=("mvp", "sum"), key_player_count=("key_player", "sum"),
    ).reset_index()
    hero_breakdown["win_rate"] = hero_breakdown["wins"] / hero_breakdown["games"]
    hero_breakdown = hero_breakdown.sort_values("games", ascending=False)

    side_breakdown = pdf.groupby("team").agg(games=("win", "size"), wins=("win", "sum")).reset_index()
    side_breakdown["win_rate"] = side_breakdown["wins"] / side_breakdown["games"]

    return {
        "games": games,
        "win_rate": pdf["win"].sum() / games,
        "avg_kp_pct": pdf["kp_pct"].mean(),
        "avg_souls_per_min": pdf["souls_per_min"].mean(),
        "avg_obj_dmg_per_min": pdf["obj_dmg_per_min"].mean(),
        "avg_kills": pdf["kills"].mean(),
        "avg_deaths": pdf["deaths"].mean(),
        "avg_assists": pdf["assists"].mean(),
        "mvp_count": int(pdf["mvp"].sum()),
        "key_player_count": int(pdf["key_player"].sum()),
        "hero_variety": pdf["hero"].nunique(),
        "hero_breakdown": hero_breakdown,
        "side_breakdown": side_breakdown,
        "match_ids": pdf["match_id"].tolist(),
    }


def ban_first_pick_counts(matches):
    """Count each hero once per match it was banned / first-picked in (match-level lists)."""
    ban_counts, fp_counts = {}, {}
    for m in matches:
        for hero in set(m.get("bans", [])):
            ban_counts[hero] = ban_counts.get(hero, 0) + 1
        for hero in set(m.get("first_picks", [])):
            fp_counts[hero] = fp_counts.get(hero, 0) + 1
    return ban_counts, fp_counts


def hero_summary_table(df, total_matches, matches=None, heroes_list=None):
    if total_matches == 0:
        return pd.DataFrame()
    ban_counts, fp_counts = ban_first_pick_counts(matches or [])

    all_heroes = set(df["hero"].dropna().unique())
    if heroes_list:
        all_heroes |= set(heroes_list)

    rows = []
    for hero in sorted(all_heroes):
        hdf = df[df["hero"] == hero]
        games = len(hdf)
        wins = hdf["win"].sum() if games else 0
        top_player = None
        top_player_games = 0
        if games:
            counts = hdf["player"].value_counts()
            top_player = counts.index[0]
            top_player_games = int(counts.iloc[0])
        rows.append({
            "hero": hero,
            "games": games,
            "win_rate": (wins / games) if games else None,
            "pick_rate": games / total_matches,
            "ban_rate": (ban_counts.get(hero, 0) / total_matches),
            "first_pick_rate": (fp_counts.get(hero, 0) / total_matches),
            "mvp_count": int(hdf["mvp"].sum()) if games else 0,
            "key_player_count": int(hdf["key_player"].sum()) if games else 0,
            "top_player": top_player,
            "top_player_games": top_player_games,
            "avg_kp_pct": hdf["kp_pct"].mean() if games else None,
        })
    return pd.DataFrame(rows).sort_values("games", ascending=False)


def hero_detail(df, hero, total_matches):
    hdf = df[df["hero"] == hero]
    player_breakdown = hdf.groupby("player").agg(
        games=("win", "size"), wins=("win", "sum"), avg_kp_pct=("kp_pct", "mean"),
    ).reset_index()
    if not player_breakdown.empty:
        player_breakdown["win_rate"] = player_breakdown["wins"] / player_breakdown["games"]
        player_breakdown = player_breakdown.sort_values("games", ascending=False)
    return {
        "games": len(hdf),
        "win_rate": hdf["win"].mean() if len(hdf) else None,
        "pick_rate": len(hdf) / total_matches if total_matches else None,
        "player_breakdown": player_breakdown,
    }
