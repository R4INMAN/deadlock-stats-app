"""The friendship buff: who wins together beyond what they win apart, and whether it means anything."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import chemistry, data_io, ratings, stats, theme

st.set_page_config(page_title="Chemistry", page_icon="🤝", layout="wide")
st.title("🤝 The Friendship Buff")
st.caption(
    "Not who wins together - who wins **more than they do apart**. Every pair below is scored "
    "against a baseline built from the two players' other games, so a duo does not make the top "
    "of the list just for containing someone on a heater."
)

matches = data_io.load_matches()
if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
side_list = ratings.sides(matches)

POSITIVE = theme.readable(theme.color("brand_green"))
NEGATIVE = theme.readable(theme.color("debuff_color"))
NEUTRAL = theme.NEUTRAL_HERO_COLOR
ACCENT = theme.readable(theme.color("tech_color"))
INK = theme.color("base_text")

controls = st.columns([2, 3])
with controls[0]:
    min_games = st.slider(
        "Minimum games together", min_value=3, max_value=20, value=chemistry.MIN_GAMES_DEFAULT,
        help="Pairs below this never appear. Raising it cuts noise but also cuts most of the roster.",
    )
with controls[1]:
    mode_label = st.radio(
        "Baseline — what the pair is measured against",
        ["Fitted ratings (recommended)", "Their records at face value"],
        horizontal=True,
        help=(
            "Fitted: a ridge Bradley-Terry model over all twelve players in each match, with the "
            "shrinkage chosen by marginal likelihood. Face value: the two players' win rates apart "
            "from each other, added on the log-odds scale and believed literally."
        ),
    )
mode = (chemistry.BASELINE_MODEL if mode_label.startswith("Fitted")
        else chemistry.BASELINE_RECORDS)


@st.cache_data(show_spinner="Fitting baselines…")
def synergy_rows(n_matches, min_games, mode):
    # n_matches is in the cache key so everything recomputes when matches are added.
    return chemistry.pair_synergy(matches, min_games=min_games, mode=mode, side_list=side_list)


@st.cache_data(show_spinner="Bootstrapping the null distribution…")
def run_tests(n_matches, min_games):
    return (chemistry.chemistry_test(matches, min_games=min_games, n_boot=1000,
                                     side_list=side_list),
            chemistry.cohesion_test(matches, side_list=side_list),
            ratings.record_calibration(matches, n_perm=400, side_list=side_list))


rows = synergy_rows(len(matches), min_games, mode)
spread_test, cohesion, calibration = run_tests(len(matches), min_games)

# ---------------------------------------------------------------- verdict
st.subheader("Is it real?")
cards = st.columns(3)

with cards[0]:
    st.markdown("**Do individual records predict wins?**")
    if calibration:
        st.metric("Win-rate slope", f"{calibration['slope']:+.2f}",
                  f"p = {calibration['p_value']:.2f} vs. chance", delta_color="off")
        st.caption(
            f"1.00 would mean a player's win rate predicts the next match exactly as advertised; "
            f"0 means it says nothing. Measured with each match held out of its own ratings, "
            f"against {calibration['n_perm']} simulated coin-flip seasons (which land at "
            f"{calibration['null_mean']:+.2f}, not 0, for bookkeeping reasons)."
        )

with cards[1]:
    if cohesion:
        st.markdown("**Do high-history teams beat their baseline?**")
        st.metric("More-cohesive side wins",
                  f"{cohesion['cohesive_side_win_rate']:.1%}",
                  f"baseline {cohesion['expected_win_rate']:.1%} · "
                  f"{cohesion['excess_win_rate'] * 100:+.1f}pp · p = {cohesion['p_value']:.2f}",
                  delta_color="off")
        st.caption(
            f"Each of {cohesion['n_matches']} matches scores both sides by how many games their "
            "pairs had already played together, then asks whether the more-practised side beat "
            "what its roster was due."
        )

with cards[2]:
    if spread_test:
        st.markdown("**Do pair win rates spread beyond the baseline?**")
        z = ((spread_test["observed"] - spread_test["null_mean"]) / spread_test["null_sd"]
             if spread_test["null_sd"] else 0.0)
        st.metric("Spread vs. baseline", f"{z:+.1f} SD", f"p = {spread_test['p_value']:.2f}",
                  delta_color="off")
        st.caption(
            f"Observed {spread_test['observed']:.1f} against {spread_test['null_mean']:.1f} from "
            f"{spread_test['n_boot']} seasons simulated at each match's baseline odds, over the "
            f"{spread_test['n_pairs']} pairs with {min_games}+ games."
        )

if cohesion and spread_test:
    if cohesion["p_value"] < 0.05 or spread_test["p_value"] < 0.05:
        st.success("At least one test clears the bar — there is signal here beyond luck.")
    else:
        lo, hi = chemistry.wilson_interval(cohesion["cohesive_side_wins"], cohesion["n_matches"])
        power_65 = chemistry.detection_power(cohesion["n_matches"], 0.65)
        power_60 = chemistry.detection_power(cohesion["n_matches"], 0.60)
        st.info(
            f"**No detectable friendship buff — and no evidence against one either.** The headline "
            f"{cohesion['cohesive_side_win_rate']:.1%} sits below its {cohesion['expected_win_rate']:.1%} "
            f"baseline, but the interval ({lo:.0%}–{hi:.0%}) straddles it, so this is *we can't tell*, "
            f"not *stacking friends loses*." + chr(10) * 2 +
            f"The honest limit is sample size. At {cohesion['n_matches']} matches these tests catch "
            f"a large effect (65/35) about {power_65:.0%} of the time, but a moderate one (60/40) "
            f"only {power_60:.0%}. A real-but-subtle buff would still be invisible here — worth "
            f"rerunning near 200 matches."
        )

if calibration and calibration["p_value"] >= 0.05:
    st.caption(
        "⚠️ Note what the first card says: in this pool, a player's win rate carries no usable "
        "signal about the next match. That is why the fitted baseline lands near 50% for nearly "
        "everyone — there is no demonstrated star to subtract. Switch the baseline to *face value* "
        "to see the strongest case that a pair's record is merely its members."
    )

st.divider()

# ---------------------------------------------------------------- leaderboard
st.subheader("🏆 Best Friends")
if not rows:
    st.info(f"No pair has {min_games}+ games together yet.")
    st.stop()

st.caption(
    "**Synergy** is win rate together minus the baseline over the very same games, in percentage "
    "points. The baseline is refitted with the pair's shared games removed — otherwise their wins "
    "together would inflate both players' individual ratings and then be subtracted back off as "
    "if they had been expected all along. *A/B apart* is each player's record in games without "
    "the other, which is usually the number that deflates a legend."
)

table = pd.DataFrame([{
    "pair": f"{r['player_a']} + {r['player_b']}",
    "games": r["games"],
    "together": f"{r['wins']}–{r['losses']} ({r['win_rate']:.0%})",
    "baseline": round(r["expected"] * 100, 1),
    "synergy (pp)": round(r["synergy"] * 100, 1),
    "p": round(r["p_value"], 3),
    "A apart": f"{r['a_apart_rate']:.0%} ({r['a_apart_games']}g)" if r["a_apart_games"] else "—",
    "B apart": f"{r['b_apart_rate']:.0%} ({r['b_apart_games']}g)" if r["b_apart_games"] else "—",
    "beats luck": "✅" if r["p_value"] < 0.05 else "",
} for r in rows])

top, bottom = st.tabs([f"Best {min(15, len(table))}", f"Worst {min(15, len(table))}"])
with top:
    st.dataframe(table.head(15), width='stretch', hide_index=True)
with bottom:
    st.dataframe(table.tail(15).iloc[::-1], width='stretch', hide_index=True)

n_sig = sum(1 for r in rows if r["p_value"] < 0.05)
expected_by_chance = 0.05 * len(rows)
st.caption(
    f"{n_sig} of {len(rows)} qualifying pairs clear p < 0.05. Testing that many pairs at once, pure "
    f"chance would produce about {expected_by_chance:.0f} — so "
    f"{'that is roughly what noise alone predicts' if n_sig <= expected_by_chance else 'that is more than noise alone predicts'}. "
    "Treat any single row as a story, not a finding."
)

# ---------------------------------------------------------------- interval plot
st.divider()
st.subheader("How much of each record is the pairing?")
# Both ends of the list, so the zero line sits in the middle of the picture rather than at its
# edge - the negative pairs are the same phenomenon and hiding them would flatter the positive ones.
edge = min(10, len(rows) // 2) or len(rows)
show = rows[:edge] + rows[-edge:] if len(rows) > edge else rows
fig = go.Figure()
for r in reversed(show):
    label = f"{r['player_a']} + {r['player_b']}"
    significant = r["p_value"] < 0.05
    tone = POSITIVE if r["synergy"] > 0 else NEGATIVE
    fig.add_trace(go.Scatter(
        x=[r["synergy_low"] * 100, r["synergy_high"] * 100], y=[label, label],
        mode="lines", line=dict(color=NEUTRAL, width=2), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[r["synergy"] * 100], y=[label], mode="markers",
        marker=dict(color=tone if significant else theme.color("off_black"), size=10,
                    line=dict(color=tone, width=2)),
        showlegend=False,
        hovertemplate=(f"{label}<br>{r['wins']}–{r['losses']} ({r['win_rate']:.0%}) vs. a "
                       f"{r['expected']:.0%} baseline<br>synergy {r['synergy'] * 100:+.1f}pp"
                       f" · p = {r['p_value']:.3f}<extra></extra>"),
    ))
    if significant:
        # Label on the outboard end of the interval, so it never lands between the dot and zero.
        outboard = (r["synergy_high"] if r["synergy"] > 0 else r["synergy_low"]) * 100
        fig.add_annotation(x=outboard + (2 if r["synergy"] > 0 else -2), y=label,
                           text=f"{r['synergy'] * 100:+.0f}pp", showarrow=False,
                           font=dict(color=INK, size=11),
                           xanchor="left" if r["synergy"] > 0 else "right")
fig.add_vline(x=0, line=dict(color=INK, width=2, dash="dash"),
              annotation_text="no synergy", annotation_position="top",
              annotation_font=dict(color=INK))
fig.update_layout(
    height=28 * len(show) + 120, margin=dict(l=60, r=60, t=40, b=40),
    xaxis_title="win rate above the baseline (percentage points)",
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK), xaxis=dict(gridcolor="#2E2C27", zeroline=False),
    yaxis=dict(gridcolor="rgba(0,0,0,0)"),
)
st.plotly_chart(fig, width='stretch')
st.caption(
    "Each bar is a 95% interval on the synergy, filled dots are the pairs that clear p < 0.05. "
    "Bars crossing the dashed line are consistent with the pair being exactly the sum of its "
    "parts — which is most of them, and the honest reason this leaderboard is for bragging "
    "rather than for drafting."
)

# ---------------------------------------------------------------- expected vs actual
st.subheader("Two good players, or a good pairing?")
scatter = go.Figure()
scatter.add_trace(go.Scatter(
    x=[0, 100], y=[0, 100], mode="lines", line=dict(color=NEUTRAL, width=2, dash="dash"),
    showlegend=False, hoverinfo="skip",
))
scatter.add_trace(go.Scatter(
    x=[r["expected"] * 100 for r in rows], y=[r["win_rate"] * 100 for r in rows],
    mode="markers",
    marker=dict(color=ACCENT, opacity=0.7, size=[6 + 1.1 * r["games"] for r in rows],
                line=dict(color=theme.color("off_black"), width=2)),
    customdata=[[f"{r['player_a']} + {r['player_b']}", r["games"], r["wins"], r["losses"],
                 r["synergy"] * 100] for r in rows],
    hovertemplate=("%{customdata[0]}<br>%{customdata[2]}–%{customdata[3]} in %{customdata[1]} games"
                   "<br>baseline %{x:.0f}%, actual %{y:.0f}%"
                   "<br>synergy %{customdata[4]:+.1f}pp<extra></extra>"),
    showlegend=False,
))
scatter.add_annotation(x=18, y=92, text="won more than expected", showarrow=False,
                       font=dict(color=INK, size=12), xanchor="left")
scatter.add_annotation(x=92, y=8, text="won less than expected", showarrow=False,
                       font=dict(color=INK, size=12), xanchor="right")
scatter.update_layout(
    height=520, margin=dict(l=10, r=10, t=30, b=40),
    xaxis=dict(title="baseline win rate (%)", range=[0, 100], gridcolor="#2E2C27",
               constrain="domain"),
    yaxis=dict(title="actual win rate together (%)", range=[0, 100], gridcolor="#2E2C27"),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color=INK),
)
st.plotly_chart(scatter, width='stretch')

baseline_spread = max(r["expected"] for r in rows) - min(r["expected"] for r in rows)
st.caption(
    "Marker size is games together. On the dashed line, a pair did exactly what its members' other "
    "games predicted — vertical distance from it is what is left over for chemistry, horizontal "
    "spread is how much the baseline thought the pairing was worth before a ball was thrown. "
    + ("**The column shape is the finding here:** the fitted baseline puts nearly every pair within "
       f"{baseline_spread * 100:.0f} points of a coin flip, so essentially all the variation is "
       "vertical — luck, not stacked talent."
       if baseline_spread < 0.15 else
       "Points far to the right that fall short of the line are the pairs whose reputations are "
       "doing the work.")
)

# ---------------------------------------------------------------- per player
st.divider()
st.subheader("Look up a player")
names = sorted(df["player"].unique())
who = st.selectbox("Player", names)
mine = chemistry.player_pair_records(matches, who, min_games=min_games, rows=rows)
if mine:
    st.dataframe(
        pd.DataFrame([{
            "teammate": r["teammate"],
            "games": r["games"],
            "together": f"{r['wins']}–{r['losses']} ({r['win_rate']:.0%})",
            "baseline": round(r["expected"] * 100, 1),
            "synergy (pp)": round(r["synergy"] * 100, 1),
            "teammate apart from you": (f"{r['teammate_apart_rate']:.0%}"
                                        if r["teammate_apart_rate"] is not None else "—"),
        } for r in mine]),
        width='stretch', hide_index=True,
    )
    st.caption("Sorted by synergy, so a teammate does not top the list merely for being good.")
else:
    st.info(f"{who} has no teammate with {min_games}+ shared games.")

with st.expander("Method — why the numbers are presented this way"):
    st.markdown(f"""
