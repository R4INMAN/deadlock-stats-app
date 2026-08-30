import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from utils import data_io, stats, theme, ui

st.set_page_config(page_title="Hero Summary", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Hero Summary", "Pick rates, ban rates, and who the meta is contesting.")

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
display["portrait"] = ui.hero_portrait_column(display["hero"])
st.dataframe(
    display[["portrait", "hero", "games", "win_rate", "draft_participation_rate", "pick_rate",
              "ban_rate", "first_pick_rate", "mvp_count", "key_player_count", "top_player",
              "top_player_games"]]
    # Games, not draft participation: participation counts bans, so a hero the group keeps
    # banning but has barely played was topping a table meant to show who actually gets played.
    .sort_values(["games", "draft_participation_rate"], ascending=[False, False]),
    width='stretch', hide_index=True,
    column_config={
        "portrait": st.column_config.ImageColumn("", width="small"),
        "hero": st.column_config.TextColumn("Hero"),
        "games": st.column_config.NumberColumn("Games"),
        "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
        "draft_participation_rate": st.column_config.NumberColumn("Draft particip.", format="%.1f%%"),
        "pick_rate": st.column_config.NumberColumn("Pick rate", format="%.1f%%"),
        "ban_rate": st.column_config.NumberColumn("Ban rate", format="%.1f%%"),
        "first_pick_rate": st.column_config.NumberColumn("First pick", format="%.1f%%"),
        "mvp_count": st.column_config.NumberColumn("MVP"),
        "key_player_count": st.column_config.NumberColumn("Key player"),
        "top_player": st.column_config.TextColumn("Top player"),
        "top_player_games": st.column_config.NumberColumn("Their games"),
    },
)

st.divider()
st.subheader("Hero detail")
hero_names = sorted(set(df["hero"].unique()) | set(heroes))
chosen = st.selectbox("Select a hero", hero_names)

detail = stats.hero_detail(df, chosen, total_matches, matches=matches)

if detail["games"] == 0 and not detail["ban_rate"]:
    st.info(f"{chosen} hasn't shown up in a draft yet.")
else:
    st.markdown(ui.hero_chip(chosen, size=44, label=f"<b>{chosen}</b>"), unsafe_allow_html=True)

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
        st.dataframe(
            pb, width='stretch', hide_index=True,
            column_config={
                "player": st.column_config.TextColumn("Player"),
                "games": st.column_config.NumberColumn("Games"),
                "wins": st.column_config.NumberColumn("Wins"),
                "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
                "avg_kp_pct": st.column_config.NumberColumn("Avg KP%", format="%.1f"),
            },
        )

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

    # A chart line is a graphical object, so it only has to clear 3:1 - but these lines sit
    # against each other as much as against the background, so they get the stricter text
    # target to keep five of them tellable apart.
    color_map = {h: theme.hero_text_color(visuals.get(h)) for h in chart_heroes}

    seqs = sorted(timeline["match_seq"].unique())
    full_index = pd.MultiIndex.from_product([chart_heroes, seqs], names=["hero", "match_seq"])
    pivot = timeline.set_index(["hero", "match_seq"])["participation_rate"].reindex(full_index) * 100

    all_vals = pivot.dropna()
    x_span = max(1, seqs[-1] - seqs[0])

    # Approximate plot box, used to size the portraits squarely in data units. Each portrait
    # sits on a slightly larger disc, and that disc - not the icon - is what has to clear its
    # neighbours, so spacing is derived from it rather than from a hand-tuned constant.
    plot_w, plot_h = 1080, 470
    icon_px = 34
    disc_px = icon_px + 7

    # The axis is padded past the data by half a portrait, so a disc sitting on a line that
    # touches 100% isn't sliced off by the top of the plot. Ticks stay inside 0-100 so the
    # padding never shows up as a meaningless "105%" label.
    pad = max(1.0, (all_vals.max() - all_vals.min()) * 0.10)
    tick_lo = max(0.0, all_vals.min() - pad)
    tick_hi = min(100.0, all_vals.max() + pad)
    disc_h = max(1.0, tick_hi - tick_lo) * (disc_px / plot_h)
    y_min = tick_lo - disc_h * 0.75
    y_max = tick_hi + disc_h * 0.75
    y_span = max(1, y_max - y_min)

    tick_step = 5 if (tick_hi - tick_lo) <= 50 else 10
    tick_vals = [t for t in range(0, 101, tick_step) if y_min <= t <= y_max]

    size_x = x_span * (icon_px / plot_w)
    size_y = y_span * (icon_px / plot_h)

    x_axis_lo = seqs[0] + 1 - x_span * 0.02
    x_axis_hi = seqs[-1] + 1 + x_span * 0.06
    x_axis_span = max(1e-9, x_axis_hi - x_axis_lo)

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
                smooth_seg = seg.ewm(span=5, adjust=False).mean()
                smoothed.loc[seg.index] = smooth_seg
                # One portrait per run, so a hero that drops out and climbs back is labelled
                # both times rather than leaving an anonymous stub earlier in the chart. The
                # whole run is kept, because a crowded portrait slides back along it.
                endpoints.append({
                    "hero": hero,
                    "points": [(int(i) + 1, float(v)) for i, v in smooth_seg.items()],
                })

        fig.add_trace(go.Scatter(
            x=[s + 1 for s in smoothed.index], y=smoothed.values,
            mode="lines", name=hero,
            line=dict(width=5, color=color_map[hero], shape="spline", smoothing=1.3),
            connectgaps=False,
            hovertemplate=f"<b>{hero}</b><br>%{{y:.0f}}% of drafts<extra></extra>",
        ))

    # Place each portrait on its own line rather than beside it: start at the line's end and,
    # if that spot is already taken, walk backwards along the line until the portrait clears
    # its neighbours. Because every candidate is a point on the curve, the portrait always sits
    # on the line it belongs to - no connector needed to explain which line it labels - and a
    # crowded pair separates along the direction its lines are already travelling.
    def to_px(x, y):
        return ((x - x_axis_lo) / x_axis_span * plot_w, (y - y_min) / y_span * plot_h)

    min_sep = disc_px + 2
    placed_px = []
    # Rightmost first, lowest first among ties, so the most recent point keeps the line's end
    # and everything crowding it is the thing that gives way.
    for ep in sorted(endpoints, key=lambda e: (-e["points"][-1][0], e["points"][-1][1])):
        best, best_clearance = None, -1.0
        for cx, cy in reversed(ep["points"]):
            cpx, cpy = to_px(cx, cy)
            clearance = min(
                (math.hypot(cpx - qx, cpy - qy) for qx, qy in placed_px),
                default=math.inf,
            )
            if clearance > best_clearance:
                best, best_clearance = (cx, cy, cpx, cpy), clearance
            if clearance >= min_sep:
                break
        cx, cy, cpx, cpy = best
        placed_px.append((cpx, cpy))
        ep["label_x"], ep["label_y"] = cx, cy

    fig.add_trace(go.Scatter(
        x=[ep["label_x"] for ep in endpoints], y=[ep["label_y"] for ep in endpoints],
        mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(size=disc_px, color=[color_map[ep["hero"]] for ep in endpoints],
                     line=dict(width=0)),
    ))

    for ep in endpoints:
        hero, ex, ey = ep["hero"], ep["label_x"], ep["label_y"]
        icon = ui.hero_portrait_uris().get(hero)
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
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.color("base_text")),
        showlegend=False,
        hovermode="closest",
        xaxis=dict(
            title="Match number (oldest to most recent)",
            showgrid=False, zeroline=False, showline=True, linecolor="rgba(128,128,128,0.35)",
            range=[x_axis_lo, x_axis_hi],
        ),
        yaxis=dict(
            title="Share of drafts picked or banned",
            range=[y_min, y_max],
            # ticksuffix is ignored under tickmode="array", so the % goes in the label text.
            tickmode="array", tickvals=tick_vals, ticktext=[f"{t}%" for t in tick_vals],
            gridcolor="rgba(128,128,128,0.18)", zeroline=False,
        ),
        margin=dict(l=70, r=40, t=30, b=60),
        height=520,
    )
    st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})

    # Standings for the panel come from the unfiltered ranking - the chart drops brief
    # appearances to stay readable, but a hero topping the list today still belongs here.
    standings = stats.draft_participation_timeline(matches, window=window, top_n=TOP_N, min_streak=1)
    latest = standings[standings["match_seq"] == standings["match_seq"].max()].sort_values("rank")
    st.markdown(f"**Most contested over the last {window} matches**")
    cols = st.columns(len(latest))
    for col, (_, row) in zip(cols, latest.iterrows()):
        portrait_path = data_io.hero_portrait_path((visuals.get(row["hero"]) or {}).get("portrait"))
        with col:
            if portrait_path:
                st.image(portrait_path, width=52)
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
            width='stretch', hide_index=True,
        )

ui.brand_footer()
