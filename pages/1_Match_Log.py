import streamlit as st
from utils import data_io, stats, theme, ui
#TESTING SAVE STATE COMMENT
st.set_page_config(page_title="Match Log", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Match Log", "Every logged game, side by side.")

matches = data_io.load_matches()
if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
# Chronological from load_matches(); reverse for newest-first. A sort_values("match_id")
# here would compare the IDs as strings and put 10-digit IDs below 8-digit ones.
msum = stats.matches_summary_df(matches).iloc[::-1]

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
st.dataframe(
    ui.match_summary_display(msum),
    width='stretch', hide_index=True,
    column_config=ui.MATCH_SUMMARY_COLUMNS,
)

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

    portraits = ui.hero_portrait_uris()
    for side in sorted(set(p["team"] for p in match["players"])):
        rows = [p for p in match["players"] if p["team"] == side]
        st.markdown(ui.side_header(side, won=any(p["win"] for p in rows)),
                    unsafe_allow_html=True)
        display_rows = []
        for p in rows:
            display_rows.append({
                "": portraits.get(p["hero"]),
                "Player": p["player"], "Hero": p["hero"],
                "MVP": ui.award_icon_uri("mvp") if p["mvp"] else "",
                "Key Player": ui.award_icon_uri("key_player") if p["key_player"] else "",
                "K": p["kills"], "D": p["deaths"], "A": p["assists"],
                "Souls (k)": p["souls_k"], "KP%": p["kp_pct"],
            })
        # The side header already says who won, so a per-row Win column would repeat it 6 times.
        st.dataframe(
            display_rows, width='stretch', hide_index=True,
            column_config={
                "": st.column_config.ImageColumn("", width="small"),
                "MVP": st.column_config.ImageColumn("MVP", width="small"),
                "Key Player": st.column_config.ImageColumn("Key", width="small"),
                "KP%": st.column_config.NumberColumn("KP%", format="%.1f"),
            },
        )

ui.brand_footer()
