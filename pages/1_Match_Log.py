import streamlit as st
from utils import data_io, stats

st.set_page_config(page_title="Match Log", page_icon="📋", layout="wide")
st.title("📋 Match Log")

matches = data_io.load_matches()
if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
msum = stats.matches_summary_df(matches).sort_values("match_id", ascending=False)

with st.expander("Filters", expanded=False):
    c1, c2, c3 = st.columns(3)
    player_filter = c1.selectbox("Player", ["Any"] + sorted(df["player"].unique()))
    hero_filter = c2.selectbox("Hero", ["Any"] + sorted(df["hero"].unique()))
    side_filter = c3.selectbox("Side", ["Any"] + sorted(df["team"].unique()))

filtered_ids = set(df["match_id"])
if player_filter != "Any":
    filtered_ids &= set(df[df["player"] == player_filter]["match_id"])
if hero_filter != "Any":
    filtered_ids &= set(df[df["hero"] == hero_filter]["match_id"])
if side_filter != "Any":
    filtered_ids &= set(df[(df["team"] == side_filter)]["match_id"])

msum = msum[msum["match_id"].isin(filtered_ids)]

st.caption(f"{len(msum)} match(es)")
st.dataframe(msum, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Match detail")
match_ids = msum["match_id"].tolist()
if match_ids:
    chosen = st.selectbox("Select a match", match_ids)
    match = next(m for m in matches if m["match_id"] == chosen)

    c1, c2 = st.columns(2)
    c1.write(f"**Length:** {match.get('game_length', 'n/a')}")
    c2.write(f"**Bans:** {', '.join(match.get('bans', [])) or 'none logged'}")
    st.write(f"**First picks:** {', '.join(match.get('first_picks', [])) or 'none logged'}")

    for side in sorted(set(p["team"] for p in match["players"])):
        st.markdown(f"**{side}**")
        rows = [p for p in match["players"] if p["team"] == side]
        display_rows = []
        for p in rows:
            display_rows.append({
                "Player": p["player"], "Hero": p["hero"], "Win": p["win"],
                "MVP": p["mvp"], "Key Player": p["key_player"],
                "K": p["kills"], "D": p["deaths"], "A": p["assists"],
                "Souls (k)": p["souls_k"], "KP%": p["kp_pct"],
            })
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
