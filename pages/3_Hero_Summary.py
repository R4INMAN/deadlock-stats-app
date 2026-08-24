import streamlit as st
from utils import data_io, stats

st.set_page_config(page_title="Hero Summary", page_icon="🦸", layout="wide")
st.title("🦸 Hero Summary")

matches = data_io.load_matches()
heroes = data_io.load_heroes()

if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
total_matches = len(matches)

st.subheader("All heroes")
table = stats.hero_summary_table(df, total_matches, matches=matches, heroes_list=heroes)
display = table.copy()
for c in ["win_rate", "pick_rate", "ban_rate", "first_pick_rate"]:
    display[c] = (display[c] * 100).round(1)
display["avg_kp_pct"] = display["avg_kp_pct"].round(1)
st.dataframe(
    display[["hero", "games", "win_rate", "pick_rate", "ban_rate", "first_pick_rate",
              "mvp_count", "key_player_count", "top_player", "top_player_games"]],
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Hero detail")
hero_names = sorted(set(df["hero"].unique()) | set(heroes))
chosen = st.selectbox("Select a hero", hero_names)

detail = stats.hero_detail(df, chosen, total_matches)

if detail["games"] == 0:
    st.info(f"{chosen} hasn't been played yet.")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Games played", detail["games"])
    c2.metric("Win rate", f"{detail['win_rate']*100:.1f}%")
    c3.metric("Pick rate", f"{detail['pick_rate']*100:.1f}%")

    st.markdown("**Who plays this hero**")
    pb = detail["player_breakdown"].copy()
    pb["win_rate"] = (pb["win_rate"] * 100).round(1)
    pb["avg_kp_pct"] = pb["avg_kp_pct"].round(1)
    st.dataframe(pb, use_container_width=True, hide_index=True)
