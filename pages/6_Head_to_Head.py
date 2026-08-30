"""Two players, two questions: how do they do together, and how do they do against each other."""
import streamlit as st

from utils import chemistry, data_io, stats

st.set_page_config(page_title="Head to Head", page_icon="⚔️", layout="wide")
st.title("⚔️ Head to Head")

matches = data_io.load_matches()
if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
names = sorted(df["player"].unique())
if len(names) < 2:
    st.info("Need at least two players with logged games.")
    st.stop()

# Default to the two most-played players. Defaulting to the alphabetical first two opens the
# page on a pair who have never shared a match, which reads as though the page is broken.
regulars = df["player"].value_counts().index.tolist()
c1, c2 = st.columns(2)
a = c1.selectbox("Player A", names, index=names.index(regulars[0]))
b = c2.selectbox("Player B", names, index=names.index(regulars[1]))

if a == b:
    st.warning("Pick two different players.")
    st.stop()


def split_records(matches, a, b):
    """Walk matches once, bucketing into games as teammates vs games on opposite sides."""
    together = {"games": 0, "wins": 0, "match_ids": []}
    against = {"games": 0, "a_wins": 0, "match_ids": []}
    for m in matches:
        by_name = {p["player"]: p for p in m["players"]}
        pa, pb = by_name.get(a), by_name.get(b)
        if not pa or not pb:
            continue
        if pa["team"] == pb["team"]:
            together["games"] += 1
            together["wins"] += bool(pa["win"])
            together["match_ids"].append(m["match_id"])
        else:
            against["games"] += 1
            against["a_wins"] += bool(pa["win"])
            against["match_ids"].append(m["match_id"])
    return together, against


together, against = split_records(matches, a, b)

if together["games"] == 0 and against["games"] == 0:
    st.info(f"{a} and {b} have never been in the same match.")
    st.stop()

st.subheader("As teammates")
if together["games"]:
    w = together["wins"]
    n = together["games"]
    lo, hi = chemistry.wilson_interval(w, n)
    m1, m2, m3 = st.columns(3)
    m1.metric("Games together", n)
    m2.metric("Record", f"{w}–{n - w}")
    m3.metric("Win rate", f"{w / n:.1%}")
    st.caption(
        f"95% interval **{lo:.1%} – {hi:.1%}**. A pair with {n} games needs to clear "
        f"**{chemistry.significant_threshold(n):.0%}** before the result means anything beyond luck."
    )
else:
    st.caption("Never played on the same team.")

st.divider()
st.subheader("As opponents")
if against["games"]:
    n = against["games"]
    aw = against["a_wins"]
    lo, hi = chemistry.wilson_interval(aw, n)
    m1, m2, m3 = st.columns(3)
    m1.metric("Games opposed", n)
    m2.metric(f"{a} wins", aw)
    m3.metric(f"{b} wins", n - aw)
    st.caption(
        f"{a} takes {aw / n:.1%} of these (95% interval {lo:.1%} – {hi:.1%}). "
        "Both players are one of twelve, so this says more about the lobbies than about either of them."
    )
else:
    st.caption("Never played against each other.")

st.divider()
st.subheader("Shared matches")
ids = set(together["match_ids"]) | set(against["match_ids"])
msum = stats.matches_summary_df(matches).iloc[::-1]
msum = msum[msum["match_id"].isin(ids)].copy()
msum["side"] = ["teammates" if mid in set(together["match_ids"]) else "opponents"
                for mid in msum["match_id"]]
st.dataframe(msum, width='stretch', hide_index=True)
