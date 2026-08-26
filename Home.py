# No-op change to trigger a Streamlit Cloud redeploy.
import streamlit as st
from utils import data_io, stats

st.set_page_config(page_title="Deadlock PUG Stats", page_icon="🎯", layout="wide")

st.title("🎯 The Rumors of PUGs Death Have Been Greatly Exaggerated")
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
    side_df = stats.side_win_rates(df)
    side_df_display = side_df.copy()
    side_df_display["win_rate"] = (side_df_display["win_rate"] * 100).round(1).astype(str) + "%"
    st.dataframe(side_df_display, use_container_width=True, hide_index=True)

    st.subheader("Recent matches")
    # load_matches() hands back chronological order, so newest-first is just a reversal.
    # Sorting on match_id here would order the IDs as strings and bury the newest match.
    msum = stats.matches_summary_df(matches).iloc[::-1].head(10)
    st.dataframe(msum, use_container_width=True, hide_index=True)
else:
    st.info("No matches logged yet — head to **Add Match** to get started.")

st.divider()
st.page_link("pages/1_Match_Log.py", label="Match Log", icon="📋")
st.page_link("pages/2_Player.py", label="Player stats", icon="🧑")
st.page_link("pages/3_Hero_Summary.py", label="Hero summary", icon="🦸")
st.page_link("pages/4_Add_Match.py", label="Add a match", icon="➕")
st.page_link("pages/5_Add_Player_Hero.py", label="Add player / hero", icon="🆕")
st.page_link("pages/6_Player_Ranks.py", label="Log player rank", icon="📈")
st.page_link("pages/7_Leaderboard.py", label="Leaderboard", icon="🏆")
st.page_link("pages/8_Player_Cards.py", label="Player cards", icon="🪪")
st.page_link("pages/9_Head_to_Head.py", label="Head to head", icon="⚔️")
st.page_link("pages/10_Chemistry.py", label="Friendship buff", icon="🤝")
