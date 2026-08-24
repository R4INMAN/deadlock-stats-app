import streamlit as st
from utils import data_io, stats

st.set_page_config(page_title="Player Stats", page_icon="🧑", layout="wide")
st.title("🧑 Player Stats")

matches = data_io.load_matches()
players = data_io.load_players()
ranks = data_io.load_ranks()

if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
total_matches = len(matches)

st.subheader("All players")
summary = stats.player_summary_table(df)
display = summary.copy()
display["win_rate"] = (display["win_rate"] * 100).round(1)
display["award_rate"] = (display["award_rate"] * 100).round(1)
for c in ["avg_kp_pct", "avg_souls_per_min", "avg_obj_dmg_per_min", "avg_kills", "avg_deaths", "avg_assists"]:
    display[c] = display[c].round(2)
st.dataframe(
    display[["player", "games", "win_rate", "hero_variety", "most_played_hero",
              "avg_kp_pct", "avg_souls_per_min", "mvp_count", "key_player_count", "award_rate"]],
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Player detail")
player_names = sorted(set(df["player"].unique()) | set(players.keys()))
chosen = st.selectbox("Select a player", player_names)

detail = stats.player_detail(df, chosen, total_matches)
rank = data_io.current_rank(chosen, ranks)
notes = players.get(chosen, {}).get("notes", "")

if detail is None:
    st.info(f"{chosen} has no logged games yet.")
else:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Games", detail["games"])
    c2.metric("Win rate", f"{detail['win_rate']*100:.1f}%")
    c3.metric("Avg KP%", f"{detail['avg_kp_pct']:.1f}")
    c4.metric("MVPs", detail["mvp_count"])
    c5.metric("Key Player awards", detail["key_player_count"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Avg Souls/min", f"{detail['avg_souls_per_min']:.1f}" if detail['avg_souls_per_min'] else "n/a")
    c2.metric("Avg Obj Dmg/min", f"{detail['avg_obj_dmg_per_min']:.1f}" if detail['avg_obj_dmg_per_min'] else "n/a")
    c3.metric("Hero variety", detail["hero_variety"])

    if rank:
        st.caption(f"Current reported rank: **{rank}**")
    if notes:
        st.caption(f"Notes: {notes}")

    st.markdown("**Win rate by side**")
    side_display = detail["side_breakdown"].copy()
    side_display["win_rate"] = (side_display["win_rate"] * 100).round(1)
    st.dataframe(side_display, use_container_width=True, hide_index=True)

    st.markdown("**Heroes played**")
    hero_display = detail["hero_breakdown"].copy()
    hero_display["win_rate"] = (hero_display["win_rate"] * 100).round(1)
    hero_display["avg_kp_pct"] = hero_display["avg_kp_pct"].round(1)
    st.dataframe(hero_display, use_container_width=True, hide_index=True)
