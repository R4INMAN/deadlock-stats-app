import datetime
import streamlit as st
from utils import data_io, dates, ui
from utils.auth import require_edit_access

st.set_page_config(page_title="Add Match", page_icon="assets/ui/puddle_punch.png", layout="wide")

if not require_edit_access():
    st.stop()

ui.page_header("Match Management", "Log a new game, or fix one that went in wrong.")

players_dict = data_io.load_players()
heroes = data_io.load_heroes()
matches = data_io.load_matches()
player_names = sorted(players_dict.keys())

TEAM_A, TEAM_B = "Hidden King", "Archmother"

mode = st.selectbox("Mode", ["Add Match", "Edit Match", "Delete Match"])

# ---------------- DELETE ----------------
if mode == "Delete Match":
    if not matches:
        st.info("No matches to delete.")
        st.stop()
    match_ids = [m["match_id"] for m in matches][::-1]  # chronological from load_matches()
    chosen_id = st.selectbox("Select match to delete", match_ids)
    match = next(m for m in matches if m["match_id"] == chosen_id)
    st.write(f"**Length:** {match.get('game_length', 'n/a')}")
    winners = [p["team"] for p in match["players"] if p["win"]]
    st.write(f"**Winner:** {winners[0] if winners else 'n/a'}")
    st.dataframe([{"Player": p["player"], "Hero": p["hero"], "Team": p["team"]} for p in match["players"]],
                 use_container_width=True, hide_index=True)

    confirm = st.checkbox(f"I'm sure I want to permanently delete match {chosen_id}")
    if st.button("Delete match", disabled=not confirm, type="primary"):
        data_io.delete_match(chosen_id)
        st.success(f"Match {chosen_id} deleted.")
        st.rerun()
    st.stop()

# ---------------- ADD / EDIT (shared form) ----------------
editing = mode == "Edit Match"
existing_match = None

if editing:
    if not matches:
        st.info("No matches to edit.")
        st.stop()
    match_ids = [m["match_id"] for m in matches][::-1]  # chronological from load_matches()
    edit_id = st.selectbox("Select match to edit", match_ids)
    existing_match = next(m for m in matches if m["match_id"] == edit_id)

if len(player_names) < 12:
    st.warning("You need at least 12 players logged (6 per side) before adding a match. Use **Add Player / Hero** first.")
if len(heroes) < 12:
    st.warning("You need at least 12 heroes logged before adding a match. Use **Add Player / Hero** first.")

st.caption("Enter all 12 players' stats, then bans, first picks, MVP, and Key Players at the bottom.")


def existing_player_row(team, slot_idx):
    if not existing_match:
        return None
    team_rows = [p for p in existing_match["players"] if p["team"] == team]
    return team_rows[slot_idx] if slot_idx < len(team_rows) else None


def idx_of(lst, value, default=0):
    try:
        return lst.index(value)
    except (ValueError, TypeError):
        return default


