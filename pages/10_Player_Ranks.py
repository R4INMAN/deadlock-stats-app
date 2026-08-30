import datetime
import streamlit as st
from utils import data_io, ui
from utils.auth import require_edit_access

if not require_edit_access():
    st.stop()
    
st.set_page_config(page_title="Player Ranks", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Player Ranks", "Reported ranks over time.")
ui.storage_notice()

players = data_io.load_players()
ranks = data_io.load_ranks()
rank_tiers = data_io.load_rank_tiers()

if not players:
    st.info("Add players first on the Add Player / Hero page.")
    st.stop()

st.subheader("Log a new rank")
with st.form("add_rank_form", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    player = c1.selectbox("Player", sorted(players.keys()))
    rank = c2.selectbox("Rank", rank_tiers)
    entry_date = c3.date_input("Date", value=datetime.date.today())
    submitted = st.form_submit_button("Log rank")
    if submitted:
        if ui.report_save(lambda: data_io.add_rank_entry(player, rank, str(entry_date)),
                          f"Logged {player} as {rank} on {entry_date}."):
            st.rerun()

st.divider()
st.subheader("Current ranks")
current = []
for p in sorted(players.keys()):
    r = data_io.current_rank(p, ranks)
    if r:
        current.append({"player": p, "current_rank": r})
st.dataframe(current, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Rank history")
player_pick = st.selectbox("View history for", ["All"] + sorted(players.keys()))
history = ranks if player_pick == "All" else [r for r in ranks if r["player"] == player_pick]
history = sorted(history, key=lambda r: (r["player"], r["date"]))
st.dataframe(history, use_container_width=True, hide_index=True)

ui.brand_footer()