There are **{len(chemistry.pair_records(matches, min_games=1, side_list=side_list))} distinct
teammate pairs** across {len(matches)} matches, and roughly half have played together exactly once.
A raw win-rate leaderboard over that is misleading twice over.

**It is mostly noise.** With hundreds of pairs to scan, dozens will show a lopsided record from
luck alone. At exactly {min_games} games a pair needs to top
**{chemistry.significant_threshold(min_games):.0%}** before its record is distinguishable from a
coin.

**It is mostly not about the pair.** Two 60% players will post a good record together whether or
not they have ever spoken, so ranking pairs by win rate is a ranking of individual records with
extra steps. Hence the baseline, and five choices that follow from it:

- **The baseline is refitted without the pair's own games.** A pair's wins together are already
  inside both players' individual records — leaving them in would let the pair fund its own
  expectation and hand back zero synergy by construction. It also means a player whose games are
  *all* with one partner falls back to average, which is the honest reading of "how good are they
  apart".
- **Ratings are ridge-penalised, with the penalty chosen by marginal likelihood.** One free
  parameter per player against {len(matches)} matches fits the season perfectly and predicts
  nothing. The evidence picks the shrinkage instead of taste doing it. The face-value baseline is
  offered as the opposite extreme: every record believed in full.
- **Wilson intervals, not point estimates.** At small samples the textbook normal interval
  misbehaves badly (a 5–0 pair gets a 100% win rate with zero width). Wilson stays sane at the edges.
- **Poisson-binomial p-values.** Once each match has its own baseline odds, a pair's games are no
  longer exchangeable coins, so the null is built by convolution rather than by the binomial formula.
- **A whole-season bootstrap and a cohesion test for the global question.** All 15 pairs on a team
  share one result, so pair records are heavily correlated; the bootstrap simulates entire matches
  at their baseline odds to preserve that. And estimating 850 pair effects from {len(matches)}
  outcomes has almost no power, so the cohesion test asks the single question "does the side with
  more shared history beat its baseline?" — one parameter instead of 850.

Power is the honest caveat throughout: a null result at this sample size rules out a *large*
friendship buff, not a small one.
""")
