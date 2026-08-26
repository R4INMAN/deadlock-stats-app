"""The friendship buff: who wins together, and whether that means anything."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import chemistry, data_io, stats

st.set_page_config(page_title="Chemistry", page_icon="🤝", layout="wide")
st.title("🤝 The Friendship Buff")

matches = data_io.load_matches()
if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)

min_games = st.slider(
    "Minimum games together", min_value=3, max_value=20, value=chemistry.MIN_GAMES_DEFAULT,
    help="Pairs below this never appear. Raising it cuts noise but also cuts most of the roster.",
)

rows = chemistry.pair_records(matches, min_games=min_games)


# ---------------------------------------------------------------- verdict
@st.cache_data(show_spinner="Bootstrapping the null distribution…")
def run_tests(n_matches, min_games):
    # n_matches is in the cache key so the verdict recomputes when matches are added.
    return chemistry.chemistry_test(matches, min_games=min_games, n_boot=1000), \
        chemistry.cohesion_test(matches)


spread_test, cohesion = run_tests(len(matches), min_games)

st.subheader("Is it real?")
if cohesion and spread_test:
    lo, hi = chemistry.wilson_interval(cohesion["cohesive_side_wins"], cohesion["n_matches"])
    verdict_cols = st.columns(2)
    with verdict_cols[0]:
        st.markdown("**Do high-history teams win more?**")
        st.metric(
            "More-cohesive side wins",
            f"{cohesion['cohesive_side_win_rate']:.1%}",
            f"{cohesion['cohesive_side_wins']} of {cohesion['n_matches']} · 95% CI {lo:.0%}–{hi:.0%}",
            delta_color="off",
        )
        st.caption(
            "Each match scores both sides by how many games their pairs had already played "
            "together, then asks whether the more-practised side won."
        )
    with verdict_cols[1]:
        st.markdown("**Do pair win rates spread more than chance?**")
        z = ((spread_test["observed"] - spread_test["null_mean"]) / spread_test["null_sd"]
             if spread_test["null_sd"] else 0.0)
        st.metric("Spread vs. coin flips", f"{z:+.1f} SD", f"p = {spread_test['p_value']:.2f}",
                  delta_color="off")
        st.caption(
            f"Observed {spread_test['observed']:.1f} against a chance-only average of "
            f"{spread_test['null_mean']:.1f}, over {spread_test['n_boot']} simulated seasons."
        )

    real = cohesion["p_value"] < 0.05 or spread_test["p_value"] < 0.05
    if real:
        st.success("At least one test clears the bar — there is signal here beyond luck.")
    else:
        power_65 = chemistry.detection_power(cohesion["n_matches"], 0.65)
        power_60 = chemistry.detection_power(cohesion["n_matches"], 0.60)
        st.info(
            f"**No detectable friendship buff — and no evidence against one either.** The headline "
            f"{cohesion['cohesive_side_win_rate']:.1%} sits below 50%, but its interval "
            f"({lo:.0%}–{hi:.0%}) straddles a coin flip, so this is *we can't tell*, not "
            f"*stacking friends loses*." + chr(10) * 2 +
            f"The honest limit is sample size. At {cohesion['n_matches']} matches these tests catch "
            f"a large effect (65/35) about {power_65:.0%} of the time, but a moderate one (60/40) "
            f"only {power_60:.0%}. A real-but-subtle buff would still be invisible here — worth "
            f"rerunning near 200 matches."
        )

st.divider()

# ---------------------------------------------------------------- leaderboard
st.subheader("🏆 Best Friends")
if not rows:
    st.info(f"No pair has {min_games}+ games together yet.")
    st.stop()

threshold = chemistry.significant_threshold(min_games)
st.caption(
    f"Sorted by win rate together, ties broken by games played. At exactly {min_games} games a pair "
    f"would need to top **{threshold:.0%}** to be distinguishable from luck — so read this as a "
    "record, not a ranking of who is genuinely better together."
)

table = pd.DataFrame([{
    "pair": f"{r['player_a']} + {r['player_b']}",
    "games": r["games"],
    "record": f"{r['wins']}–{r['losses']}",
    "win_rate": round(r["win_rate"] * 100, 1),
    "95% low": round(r["ci_low"] * 100, 1),
    "95% high": round(r["ci_high"] * 100, 1),
    "beats luck": "✅" if r["beats_noise"] else "",
} for r in rows])

top, bottom = st.tabs([f"Best {min(15, len(table))}", f"Worst {min(15, len(table))}"])
with top:
    st.dataframe(table.head(15), use_container_width=True, hide_index=True)
with bottom:
    st.dataframe(table.tail(15).iloc[::-1], use_container_width=True, hide_index=True)

n_sig = int(sum(r["beats_noise"] for r in rows))
expected_by_chance = 0.05 * len(rows)
st.caption(
    f"{n_sig} of {len(rows)} qualifying pairs clear the luck bar. Pure chance would produce about "
    f"{expected_by_chance:.0f} — so {'that is roughly what noise alone predicts' if n_sig <= expected_by_chance else 'that is more than noise alone predicts'}."
)

# ---------------------------------------------------------------- interval plot
st.divider()
st.subheader("How much to trust each pair")
show = rows[:20]
fig = go.Figure()
for i, r in enumerate(reversed(show)):
    label = f"{r['player_a']} + {r['player_b']}"
    fig.add_trace(go.Scatter(
        x=[r["ci_low"] * 100, r["ci_high"] * 100], y=[label, label],
        mode="lines", line=dict(color="#5A6478", width=6), showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[r["win_rate"] * 100], y=[label], mode="markers",
        marker=dict(color="#5FE69E" if r["beats_noise"] else "#C9D1D9", size=11,
                    line=dict(color="#10130D", width=1)),
        showlegend=False,
        hovertemplate=f"{label}<br>{r['wins']}–{r['losses']} ({r['win_rate']:.1%})<extra></extra>",
    ))
fig.add_vline(x=50, line=dict(color="#D74949", width=2, dash="dash"),
              annotation_text="coin flip", annotation_position="top")
fig.update_layout(
    height=28 * len(show) + 120, margin=dict(l=10, r=10, t=40, b=40),
    xaxis_title="win rate together (%)", xaxis_range=[0, 100],
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Each bar is a 95% Wilson interval. Bars crossing the red line are consistent with the pair "
    "being no better together than apart — which is most of them, and the honest reason the "
    "leaderboard above is for bragging rather than for drafting."
)

# ---------------------------------------------------------------- per player
st.divider()
st.subheader("Look up a player")
names = sorted(df["player"].unique())
who = st.selectbox("Player", names)
mine = chemistry.player_pair_records(matches, who, min_games=min_games)
if mine:
    st.dataframe(
        pd.DataFrame([{
            "teammate": r["teammate"], "games": r["games"],
            "record": f"{r['wins']}–{r['losses']}",
            "win_rate": round(r["win_rate"] * 100, 1),
        } for r in mine]),
        use_container_width=True, hide_index=True,
    )
else:
    st.info(f"{who} has no teammate with {min_games}+ shared games.")

with st.expander("Method — why the numbers are presented this way"):
    st.markdown(f"""
There are **{len(chemistry.pair_records(matches, min_games=1))} distinct teammate pairs** across
{len(matches)} matches, and roughly half have played together exactly once. That combination is a
trap: with hundreds of pairs to scan, dozens will show a lopsided record from luck alone. Ranking
them and crowning the top is a reliable way to invent friendships that aren't there.

Three choices follow from that:

- **Wilson intervals, not point estimates.** At small samples the textbook normal interval
  misbehaves badly (a 5–0 pair gets a 100% win rate with zero width). Wilson stays sane at the edges.
- **A whole-season bootstrap, not a per-pair test.** All 15 pairs on a team share one result, so
  pair records are heavily correlated. The null simulates entire matches to preserve that; a test
  treating pairs as independent would call almost any group significant.
- **A cohesion test alongside it.** Estimating 850 pair effects from {len(matches)} outcomes has
  almost no power. Asking the single question "does the side with more shared history win?" spends
  one parameter instead of 850, which is why it is the test that can actually answer the theory.

Power is the honest caveat throughout: a null result at this sample size rules out a *large*
friendship buff, not a small one.
""")
