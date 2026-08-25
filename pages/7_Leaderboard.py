import streamlit as st
from utils import data_io, stats

st.set_page_config(page_title="Leaderboard", page_icon="🏆", layout="wide")
st.title("🏆 Leaderboard")

MIN_GAMES = 10
TOP_N = 10

matches = data_io.load_matches()

if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)

st.subheader(f"Top {TOP_N} win rates (min. {MIN_GAMES} games played)")
leaderboard = stats.winrate_leaderboard(df, min_games=MIN_GAMES, top_n=TOP_N)

if leaderboard.empty:
    st.info(f"No players have reached {MIN_GAMES} games played yet.")
else:
    display = leaderboard.reset_index(drop=True).copy()
    display.index = display.index + 1
    display["win_rate"] = (display["win_rate"] * 100).round(1)
    st.dataframe(
        display[["player", "games", "wins", "win_rate", "most_played_hero"]],
        use_container_width=True,
    )
