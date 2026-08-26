"""One screenshot-able block per player - built to be pasted into Discord, not scrolled past."""
import streamlit as st

from utils import chemistry, data_io, stats, theme, ui

st.set_page_config(page_title="Player Cards", page_icon="🪪", layout="wide")
st.title("🪪 Player Cards")

matches = data_io.load_matches()
players = data_io.load_players()
ranks = data_io.load_ranks()
visuals = data_io.load_hero_visuals()

if not matches:
    st.info("No matches logged yet.")
    st.stop()

df = stats.matches_to_rows_df(matches)
names = sorted(df["player"].unique())
# Open on whoever has played most, rather than whoever is alphabetically first.
most_played = df["player"].value_counts().index[0]
chosen = st.selectbox("Player", names, index=names.index(most_played))

pdf = df[df["player"] == chosen]
detail = stats.player_detail(df, chosen, len(matches))
rank = data_io.current_rank(chosen, ranks)
notes = players.get(chosen, {}).get("notes", "")

hero_counts = pdf["hero"].value_counts()
signature = hero_counts.index[0]
sig_games = int(hero_counts.iloc[0])
sig_visual = visuals.get(signature, {})
# Via theme rather than straight off the visual: a few of the official hero colors are too dark
# to read on this page's background, and theme lifts those while keeping the hue.
accent = theme.hero_color(sig_visual)
accent_text = theme.hero_text_color(sig_visual)
portrait = ui.hero_portrait_uris().get(signature)

wins = int(pdf["win"].sum())
games = len(pdf)
losses = games - wins

# Best teammate, by the same 5-game floor the Chemistry page uses. Shown with its record so
# the number is never presented as more solid than it is.
mates = chemistry.player_pair_records(matches, chosen, min_games=5)
best_mate = mates[0] if mates else None

st.markdown(
    f"""
<div style="border:1px solid #333;border-left:6px solid {accent};border-radius:10px;
            padding:18px 22px;background:linear-gradient(90deg,{accent}14,transparent 60%);">
  <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;">
    {f'<img src="{portrait}" style="width:64px;height:64px;border-radius:8px;">' if portrait else ''}
    <div>
      <div style="font-size:1.9rem;font-weight:700;line-height:1.1;">{chosen}</div>
      <div style="opacity:.75;font-size:.95rem;">
        {rank or 'unranked'} &nbsp;·&nbsp; signature hero <b style="color:{accent_text};">{signature}</b> ({sig_games}g)
      </div>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Record", f"{wins}–{losses}")
c2.metric("Win rate", f"{detail['win_rate']*100:.1f}%")
c3.metric("MVPs", detail["mvp_count"])
c4.metric("Key player", detail["key_player_count"])
c5.metric("Heroes played", detail["hero_variety"])

c1, c2, c3 = st.columns(3)
c1.metric("Avg KP%", f"{detail['avg_kp_pct']:.1f}")
c2.metric("Souls/min", f"{detail['avg_souls_per_min']:.1f}" if detail["avg_souls_per_min"] else "n/a")
c3.metric(
    "Best teammate",
    best_mate["teammate"] if best_mate else "—",
    f"{best_mate['wins']}–{best_mate['losses']} together" if best_mate else None,
)

# A player's win rate is a small sample too - 39 games still spans roughly +/-15 points.
lo, hi = chemistry.wilson_interval(wins, games)
st.caption(
    f"Win rate 95% interval: **{lo:.1%} – {hi:.1%}** over {games} games. "
    f"{'Clear of a coin flip.' if lo > 0.5 or hi < 0.5 else 'Overlaps 50%, so treat the headline number as a range, not a verdict.'}"
)
if notes:
    st.caption(f"Notes: {notes}")

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Hero pool")
    hb = detail["hero_breakdown"].copy()
    hb["win_rate"] = (hb["win_rate"] * 100).round(1)
    hb["avg_kp_pct"] = hb["avg_kp_pct"].round(1)
    st.dataframe(
        hb[["hero", "games", "wins", "win_rate", "avg_kp_pct", "mvp_count"]],
        use_container_width=True, hide_index=True,
    )

with right:
    st.subheader("Who they win with")
    if mates:
        st.dataframe(
            [{
                "teammate": r["teammate"],
                "games": r["games"],
                "record": f"{r['wins']}–{r['losses']}",
                "win_rate": round(r["win_rate"] * 100, 1),
            } for r in mates],
            use_container_width=True, hide_index=True,
        )
        st.caption("Minimum 5 games together. See **Chemistry** for how much of this is real.")
    else:
        st.info(f"{chosen} has no teammate with 5+ shared games yet.")
