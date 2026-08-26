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
    # load_matches() hands back chronological order, so newest-first is just a reversal.
    # Sorting on match_id here would order the IDs as strings and bury the newest match.
    msum = stats.matches_summary_df(matches).iloc[::-1].head(10)
    st.dataframe(
        ui.match_summary_display(msum),
        use_container_width=True, hide_index=True,
        column_config=ui.MATCH_SUMMARY_COLUMNS,
    )
else:
    st.info("No matches logged yet — head to **Add Match** to get started.")

st.divider()
# Reading pages first, then the three that write to data/. Page order here has to stay in step
# with the number prefixes on the files, since those drive the sidebar independently.
st.page_link("pages/1_Match_Log.py", label="Match Log")
st.page_link("pages/2_Player.py", label="Player stats")
st.page_link("pages/3_Hero_Summary.py", label="Hero summary")
st.page_link("pages/4_Leaderboard.py", label="Leaderboard")
st.page_link("pages/5_Player_Cards.py", label="Player cards")
st.page_link("pages/6_Head_to_Head.py", label="Head to head")
st.page_link("pages/7_Chemistry.py", label="Friendship buff")

st.caption("Keeping the data up to date")
st.page_link("pages/8_Add_Match.py", label="Add a match")
st.page_link("pages/9_Add_Player_Hero.py", label="Add player / hero")
st.page_link("pages/10_Player_Ranks.py", label="Log player rank")

ui.brand_footer()
