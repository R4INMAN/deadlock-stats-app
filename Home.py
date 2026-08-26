import streamlit as st
from utils import data_io, stats, theme, ui

st.set_page_config(page_title="Puddle Punch PUGs", page_icon="assets/ui/puddle_punch.png",
                   layout="wide")

ui.page_header(
    "Puddle Punch PUGs",
    "The rumors of PUGs death have been greatly exaggerated.",
    mark_size=44,
)
st.link_button("New Draft", "https://statlocker.gg/draft/")

matches = data_io.load_matches()
players = data_io.load_players()
heroes = data_io.load_heroes()

df = stats.matches_to_rows_df(matches)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Matches logged", len(matches))
col2.metric("Players tracked", len(players))
col3.metric("Heroes tracked", len(heroes))
col4.metric("Player-games logged", len(df))

st.divider()

if not df.empty:
    st.subheader("Side win rates")
    # Two sides is a comparison, not a table - a pair of bars in the sides' own colors says
    # "these are close" faster than two rows of numbers do.
    side_df = stats.side_win_rates(df).sort_values("win_rate", ascending=False)
    for _, row in side_df.iterrows():
        ui.side_bar(row["team"], row["win_rate"], int(row["wins"]), int(row["games"]))

    st.subheader("Recent matches")
    msum = stats.matches_summary_df(matches).sort_values("match_id", ascending=False).head(10)
    st.dataframe(
        msum[["match_id", "game_length", "win_side", "mvps", "key_players", "num_players"]],
        use_container_width=True, hide_index=True,
        column_config=ui.MATCH_SUMMARY_COLUMNS,
    )
else:
    st.info("No matches logged yet — head to **Add Match** to get started.")

st.divider()
st.page_link("pages/1_Match_Log.py", label="Match Log")
st.page_link("pages/2_Player.py", label="Player stats")
st.page_link("pages/3_Hero_Summary.py", label="Hero summary")
st.page_link("pages/4_Add_Match.py", label="Add a match")
st.page_link("pages/5_Add_Player_Hero.py", label="Add player / hero")
st.page_link("pages/6_Player_Ranks.py", label="Log player rank")
st.page_link("pages/7_Leaderboard.py", label="Leaderboard")

ui.brand_footer()
