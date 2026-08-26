"""Shared page furniture: the branded header, hero portraits, and team/hero color accents.

Everything here draws on `theme` for color, so the contrast rules there are the single place
that decides whether a hero's color is safe to show.
"""
import base64
import re

import streamlit as st

from utils import data_io, theme

PUDDLE_PUNCH_ICON = "puddle_punch.png"


def _mask_icon(uri, size, color, opacity=1.0):
    """A single-color silhouette rendered in an arbitrary color.

    The game's icons are white-on-transparent, which is invisible against a dark page. Rather
    than vendor a recolored copy per accent, use the source image as a CSS mask and paint the
    color behind it - one asset, any color, and it stays crisp at any size.
    """
    if not uri:
        return ""
    return (
        f'<span style="display:inline-block;width:{size}px;height:{size}px;'
        f'background-color:{color};opacity:{opacity};vertical-align:middle;'
        f"-webkit-mask:url('{uri}') no-repeat center/contain;"
        f"mask:url('{uri}') no-repeat center/contain;\"></span>"
    )


def puddle_punch_mark(size=34, color=None, opacity=1.0):
    """The group's namesake: Viscous' Puddle Punch ability icon, tinted to the accent color."""
    uri = theme.data_uri(theme.ui_asset_path(PUDDLE_PUNCH_ICON))
    return _mask_icon(uri, size, color or theme.color("viscous_color"), opacity)


def page_header(title, subtitle=None, mark_size=34):
    """Every page opens the same way: the fist, the page name, an optional line of context.

    This replaces the per-page emoji in the titles - one consistent mark reads as a group logo,
    where a different emoji per page reads as seven unrelated pages.
    """
    accent = theme.color("viscous_color")
    text = theme.color("base_text")
    sub = (
        f'<div style="color:{text};opacity:0.6;font-size:0.9rem;margin-top:0.15rem;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.7rem;margin:0.2rem 0 1.1rem;">'
        f"{puddle_punch_mark(mark_size, accent)}"
        f"<div><div style=\"font-size:1.9rem;font-weight:700;line-height:1.15;color:{text};\">{title}</div>"
        f"{sub}</div></div>",
        unsafe_allow_html=True,
    )


def brand_footer():
    """A quiet mark at the bottom of the page, so the theme reads as intentional and not
    as one lonely icon in the header."""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.45rem;opacity:0.35;'
        f'font-size:0.78rem;margin-top:1.4rem;">'
        f'{puddle_punch_mark(14, theme.color("base_text"))}'
        f"<span>Puddle Punch PUGs</span></div>",
        unsafe_allow_html=True,
    )


# --- shared column layouts ----------------------------------------------------------------------

# The match summary table appears on both Home and the Match Log; the `date` column is dropped
# because the imported history has no dates and a column of "None" is worse than no column.
MATCH_SUMMARY_COLUMNS = {
    "match_id": st.column_config.TextColumn("Match"),
    "game_length": st.column_config.TextColumn("Length"),
    "win_side": st.column_config.TextColumn("Won by"),
    "mvps": st.column_config.TextColumn("MVP"),
    "key_players": st.column_config.TextColumn("Key players"),
    "num_players": st.column_config.NumberColumn("Players"),
}


# --- hero portraits ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def hero_portrait_uris():
    """{hero name -> data: URI}, built once per session.

    Data URIs rather than file paths because these go into st.dataframe image columns and into
    raw HTML, neither of which can read from the local filesystem. 38 portraits at ~16KB is
    small enough to hold inline; caching keeps it off every script re-run.
    """
    visuals = data_io.load_hero_visuals()
    uris = {}
    for hero, visual in visuals.items():
        path = data_io.hero_portrait_path((visual or {}).get("portrait"))
        uri = theme.data_uri(path)
        if uri:
            uris[hero] = uri
    return uris


def hero_portrait_column(series):
    """Portrait URIs lined up with a column of hero names, for st.column_config.ImageColumn.

    Heroes with no vendored portrait get None, which the image column renders as an empty cell -
    the row still shows, it just has no picture.
    """
    uris = hero_portrait_uris()
    return series.map(lambda hero: uris.get(hero))


def hero_chip(hero, size=26, label=None, muted_label=False):
    """A hero portrait with its name beside it, for use outside of a dataframe."""
    uri = hero_portrait_uris().get(hero)
    visual = data_io.load_hero_visuals().get(hero)
    text_color = theme.color("base_text")
    img = (
        f'<img src="{uri}" width="{size}" height="{size}" '
        f'style="border-radius:4px;vertical-align:middle;" alt="">'
        if uri else ""
    )
    name = label if label is not None else hero
    opacity = 0.65 if muted_label else 1.0
    return (
        f'<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
        f"{img}"
        f'<span style="color:{text_color};opacity:{opacity};'
        f'border-left:3px solid {theme.hero_color(visual)};padding-left:0.4rem;">{name}</span>'
        f"</span>"
    )


