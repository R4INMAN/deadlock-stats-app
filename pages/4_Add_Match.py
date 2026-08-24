import streamlit as st
from utils import data_io
from utils.auth import require_edit_access

if not require_edit_access():
    st.stop()

st.set_page_config(page_title="Add Match", page_icon="➕", layout="wide")
st.title("➕ Add Match")

players_dict = data_io.load_players()
heroes = data_io.load_heroes()
matches = data_io.load_matches()
player_names = sorted(players_dict.keys())

if len(player_names) < 12:
    st.warning("You need at least 12 players logged (6 per side) before adding a match. Use **Add Player / Hero** first.")
if len(heroes) < 12:
    st.warning("You need at least 12 heroes logged before adding a match. Use **Add Player / Hero** first.")

TEAM_A, TEAM_B = "Hidden King", "Archmother"

st.caption("Enter all 12 players' stats, then bans, first picks, MVP, and Key Players at the bottom.")

with st.form("add_match_form", clear_on_submit=False):
    match_id = st.text_input("Match ID", value="")
    game_length = st.text_input("Game length (MM:SS)", value="30:00")
    winning_side = st.radio("Winning side", [TEAM_A, TEAM_B], horizontal=True)

    all_rows = []
    for team in (TEAM_A, TEAM_B):
        st.subheader(team)
        cols = st.columns(6)
        for i in range(6):
            with cols[i]:
                st.markdown(f"**Slot {i+1}**")
                p = st.selectbox("Player", player_names, key=f"{team}_player_{i}")
                h = st.selectbox("Hero", heroes, key=f"{team}_hero_{i}")
                k = st.number_input("Kills", min_value=0, step=1, key=f"{team}_k_{i}")
                d = st.number_input("Deaths", min_value=0, step=1, key=f"{team}_d_{i}")
                a = st.number_input("Assists", min_value=0, step=1, key=f"{team}_a_{i}")
                souls = st.number_input("Souls (k)", min_value=0.0, step=1.0, key=f"{team}_souls_{i}")
                plr = st.number_input("Plyr Dmg (k)", min_value=0.0, step=1.0, key=f"{team}_plr_{i}")
                obj = st.number_input("Obj Dmg (k)", min_value=0.0, step=1.0, key=f"{team}_obj_{i}")
                heal = st.number_input("Healing (k)", min_value=0.0, step=1.0, key=f"{team}_heal_{i}")
                all_rows.append({"team": team, "player": p, "hero": h, "kills": k, "deaths": d,
                                  "assists": a, "souls_k": souls, "plr_damage_k": plr,
                                  "obj_damage_k": obj, "healing_k": heal})

    st.divider()
    c1, c2 = st.columns(2)
    bans = c1.multiselect("Bans", heroes)
    first_picks = c2.multiselect("First picks (draft order not tracked)", heroes)

    all_player_names_in_match = [r["player"] for r in all_rows]
    mvp = st.selectbox("MVP", ["None"] + player_names)
    key_players = st.multiselect("Key Players (pick exactly 2)", player_names)

    submitted = st.form_submit_button("Save match")

    if submitted:
        errors = []
        if not match_id.strip():
            errors.append("Match ID is required")
        if mvp != "None" and mvp not in all_player_names_in_match:
            errors.append(f"{mvp} (MVP) isn't one of the 12 players in this match.")
        if any(kp not in all_player_names_in_match for kp in key_players):
            errors.append("All Key Players must be players in this match.")
        if len(set(all_player_names_in_match)) != 12:
            errors.append("Each of the 12 slots must have a unique player.")
        if any(m["match_id"] == match_id for m in matches):
            errors.append(f"Match ID {match_id} already exists.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            team_kills = {TEAM_A: sum(r["kills"] for r in all_rows if r["team"] == TEAM_A),
                          TEAM_B: sum(r["kills"] for r in all_rows if r["team"] == TEAM_B)}
            players_out = []
            for r in all_rows:
                tk = team_kills[r["team"]] or 1
                kp = round((r["kills"] + r["assists"]) / tk * 100, 2)
                players_out.append({
                    "team": r["team"], "player": r["player"], "hero": r["hero"],
                    "win": r["team"] == winning_side,
                    "mvp": r["player"] == mvp,
                    "key_player": r["player"] in key_players,
                    "kp_pct": kp,
                    "kills": r["kills"], "deaths": r["deaths"], "assists": r["assists"],
                    "souls_k": r["souls_k"], "plr_damage_k": r["plr_damage_k"],
                    "obj_damage_k": r["obj_damage_k"], "healing_k": r["healing_k"],
                    "draft_slot": None,
                })
            new_match = {
                "match_id": match_id, "date": str(st.session_state.get("_today", "")) or None,
                "game_length": game_length, "players": players_out,
                "bans": bans, "first_picks": first_picks,
            }
            import datetime
            new_match["date"] = str(datetime.date.today())
            data_io.add_match(new_match)
            st.success(f"Match {match_id} saved!")
            st.balloons()
