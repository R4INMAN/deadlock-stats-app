import streamlit as st
import altair as alt
from utils import data_io, stats, theme, ui

st.set_page_config(page_title="Player Stats", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Player Stats", "Who shows up, who wins, and who they show up as.")

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
display["hero_portrait"] = ui.hero_portrait_column(display["most_played_hero"])
st.dataframe(
    display[["hero_portrait", "player", "games", "win_rate", "hero_variety", "most_played_hero",
              "avg_kp_pct", "avg_souls_per_min", "mvp_count", "key_player_count", "award_rate"]],
    use_container_width=True, hide_index=True,
    column_config={
        "hero_portrait": st.column_config.ImageColumn("", width="small",
                                                       help="Most played hero"),
        "player": st.column_config.TextColumn("Player"),
        "games": st.column_config.NumberColumn("Games"),
        "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
        "hero_variety": st.column_config.NumberColumn("Heroes"),
        "most_played_hero": st.column_config.TextColumn("Most played"),
        "avg_kp_pct": st.column_config.NumberColumn("Avg KP%", format="%.1f"),
        "avg_souls_per_min": st.column_config.NumberColumn("Souls/min", format="%.1f"),
        "mvp_count": st.column_config.NumberColumn("MVP"),
        "key_player_count": st.column_config.NumberColumn("Key player"),
        "award_rate": st.column_config.NumberColumn("Award rate", format="%.1f%%"),
    },
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
    # Lead with the player's signature hero, so the detail view opens on a face rather than
    # on a row of numbers.
    signature = detail["hero_breakdown"].iloc[0]
    st.markdown(
        ui.hero_chip(signature["hero"], size=44,
                     label=f"<b>{chosen}</b> &middot; mostly {signature['hero']} "
                           f"({int(signature['games'])} game{'s' if signature['games'] != 1 else ''})"),
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Games", detail["games"])
    c2.metric("Win rate", f"{detail['win_rate']*100:.1f}%")
    c3.metric("Avg KP%", f"{detail['avg_kp_pct']:.1f}")
    c4.metric("MVPs", detail["mvp_count"])
    c5.metric("Key Player awards", detail["key_player_count"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Avg Souls/min",
              f"{detail['avg_souls_per_min']:.1f}" if detail['avg_souls_per_min'] else "n/a")
    c2.metric("Avg Obj Dmg/min",
              f"{detail['avg_obj_dmg_per_min']:.1f}" if detail['avg_obj_dmg_per_min'] else "n/a")
    c3.metric("Hero variety", detail["hero_variety"])

    if rank:
        st.caption(f"Current reported rank: **{rank}**")
    if notes:
        st.caption(f"Notes: {notes}")

    st.markdown("**Win rate by side**")
    side_display = detail["side_breakdown"].copy()
    side_display["win_rate"] = (side_display["win_rate"] * 100).round(1)
    st.dataframe(
        side_display, use_container_width=True, hide_index=True,
        column_config={
            "team": st.column_config.TextColumn("Side"),
            "games": st.column_config.NumberColumn("Games"),
            "wins": st.column_config.NumberColumn("Wins"),
            "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
        },
    )

    st.markdown("**Heroes played**")
    hero_display = detail["hero_breakdown"].copy()
    hero_display["win_rate"] = (hero_display["win_rate"] * 100).round(1)
    hero_display["avg_kp_pct"] = hero_display["avg_kp_pct"].round(1)
    hero_display["portrait"] = ui.hero_portrait_column(hero_display["hero"])
    st.dataframe(
        hero_display[["portrait", "hero", "games", "wins", "win_rate", "avg_kp_pct",
                       "mvp_count", "key_player_count"]],
        use_container_width=True, hide_index=True,
        column_config={
            "portrait": st.column_config.ImageColumn("", width="small"),
            "hero": st.column_config.TextColumn("Hero"),
            "games": st.column_config.NumberColumn("Games"),
            "wins": st.column_config.NumberColumn("Wins"),
            "win_rate": st.column_config.NumberColumn("Win rate", format="%.1f%%"),
            "avg_kp_pct": st.column_config.NumberColumn("Avg KP%", format="%.1f"),
            "mvp_count": st.column_config.NumberColumn("MVP"),
            "key_player_count": st.column_config.NumberColumn("Key player"),
        },
    )

    st.markdown("**Trend over time**")
    stat_options = {
        "Win rate": "win_rate",
        "Avg KP%": "avg_kp_pct",
        "Avg Souls/min": "avg_souls_per_min",
        "Avg Obj Dmg/min": "avg_obj_dmg_per_min",
        "Avg Kills": "avg_kills",
        "Avg Deaths": "avg_deaths",
        "Avg Assists": "avg_assists",
    }
    c1, c2 = st.columns([2, 1])
    stat_label = c1.selectbox("Stat", list(stat_options.keys()))
    window = c2.number_input("Rolling window (games)", min_value=2, max_value=50, value=10)

    trend = stats.player_stat_over_time(df, chosen, stat=stat_options[stat_label], window=window)
    if trend.empty:
        st.info("Not enough data to chart yet.")
    else:
        long_df = trend.melt(
            id_vars=["game_number"],
            value_vars=["cumulative", "rolling"],
            var_name="series", value_name="value",
        )
        long_df["series"] = long_df["series"].map({
            "cumulative": "Cumulative average",
            "rolling": f"Rolling avg (last {window})",
        })

        # Rolling is the series you actually read, so it gets the brighter of the two side
        # colors; the cumulative baseline sits behind it in the same hue.
        cumulative_label = "Cumulative average"
        rolling_label = f"Rolling avg (last {window})"

        chart = alt.Chart(long_df).mark_bar().encode(
            x=alt.X("game_number:O", title="Game #"),
            xOffset="series:N",
            y=alt.Y("value:Q", title=stat_label),
            color=alt.Color("series:N", title="", scale=alt.Scale(
                domain=[cumulative_label, rolling_label],
                range=[theme.color("team2_color"), theme.color("team2_color_bright")],
            )),
            tooltip=["game_number", "series", alt.Tooltip("value:Q", format=".2f")],
        ).properties(height=400).configure_view(fill=None, stroke=None).configure(
            background="rgba(0,0,0,0)"
        ).configure_axis(
            labelColor=theme.color("base_text"), titleColor=theme.color("base_text"),
        ).configure_legend(
            labelColor=theme.color("base_text"), titleColor=theme.color("base_text"),
        )

        st.altair_chart(chart, use_container_width=True)

ui.brand_footer()