# --- teams ------------------------------------------------------------------------------------

def side_header(team, won=None):
    """A team's name in its own color, behind the sigil the game uses for that side.

    Amber and Sapphire are the only thing in the app with a genuinely fixed identity, so they
    are the one place a strong color is worth spending - it tells you which half of the
    scoreboard you're reading without you having to parse the name.
    """
    color = theme.team_color(team)
    sigil_file = theme.TEAM_SIGILS.get(team)
    uri = theme.data_uri(theme.ui_asset_path(sigil_file), mime="image/svg+xml") if sigil_file else None
    result = ""
    if won is not None:
        label = "WIN" if won else "LOSS"
        # The result chip is filled only on a win, so a scoreboard reads at a glance instead of
        # asking you to compare two equally-weighted badges.
        style = (f"background:{color};color:{theme.color('off_black')};" if won
                 else f"border:1px solid {color};color:{color};")
        result = (f'<span style="{style}font-size:0.68rem;font-weight:700;letter-spacing:0.06em;'
                  f'padding:0.1rem 0.42rem;border-radius:3px;margin-left:0.55rem;">{label}</span>')
    return (
        f'<div style="display:flex;align-items:center;gap:0.5rem;margin:0.9rem 0 0.35rem;">'
        f"{_mask_icon(uri, 22, color)}"
        f'<span style="color:{color};font-weight:700;font-size:1.02rem;">{team}</span>'
        f"{result}</div>"
    )


def side_bar(team, win_rate, wins, games):
    """One side's win rate as a labelled bar in that side's color.

    The bar is drawn against a 0-100% track rather than scaled to the leader, so two sides
    sitting near even look near even instead of looking like a blowout.
    """
    color = theme.team_color(team)
    sigil_file = theme.TEAM_SIGILS.get(team)
    uri = theme.data_uri(theme.ui_asset_path(sigil_file), mime="image/svg+xml") if sigil_file else None
    pct = win_rate * 100
    text = theme.color("base_text")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.6rem;margin:0.35rem 0;">'
        f"{_mask_icon(uri, 20, color)}"
        f'<span style="color:{color};font-weight:600;min-width:8.5rem;">{team}</span>'
        f'<span style="flex:1;height:9px;border-radius:5px;'
        f'background:{theme.color("color_common_dark_gray")};overflow:hidden;">'
        f'<span style="display:block;height:100%;width:{pct:.1f}%;background:{color};"></span>'
        f"</span>"
        f'<span style="color:{text};font-variant-numeric:tabular-nums;min-width:9.5rem;'
        f'text-align:right;">{pct:.1f}%  <span style="opacity:0.5;">({wins}/{games})</span></span>'
        f"</div>",
        unsafe_allow_html=True,
    )


# --- awards ------------------------------------------------------------------------------------

AWARD_ICONS = {"mvp": ("mvp_trophy.svg", "color_gold"),
                "key_player": ("key_player_trophy.svg", "base_text")}


@st.cache_data(show_spinner=False)
def award_icon_uri(award):
    """The game's own trophy for an award, pre-tinted, as a data: URI.

    st.column_config.ImageColumn takes an image per cell and nothing else, so the tint has to be
    baked into the SVG rather than applied with CSS the way _mask_icon does elsewhere.
    """
    icon_file, color_key = AWARD_ICONS[award]
    path = theme.ui_asset_path(icon_file)
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    # The trophies are painted with radial gradients and a drop-shadow filter, tuned to sit on a
    # bright post-game screen; at 20px on a dark table they come out as a faint smudge. Overriding
    # every paint with one flat color turns them back into a legible silhouette. `fill="none"` is
    # left alone - those elements are stroke outlines, and filling them would blot the shape out.
    color = theme.color(color_key)
    flatten = (f"<style>[fill]:not([fill='none']){{fill:{color} !important}}"
               f"[filter]{{filter:none !important}}</style>")
    svg = re.sub(r"(<svg[^>]*>)", lambda m: m.group(1) + flatten, svg, count=1)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def award_column(series, award):
    """Trophy image where the award was won, None elsewhere - an empty cell reads as 'no award'
    more quickly than an unchecked box does."""
    uri = award_icon_uri(award)
    return [uri if bool(v) else None for v in series]
