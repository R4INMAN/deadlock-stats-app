"""Deadlock's own palette and art, plus the contrast rules that make them safe to use.

The colors and images all come from the game (vendored by fetch_deadlock_assets.py), so the app
reads as Deadlock rather than as default Streamlit. But the game tunes its hero colors for a
dark 3D scene with glow behind it, and a lot of them are far too dark to read as flat UI on a
web page - Calico's purple lands at 1.9:1 against the background, where readable body text wants
4.5:1. So nothing here hands out a raw hero color: `hero_color` lifts it until it actually
clears a contrast target, keeping the hue that identifies the hero.
"""
import base64
import colorsys
import functools
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALETTE_FILE = os.path.join(ROOT_DIR, "data", "palette.json")
UI_DIR = os.path.join(ROOT_DIR, "assets", "ui")

# Used when the palette file is missing or the game drops a color name - the app should still
# render, just without that particular flourish.
PALETTE_FALLBACK = {
    "off_black": "#10130D",
    "base_text": "#FFEFD7",
    "base_border": "#444444",
    "color_common_dark_gray": "#2E2C27",
    "viscous_color": "#319826",
    "color_gold": "#FFED79",
    "soul_color": "#70F8C1",
    "team1_color": "#D4860B",
    "team2_color": "#4D75C3",
}
NEUTRAL_HERO_COLOR = "#8892A6"

# Contrast ratios from WCAG 2.1: 4.5:1 is the bar for body text, 3:1 for large text and for
# graphical objects like a chart line or an icon.
TEXT_CONTRAST = 4.5
GRAPHIC_CONTRAST = 3.0


@functools.lru_cache(maxsize=1)
def palette():
    """The game's named colors, as vendored. Falls back per-key, not all-or-nothing."""
    colors = dict(PALETTE_FALLBACK)
    if os.path.exists(PALETTE_FILE):
        with open(PALETTE_FILE) as f:
            colors.update(json.load(f))
    return colors


def color(name):
    return palette().get(name, PALETTE_FALLBACK.get(name, NEUTRAL_HERO_COLOR))


# --- contrast ---------------------------------------------------------------------------------

def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(*(round(max(0.0, min(1.0, c)) * 255) for c in (r, g, b)))


def _relative_luminance(hex_color):
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def readable(hex_color, background=None, target=GRAPHIC_CONTRAST):
    """The same hue, lightened until it clears `target` contrast against `background`.

    Bisects on HLS lightness rather than blending toward white, which would wash the hue out and
    make two heroes that started far apart converge on the same pale pastel. A muted-but-tinted
    color gets a saturation floor for the same reason - it would otherwise lift into flat grey.
    """
    background = background or color("off_black")
    if contrast_ratio(hex_color, background) >= target:
        return hex_color

    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_color))
    # A true grey (Sinclair's #6B6B6B) has no hue to protect, and HLS reports its hue as 0 -
    # so applying the floor would invent a saturated red out of nothing. Leave greys grey.
    if s > 0.05:
        s = max(s, 0.45)
    # White always clears a dark background, so a solution exists in [l, 1.0] and 12 halvings
    # land well inside a single 8-bit step.
    lo, hi = l, 1.0
    for _ in range(12):
        mid = (lo + hi) / 2
        candidate = _hex(*colorsys.hls_to_rgb(h, mid, s))
        if contrast_ratio(candidate, background) >= target:
            hi = mid
        else:
            lo = mid
    return _hex(*colorsys.hls_to_rgb(h, hi, s))


def hero_color(visual, target=GRAPHIC_CONTRAST, background=None):
    """Readable accent color for a hero, given its entry from hero_visuals.json (or None)."""
    raw = (visual or {}).get("color") or NEUTRAL_HERO_COLOR
    return readable(raw, background=background, target=target)


def hero_text_color(visual, background=None):
    """As above, but cleared for use as actual text."""
    return hero_color(visual, target=TEXT_CONTRAST, background=background)


# --- team colors ------------------------------------------------------------------------------

# The two sides in Deadlock are Amber and Sapphire; this group renames them after the patrons.
# Anything not one of those two (an old or one-off side name) falls through to a neutral.
TEAM_COLOR_KEYS = {
    "Hidden King": "team1_color",
    "Amber Hand": "team1_color",
    "Archmother": "team2_color",
    "Sapphire Flame": "team2_color",
}
TEAM_SIGILS = {
    "Hidden King": "sigil_team1.svg",
    "Amber Hand": "sigil_team1.svg",
    "Archmother": "sigil_team2.svg",
    "Sapphire Flame": "sigil_team2.svg",
}


def team_color(team, target=GRAPHIC_CONTRAST):
    key = TEAM_COLOR_KEYS.get(team)
    return readable(color(key), target=target) if key else NEUTRAL_HERO_COLOR


# --- ui art -----------------------------------------------------------------------------------

def ui_asset_path(name):
    path = os.path.join(UI_DIR, name)
    return path if os.path.exists(path) else None



@functools.lru_cache(maxsize=128)
def data_uri(path, mime="image/png"):
    """A local image as a data: URI - needed anywhere the bytes must be inline (Plotly, raw HTML)."""
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
