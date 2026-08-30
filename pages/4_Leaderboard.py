import streamlit as st
from utils import data_io, stats, ui

st.set_page_config(page_title="Leaderboard", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Leaderboard", "Best win rates among the regulars.")

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
    display["portrait"] = ui.hero_portrait_column(display["most_played_hero"])
    st.dataframe(
        display[["portrait", "player", "games", "wins", "win_rate", "most_played_hero"]],
        width='stretch',
        column_config={
            "portrait": st.column_config.ImageColumn("", width="small",
                                                      help="Most played hero"),
            "player": st.column_config.TextColumn("Player"),
            "games": st.column_config.NumberColumn("Games"),
            "wins": st.column_config.NumberColumn("Wins"),
            "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
            "most_played_hero": st.column_config.TextColumn("Most played"),
        },
    )

ui.brand_footer()
