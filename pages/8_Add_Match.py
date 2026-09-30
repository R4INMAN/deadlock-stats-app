import datetime
import streamlit as st
from utils import data_io, dates, deadlock_api, ui
from utils.auth import require_edit_access

st.set_page_config(page_title="Add Match", page_icon="assets/ui/puddle_punch.png", layout="wide")

if not require_edit_access():
    st.stop()

ui.page_header("Match Management", "Log a new game, or fix one that went in wrong.")

players_dict = data_io.players_by_name()
heroes = data_io.load_heroes()
matches = data_io.load_matches()

# After the loads, not before: what is stale is only known once they have tried.
ui.storage_notice()
ui.stop_if_stale()

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
                 width='stretch', hide_index=True)

    confirm = st.checkbox(f"I'm sure I want to permanently delete match {chosen_id}")
    if st.button("Delete match", disabled=not confirm, type="primary"):
        if ui.report_save(lambda: data_io.delete_match(chosen_id),
                          f"Match {chosen_id} deleted."):
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

# ---------------- IMPORT (Add mode only) ----------------
# Fetching fills the form rather than saving: bans and first picks never reach the API (we draft
# on statlocker), and whoever is logging should still see the numbers before they go in. It also
# makes losing the form cheap - go add a missing player, come back, fetch again.
imported = None
if not editing:
    with st.container(border=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        fetch_id = c1.text_input("Fetch from match ID",
                                 help="Fills in heroes, teams, K/D/A, souls, damage, healing, "
                                      "length, date, winner, MVP and Key Players from the "
                                      "Deadlock API. Bans and first picks still need entering.")
        if c2.button("Fetch", width="stretch") and fetch_id.strip():
            fetch_id = fetch_id.strip()
            if any(m["match_id"] == fetch_id for m in matches):
                st.session_state.pop("imported_match", None)
                st.warning(f"Match {fetch_id} is already logged - use **Edit Match** to change it.")
            else:
                with st.spinner("Asking the Deadlock API..."):
                    info = deadlock_api.match_info(fetch_id)
                if info is None:
                    st.session_state.pop("imported_match", None)
                    st.error(f"The API doesn't have match {fetch_id}. Custom lobbies are sometimes "
                             f"never picked up - check the ID, or enter this one by hand below.")
                else:
                    st.session_state["imported_match"] = deadlock_api.to_match(
                        info, data_io.load_players(), heroes)
        imported = st.session_state.get("imported_match")
        if imported:
            st.success(f"Loaded match {imported['match_id']} - check it over, add bans and "
                       f"first picks, then save.")
            if st.button("Clear and enter by hand"):
                st.session_state.pop("imported_match", None)
                st.rerun()

# What the form opens on: the match being edited, the one just fetched, or nothing.
prefill = existing_match or imported

# Streamlit keeps a *keyed* widget's value in session state and, from its second run onward,
# ignores the `index=` / `value=` the script passes. Every box-score field below needs a key -
# six identical widgets in a row cannot be told apart without one - so the whole box score sat
# on whatever the Add form had last left in it, while the unkeyed fields above (date, length,
# winner, MVP) picked the chosen match up correctly. That is the reported "editing a match
# fills in the date but not the heroes", and it is why fixing a date meant retyping 12 players.
# Naming the keys after the match makes each selection a fresh set of widgets, and a fresh
# widget does read the default it is given.
form_scope = (f"edit_{edit_id}" if editing
              else f"import_{imported['match_id']}" if imported else "add")

if len(player_names) < 12:
    st.warning("You need at least 12 players logged (6 per side) before adding a match. Use **Add Player / Hero** first.")
if len(heroes) < 12:
    st.warning("You need at least 12 heroes logged before adding a match. Use **Add Player / Hero** first.")

# A name the dropdowns no longer offer cannot be pre-selected, so the slot falls back to the
# first option - and saving would quietly rewrite that row to somebody else. Say so instead.
if existing_match:
    unknown = sorted({p["player"] for p in existing_match["players"] if p["player"] not in player_names}
                     | {p["hero"] for p in existing_match["players"] if p["hero"] not in heroes})
    if unknown:
        st.warning(
            f"**{', '.join(unknown)}** " + ("is" if len(unknown) == 1 else "are") +
            " no longer in the player/hero lists, so those slots could not be filled in and are "
            "showing the first option instead. Fix them before saving, or the match will be "
            "rewritten with the wrong name."
        )

if imported:
    unlinked = [r for r in imported["players"] if r["player"] is None]
    if unlinked:
        st.info(
            "**" + ("One account isn't" if len(unlinked) == 1 else f"{len(unlinked)} accounts aren't")
            + " linked to a player yet** - the empty Player slots below. Pick who each one is and the "
              "account is remembered for next time. Someone brand new needs adding on **Add Player / "
              "Hero** first; fetching again afterwards brings everything back."
        )
    unknown_heroes = sorted({str(r["hero_id"]) for r in imported["players"] if r["hero"] is None})
    if unknown_heroes:
        st.warning(f"Hero id {', '.join(unknown_heroes)} isn't in our hero list - probably a new "
                   f"release. Add it on **Add Player / Hero**, then run `fetch_deadlock_assets.py`.")

st.caption("Enter all 12 players' stats, then bans, first picks, MVP, and Key Players at the bottom.")


def existing_player_row(team, slot_idx):
    if not prefill:
        return None
    team_rows = [p for p in prefill["players"] if p["team"] == team]
    return team_rows[slot_idx] if slot_idx < len(team_rows) else None


def idx_of(lst, value, default=0):
    try:
        return lst.index(value)
    except (ValueError, TypeError):
        return default


def slot_index(lst, row, field):
    """Pre-selection for a player/hero box. An imported slot we could not identify opens empty,
    so nobody saves a match with the first name in the list standing in for a stranger."""
    if imported and row and row[field] is None:
        return None
    return idx_of(lst, row[field] if row else None)


with st.form("match_form", clear_on_submit=False):
    if editing:
        match_id = existing_match["match_id"]
        st.text_input("Match ID", value=match_id, disabled=True)
    else:
        match_id = st.text_input("Match ID", value=imported["match_id"] if imported else "")

    # Defaults to tonight where the group plays, not where the server runs - but it stays
    # editable, because a match logged the morning after is not a match played that morning.
    # An existing match the backfill has not reached yet opens empty rather than defaulting to
    # today, so editing an old match for some unrelated reason cannot stamp it with this date.
    if prefill:
        stored = prefill.get("date")
        default_date = datetime.date.fromisoformat(stored) if stored else None
    else:
        default_date = dates.today()
    match_date = st.date_input("Date played", value=default_date,
                               help="The night the match was played.")

    default_length = prefill["game_length"] if prefill else "30:00"
    game_length = st.text_input("Game length (MM:SS)", value=default_length)

    default_winner = TEAM_A
    if prefill:
        winners = [p["team"] for p in prefill["players"] if p["win"]]
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
            index=slot_index(player_names, team_existing[i], "player"),
            placeholder=(f"Account {team_existing[i]['account_id']}"
                         if imported and team_existing[i] else "Choose a player"),
            key=f"{form_scope}_{team}_player_{i}", label_visibility="collapsed"))

        heroes_sel = field_row("Hero", "hero", lambda i, c: st.selectbox(
            "Hero", heroes,
            index=slot_index(heroes, team_existing[i], "hero"),
            key=f"{form_scope}_{team}_hero_{i}", label_visibility="collapsed"))

        slots_sel = field_row("Draft Slot", "slot", lambda i, c: st.number_input(
            "Draft Slot", min_value=1, max_value=12, step=1,
            value=(team_existing[i]["draft_slot"] if team_existing[i] and team_existing[i].get("draft_slot") else
                   (i + 1 if team == TEAM_A else i + 7)),
            key=f"{form_scope}_{team}_slot_{i}", label_visibility="collapsed"))

        kills_sel = field_row("Kills", "k", lambda i, c: st.number_input(
            "Kills", min_value=0, step=1,
            value=team_existing[i]["kills"] if team_existing[i] else 0,
            key=f"{form_scope}_{team}_k_{i}", label_visibility="collapsed"))

        deaths_sel = field_row("Deaths", "d", lambda i, c: st.number_input(
            "Deaths", min_value=0, step=1,
            value=team_existing[i]["deaths"] if team_existing[i] else 0,
            key=f"{form_scope}_{team}_d_{i}", label_visibility="collapsed"))

        assists_sel = field_row("Assists", "a", lambda i, c: st.number_input(
            "Assists", min_value=0, step=1,
            value=team_existing[i]["assists"] if team_existing[i] else 0,
            key=f"{form_scope}_{team}_a_{i}", label_visibility="collapsed"))

        souls_sel = field_row("Souls (k)", "souls", lambda i, c: st.number_input(
            "Souls (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["souls_k"]) if team_existing[i] and team_existing[i].get("souls_k") is not None else 0.0,
            key=f"{form_scope}_{team}_souls_{i}", label_visibility="collapsed"))

        plr_sel = field_row("Plyr Dmg (k)", "plr", lambda i, c: st.number_input(
            "Plyr Dmg (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["plr_damage_k"]) if team_existing[i] and team_existing[i].get("plr_damage_k") is not None else 0.0,
            key=f"{form_scope}_{team}_plr_{i}", label_visibility="collapsed"))

        obj_sel = field_row("Obj Dmg (k)", "obj", lambda i, c: st.number_input(
            "Obj Dmg (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["obj_damage_k"]) if team_existing[i] and team_existing[i].get("obj_damage_k") is not None else 0.0,
            key=f"{form_scope}_{team}_obj_{i}", label_visibility="collapsed"))

        heal_sel = field_row("Healing (k)", "heal", lambda i, c: st.number_input(
            "Healing (k)", min_value=0.0, step=1.0,
            value=float(team_existing[i]["healing_k"]) if team_existing[i] and team_existing[i].get("healing_k") is not None else 0.0,
            key=f"{form_scope}_{team}_heal_{i}", label_visibility="collapsed"))

        for i in range(6):
            all_rows.append({"team": team, "player": players_sel[i], "hero": heroes_sel[i],
                              "account_id": team_existing[i].get("account_id") if team_existing[i] else None,
                              "was_unlinked": bool(imported and team_existing[i]
                                                   and team_existing[i]["player"] is None),
                              "kills": kills_sel[i], "deaths": deaths_sel[i], "assists": assists_sel[i],
                              "souls_k": souls_sel[i], "plr_damage_k": plr_sel[i],
                              "obj_damage_k": obj_sel[i], "healing_k": heal_sel[i],
                              "draft_slot": slots_sel[i]})

    st.divider()
    c1, c2 = st.columns(2)
    default_bans = prefill.get("bans", []) if prefill else []
    default_fps = prefill.get("first_picks", []) if prefill else []
    bans = c1.multiselect("Bans", heroes, default=[b for b in default_bans if b in heroes])
    first_picks = c2.multiselect("First picks (draft order not tracked)", heroes,
                                  default=[f for f in default_fps if f in heroes])

    all_player_names_in_match = [r["player"] for r in all_rows]

    default_mvp = "None"
    default_keys = []
    if prefill:
        mvps = [p["player"] for p in prefill["players"] if p.get("mvp") and p["player"]]
        if mvps:
            default_mvp = mvps[0]
        default_keys = [p["player"] for p in prefill["players"] if p.get("key_player") and p["player"]]

    # Keyed per form_scope for the same reason as the box score: without a key a fresh fetch
    # would be ignored in favour of whatever these boxes held a run ago.
    mvp = st.selectbox("MVP", ["None"] + player_names, index=idx_of(["None"] + player_names, default_mvp),
                       key=f"{form_scope}_mvp")
    key_players = st.multiselect("Key Players (pick exactly 2)", player_names,
                                  default=[k for k in default_keys if k in player_names],
                                  key=f"{form_scope}_key_players")

    submit_label = "Save changes" if editing else "Save match"
    submitted = st.form_submit_button(submit_label)

    if submitted:
        errors = []
        if any(r["player"] is None for r in all_rows):
            errors.append("Every Player slot needs someone in it.")
        if any(r["hero"] is None for r in all_rows):
            errors.append("Every Hero slot needs a hero.")
        if not match_id.strip():
            errors.append("Match ID is required")
        if mvp != "None" and mvp not in all_player_names_in_match:
            errors.append(f"{mvp} (MVP) isn't one of the 12 players in this match.")
        if any(kp not in all_player_names_in_match for kp in key_players):
            errors.append("All Key Players must be players in this match.")
        if len(key_players) != 2:
            errors.append("Please select exactly 2 Key Players.")
        if None not in all_player_names_in_match and len(set(all_player_names_in_match)) != 12:
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
                    # The person, not the name. Everything that reads this match back resolves
                    # the display name from here, so a later alias change carries the row with it.
                    "player_key": players_dict[r["player"]]["player_key"],
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
                ui.report_save(lambda: data_io.update_match(match_id, new_match),
                               f"Match {match_id} updated!")
            elif ui.report_save(lambda: data_io.add_match(new_match),
                                f"Match {match_id} saved!", celebrate=True):
                # After the match, not before: link_account re-keys a nickname-keyed player and
                # rewrites their match rows, and that sweep has to see this match to move it.
                for r in all_rows:
                    if r["was_unlinked"] and r["account_id"]:
                        ui.report_save(
                            lambda r=r: data_io.link_account(players_dict[r["player"]]["player_key"],
                                                             r["account_id"]),
                            f"Linked account {r['account_id']} to {r['player']}.")
                st.session_state.pop("imported_match", None)

ui.brand_footer()
