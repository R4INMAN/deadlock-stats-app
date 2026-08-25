import colorsys

import pandas as pd
import plotly.graph_objects as go
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
st.caption("**Draft participation** = the share of matches where a hero was picked or banned at any point in the draft.")
table = stats.hero_summary_table(df, total_matches, matches=matches, heroes_list=heroes)
display = table.copy()
for c in ["win_rate", "pick_rate", "ban_rate", "first_pick_rate", "draft_participation_rate"]:
    display[c] = (display[c] * 100).round(1)
display["avg_kp_pct"] = display["avg_kp_pct"].round(1)
st.dataframe(
    display[["hero", "games", "win_rate", "draft_participation_rate", "pick_rate", "ban_rate",
              "first_pick_rate", "mvp_count", "key_player_count", "top_player", "top_player_games"]]
    .sort_values("draft_participation_rate", ascending=False),
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Hero detail")
hero_names = sorted(set(df["hero"].unique()) | set(heroes))
chosen = st.selectbox("Select a hero", hero_names)

detail = stats.hero_detail(df, chosen, total_matches, matches=matches)

if detail["games"] == 0 and not detail["ban_rate"]:
    st.info(f"{chosen} hasn't shown up in a draft yet.")
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games played", detail["games"])
    c2.metric("Win rate", f"{detail['win_rate']*100:.1f}%" if detail["win_rate"] is not None else "n/a")
    c3.metric("Pick rate", f"{detail['pick_rate']*100:.1f}%")
    c4.metric("Draft participation", f"{detail['draft_participation_rate']*100:.1f}%")

    if detail["games"]:
        st.markdown("**Who plays this hero**")
        pb = detail["player_breakdown"].copy()
        pb["win_rate"] = (pb["win_rate"] * 100).round(1)
        pb["avg_kp_pct"] = pb["avg_kp_pct"].round(1)
        st.dataframe(pb, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Who the meta is contesting")
st.caption(
    "How often each hero was picked **or** banned, tracked over a rolling window of recent matches. "
    "Only the top 5 at any given point are drawn, so heroes rise into the chart and fall out of it "
    "as the meta shifts. Each line ends at that hero's portrait."
)

TOP_N = 5
max_window = max(5, min(40, total_matches))
default_window = min(25, max_window)
window = st.slider(
    "Smoothing - matches averaged together", min_value=5, max_value=max_window,
    value=default_window, step=1,
    help="A bigger window means a smoother, slower-moving trend. A smaller one reacts faster but is noisier.",
)

timeline = stats.draft_participation_timeline(matches, window=window, top_n=TOP_N)

if timeline.empty:
    st.info("Not enough draft data yet to show a trend. Log a few more matches.")
else:
    chart_heroes = sorted(timeline["hero"].unique())
    visuals = data_io.load_hero_visuals()

    def _brighten(hex_color, floor=0.52):
        """Official hero colors are tuned for the game UI; several are too dark to read as a
        line on a chart. Lift lightness to a floor while keeping the hue that identifies them."""
        h, l, s = colorsys.rgb_to_hls(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
        r, g, b = colorsys.hls_to_rgb(h, max(l, floor), max(s, 0.45))
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    fallback = "#8892a6"
    color_map = {
        h: _brighten((visuals.get(h) or {}).get("color") or fallback)
        for h in chart_heroes
    }

    seqs = sorted(timeline["match_seq"].unique())
    full_index = pd.MultiIndex.from_product([chart_heroes, seqs], names=["hero", "match_seq"])
    pivot = timeline.set_index(["hero", "match_seq"])["participation_rate"].reindex(full_index) * 100

    all_vals = pivot.dropna()
    y_min = max(0, all_vals.min() - 8)
    y_max = min(100, all_vals.max() + 8)
    x_span = max(1, seqs[-1] - seqs[0])
    y_span = max(1, y_max - y_min)

    # Approximate plot box, used to size the portraits squarely in data units.
    plot_w, plot_h = 1080, 470
    icon_px = 34
    size_x = x_span * (icon_px / plot_w)
    size_y = y_span * (icon_px / plot_h)

    fig = go.Figure()
    endpoints = []
    for hero in chart_heroes:
        series = pivot.loc[hero]
        # Smooth inside each contiguous run only - a hero that leaves the top 5 and returns later
        # should show a real gap, not a line interpolated across its absence.
        smoothed = series.copy()
        run = series.notna().ne(series.notna().shift()).cumsum()
        for _, seg in series.groupby(run):
            if seg.notna().all():
                smoothed.loc[seg.index] = seg.ewm(span=5, adjust=False).mean()
                # One portrait per run, so a hero that drops out and climbs back is labelled
                # both times rather than leaving an anonymous stub earlier in the chart.
                endpoints.append((hero, seg.index[-1] + 1, float(smoothed.loc[seg.index[-1]])))

        fig.add_trace(go.Scatter(
            x=[s + 1 for s in smoothed.index], y=smoothed.values,
            mode="lines", name=hero,
            line=dict(width=5, color=color_map[hero], shape="spline", smoothing=1.3),
            connectgaps=False,
            hovertemplate=f"<b>{hero}</b><br>%{{y:.0f}}% of drafts<extra></extra>",
        ))

    # Nudge portraits apart when several lines end at the same place, so none is hidden.
    # Walking bottom-up and pushing each one clear of the highest portrait it collides with
    # makes a stack of overlapping endpoints fan out instead of piling onto one spot.
    endpoints.sort(key=lambda e: e[2])
    for i, (hero, ex, ey) in enumerate(endpoints):
        for _, px_, py_ in endpoints[:i]:
            if abs(ex - px_) < x_span * 0.04 and ey < py_ + size_y:
                ey = py_ + size_y
        endpoints[i] = (hero, ex, ey)

    for hero, ex, ey in endpoints:
        icon = data_io.hero_icon_data_uri((visuals.get(hero) or {}).get("icon"))
        if icon:
            fig.add_layout_image(dict(
                source=icon, xref="x", yref="y", x=ex, y=ey,
                sizex=size_x, sizey=size_y,
                xanchor="center", yanchor="middle", layer="above",
            ))
        else:
            fig.add_annotation(x=ex, y=ey, text=hero, showarrow=False, xanchor="left",
                                xshift=8, font=dict(size=12, color=color_map[hero]))

    fig.update_layout(
        showlegend=False,
        hovermode="closest",
        xaxis=dict(
            title="Match number (oldest to most recent)",
            showgrid=False, zeroline=False, showline=True, linecolor="rgba(128,128,128,0.35)",
            range=[seqs[0] + 1 - x_span * 0.02, seqs[-1] + 1 + x_span * 0.06],
        ),
        yaxis=dict(
            title="Share of drafts picked or banned",
            ticksuffix="%", range=[y_min, y_max],
            gridcolor="rgba(128,128,128,0.18)", zeroline=False,
        ),
        margin=dict(l=70, r=40, t=30, b=60),
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Standings for the panel come from the unfiltered ranking - the chart drops brief
    # appearances to stay readable, but a hero topping the list today still belongs here.
    standings = stats.draft_participation_timeline(matches, window=window, top_n=TOP_N, min_streak=1)
    latest = standings[standings["match_seq"] == standings["match_seq"].max()].sort_values("rank")
    st.markdown(f"**Most contested over the last {window} matches**")
    cols = st.columns(len(latest))
    for col, (_, row) in zip(cols, latest.iterrows()):
        icon_path = data_io.hero_icon_path((visuals.get(row["hero"]) or {}).get("icon"))
        with col:
            if icon_path:
                st.image(icon_path, width=52)
            st.metric(row["hero"], f"{row['participation_rate']*100:.0f}%")

    with st.expander("View underlying data"):
        table_display = timeline.copy()
        table_display["participation_rate"] = (table_display["participation_rate"] * 100).round(1)
        table_display["match_#"] = table_display["match_seq"] + 1
        table_display = table_display.rename(columns={
            "participation_rate": "participation_%",
            "banned": "banned_in_window", "first_pick": "first_picked_in_window", "picked": "picked_in_window",
        })
        st.dataframe(
            table_display[["match_#", "match_id", "rank", "hero", "participation_%",
                            "banned_in_window", "first_picked_in_window", "picked_in_window"]]
            .sort_values(["match_#", "rank"]),
            use_container_width=True, hide_index=True,
        )