with st.form("match_form", clear_on_submit=False):
    if editing:
        match_id = existing_match["match_id"]
        st.text_input("Match ID", value=match_id, disabled=True)
    else:
        match_id = st.text_input("Match ID", value="")

    # Defaults to tonight where the group plays, not where the server runs - but it stays
    # editable, because a match logged the morning after is not a match played that morning.
    # An existing match the backfill has not reached yet opens empty rather than defaulting to
    # today, so editing an old match for some unrelated reason cannot stamp it with this date.
    if existing_match:
        stored = existing_match.get("date")
        default_date = datetime.date.fromisoformat(stored) if stored else None
    else:
        default_date = dates.today()
    match_date = st.date_input("Date played", value=default_date,
                               help="The night the match was played.")

    default_length = existing_match["game_length"] if existing_match else "30:00"
    game_length = st.text_input("Game length (MM:SS)", value=default_length)

    default_winner = TEAM_A
    if existing_match:
        winners = [p["team"] for p in existing_match["players"] if p["win"]]
        if winners:
            default_winner = winners[0]
    winning_side = st.radio("Winning side", [TEAM_A, TEAM_B], horizontal=True,
                             index=[TEAM_A, TEAM_B].index(default_winner))

    all_rows = []
    for team in (TEAM_A, TEAM_B):
        st.subheader(team)
        team_existing = [existing_player_row(team, i) for i in range(6)]

        def field_row(label, key_prefix, widget_fn):
            """Render one field across all 6 slots as a single row, for horizontal tabbing."""
            st.markdown(f"**{label}**")
            cols = st.columns(6)
            values = []
            for i in range(6):
                with cols[i]:
                    values.append(widget_fn(i, cols[i]))
            return values

        players_sel = field_row("Player", "player", lambda i, c: st.selectbox(
            "Player", player_names,
            index=idx_of(player_names, team_existing[i]["player"] if team_existing[i] else None),
            key=f"{team}_player_{i}", label_visibility="collapsed"))

        heroes_sel = field_row("Hero", "hero", lambda i, c: st.selectbox(
            "Hero", heroes,
            index=idx_of(heroes, team_existing[i]["hero"] if team_existing[i] else None),
            key=f"{team}_hero_{i}", label_visibility="collapsed"))

        slots_sel = field_row("Draft Slot", "slot", lambda i, c: st.number_input(
            "Draft Slot", min_value=1, max_value=12, step=1,
            value=(team_existing[i]["draft_slot"] if team_existing[i] and team_existing[i].get("draft_slot") else
                   (i + 1 if team == TEAM_A else i + 7)),
            key=f"{team}_slot_{i}", label_visibility="collapsed"))

        kills_sel = field_row("Kills", "k", lambda i, c: st.number_input(
            "Kills", min_value=0, step=1,
            value=team_existing[i]["kills"] if team_existing[i] else 0,
            key=f"{team}_k_{i}", label_visibility="collapsed"))

        deaths_sel = field_row("Deaths", "d", lambda i, c: st.number_input(
            "Deaths", min_value=0, step=1,
            value=team_existing[i]["deaths"] if team_existing[i] else 0,
            key=f"{team}_d_{i}", label_visibility="collapsed"))

        assists_sel = field_row("Assists", "a", lambda i, c: st.number_input(
            "Assists", min_value=0, step=1,
            value=team_existing[i]["assists"] if team_existing[i] else 0,
            key=f"{team}_a_{i}", label_visibility="collapsed"))

        souls_sel = field_row("Souls (k)", "souls", lambda i, c: st.number_input(
            "Souls (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["souls_k"]) if team_existing[i] and team_existing[i].get("souls_k") is not None else 0.0,
            key=f"{team}_souls_{i}", label_visibility="collapsed"))

        plr_sel = field_row("Plyr Dmg (k)", "plr", lambda i, c: st.number_input(
            "Plyr Dmg (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["plr_damage_k"]) if team_existing[i] and team_existing[i].get("plr_damage_k") is not None else 0.0,
            key=f"{team}_plr_{i}", label_visibility="collapsed"))

        obj_sel = field_row("Obj Dmg (k)", "obj", lambda i, c: st.number_input(
            "Obj Dmg (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["obj_damage_k"]) if team_existing[i] and team_existing[i].get("obj_damage_k") is not None else 0.0,
            key=f"{team}_obj_{i}", label_visibility="collapsed"))

        heal_sel = field_row("Healing (k)", "heal", lambda i, c: st.number_input(
            "Healing (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["healing_k"]) if team_existing[i] and team_existing[i].get("healing_k") is not None else 0.0,
            key=f"{team}_heal_{i}", label_visibility="collapsed"))

        for i in range(6):
            all_rows.append({"team": team, "player": players_sel[i], "hero": heroes_sel[i],
                              "kills": kills_sel[i], "deaths": deaths_sel[i], "assists": assists_sel[i],
                              "souls_k": souls_sel[i], "plr_damage_k": plr_sel[i],
                              "obj_damage_k": obj_sel[i], "healing_k": heal_sel[i],
                              "draft_slot": slots_sel[i]})

    st.divider()
    c1, c2 = st.columns(2)
    default_bans = existing_match.get("bans", []) if existing_match else []
    default_fps = existing_match.get("first_picks", []) if existing_match else []
    bans = c1.multiselect("Bans", heroes, default=[b for b in default_bans if b in heroes])
    first_picks = c2.multiselect("First picks (draft order not tracked)", heroes,
                                  default=[f for f in default_fps if f in heroes])

    all_player_names_in_match = [r["player"] for r in all_rows]

    default_mvp = "None"
    default_keys = []
    if existing_match:
        mvps = [p["player"] for p in existing_match["players"] if p.get("mvp")]
        if mvps:
            default_mvp = mvps[0]
        default_keys = [p["player"] for p in existing_match["players"] if p.get("key_player")]

    mvp = st.selectbox("MVP", ["None"] + player_names, index=idx_of(["None"] + player_names, default_mvp))
    key_players = st.multiselect("Key Players (pick exactly 2)", player_names,
                                  default=[k for k in default_keys if k in player_names])

    submit_label = "Save changes" if editing else "Save match"
    submitted = st.form_submit_button(submit_label)

    if submitted:
        errors = []
        if not match_id.strip():
            errors.append("Match ID is required")
        if mvp != "None" and mvp not in all_player_names_in_match:
            errors.append(f"{mvp} (MVP) isn't one of the 12 players in this match.")
        if any(kp not in all_player_names_in_match for kp in key_players):
            errors.append("All Key Players must be players in this match.")
        if len(key_players) != 2:
            errors.append("Please select exactly 2 Key Players.")
        if len(set(all_player_names_in_match)) != 12:
            errors.append("Each of the 12 slots must have a unique player.")
        if not editing and any(m["match_id"] == match_id for m in matches):
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
                    "draft_slot": r["draft_slot"],
                })
            new_match = {
                "match_id": match_id,
                "date": str(match_date) if match_date else None,
                "game_length": game_length, "players": players_out,
                "bans": bans, "first_picks": first_picks,
            }
            if editing:
                data_io.update_match(match_id, new_match)
                st.success(f"Match {match_id} updated!")
            else:
                data_io.add_match(new_match)
                st.success(f"Match {match_id} saved!")
                st.balloons()

ui.brand_footer()
