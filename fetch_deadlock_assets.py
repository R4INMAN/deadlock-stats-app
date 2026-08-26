"""Refresh vendored art + palette from the community Deadlock assets API.

Run manually when Valve adds/reworks heroes:  python fetch_deadlock_assets.py

Vendoring keeps the app working with no network access at page-render time, which matters
because Streamlit re-runs the whole script on every widget interaction - a page that fetched
its own icons would re-fetch them dozens of times per session.

What lands where:
  assets/heroes/<hero>.png   128x128 character portrait (icon_image_small)
  assets/ui/<name>.svg|png   shared UI icons (side sigils, award trophies, the Puddle Punch fist)
  data/hero_visuals.json             per-hero official color + icon filenames
  data/palette.json                  the game's own named colors, filtered to what we theme with
"""
import json
import os
import re
import urllib.request

API = "https://api.deadlock-api.com/v1"
# The assets API and its CDN reject the default urllib agent.
UA = "deadlock-stats-app/1.0 (asset refresh)"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
PORTRAIT_DIR = os.path.join(ROOT, "assets", "heroes")
UI_DIR = os.path.join(ROOT, "assets", "ui")
VISUALS_FILE = os.path.join(DATA_DIR, "hero_visuals.json")
PALETTE_FILE = os.path.join(DATA_DIR, "palette.json")

# Shared UI art, by the name we save it under. The fist is Viscous' Puddle Punch ability icon -
# the group's namesake, and the closest thing the game ships to a logo for us.
UI_ICONS = {
    "puddle_punch": "/images/abilities/viscous/viscous_goo_punch.png",
    "mvp_trophy": "/icons/post_game/mvp_trophy.svg",
    "key_player_trophy": "/icons/post_game/key_player_trophy.svg",
    # The compact side sigils, not hud/core/logo_team*.svg - those are 1280x191 wordmark
    # banners that collapse into a dash at icon size. team1 is the Hidden King's crown,
    # team2 the Archmother's keyhole hand, which is what the group named its sides after.
    "sigil_team1": "/icons/hud/core/team1_icon.svg",
    "sigil_team2": "/icons/hud/core/team2_icon.svg",
}
ASSET_CDN = "https://assets-bucket.deadlock-api.com/assets-api-res"

# The game ships 164 named colors; these are the ones we actually theme with. Pulling them from
# the API rather than hardcoding hexes means a Valve art pass carries into the app for free.
PALETTE_KEYS = [
    "off_black",          # page background
    "base_text",          # warm off-white body text
    "base_border",
    "color_common_dark_gray",
    "color_common_darkest_gray",
    "viscous_color",      # Puddle Punch green - our accent
    "brand_green",
    "color_gold",
    "soul_color",
    "spirit_color",
    "weapon_color",
    "tech_color",
    "team1_color",        # the two sides, straight from the game
    "team1_color_bright",
    "team2_color",
    "team2_color_bright",
    "warning_red",
    "debuff_color",
]
# The game also names a color per rank tier (rank0_color .. rank11_color, matching
# data/rank_tiers.json). Nothing uses them yet; add them back here when Player Ranks gets themed.


def norm(name):
    """'Mo & Krill' / 'The Doorman' -> a key that matches our own hero spellings."""
    n = name.lower().replace("&", "and")
    n = re.sub(r"^the ", "", n)
    return re.sub(r"[^a-z0-9]", "", n)


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}))


def download(url, path):
    with get(url) as resp, open(path, "wb") as out:
        out.write(resp.read())


def hex_of(color):
    return "#%02X%02X%02X" % (color["red"], color["green"], color["blue"])


def fetch_heroes():
    with get(f"{API}/assets/heroes") as resp:
        api_heroes = json.load(resp)
    api_by_key = {norm(h["name"]): h for h in api_heroes if h.get("name")}

    with open(os.path.join(DATA_DIR, "heroes.json")) as f:
        our_heroes = json.load(f)

    visuals, missing = {}, []
    for hero in our_heroes:
        api_hero = api_by_key.get(norm(hero))
        if not api_hero:
            missing.append(hero)
            continue
        images = api_hero.get("images") or {}
        portrait_name = None
        # icon_image_small, not minimap_image: the minimap version is a flat 50px blob built to
        # be read at a glance on a map, and it loses the face that makes a hero recognisable.
        if images.get("icon_image_small"):
            portrait_name = f"{norm(hero)}.png"
            download(images["icon_image_small"], os.path.join(PORTRAIT_DIR, portrait_name))

        visuals[hero] = {
            "color": (api_hero.get("colors") or {}).get("style_hex"),
            "portrait": portrait_name,
        }
        print(f"  {hero:14s} {visuals[hero]['color']}  {portrait_name}")

    with open(VISUALS_FILE, "w") as f:
        json.dump(visuals, f, indent=2, sort_keys=True)
    print(f"Wrote {len(visuals)} heroes to {VISUALS_FILE}")
    if missing:
        print(f"No API match (will fall back to a generated color): {missing}")


def fetch_ui_icons():
    for name, path in UI_ICONS.items():
        ext = os.path.splitext(path)[1]
        download(ASSET_CDN + path, os.path.join(UI_DIR, name + ext))
        print(f"  {name}{ext}")


def fetch_palette():
    with get(f"{API}/assets/colors") as resp:
        colors = json.load(resp)
    palette = {k: hex_of(colors[k]) for k in PALETTE_KEYS if k in colors}
    with open(PALETTE_FILE, "w") as f:
        json.dump(palette, f, indent=2, sort_keys=True)
    missing = [k for k in PALETTE_KEYS if k not in colors]
    print(f"Wrote {len(palette)} colors to {PALETTE_FILE}")
    if missing:
        print(f"  Not in the API any more (theme falls back to its defaults): {missing}")


def main():
    for d in (PORTRAIT_DIR, UI_DIR):
        os.makedirs(d, exist_ok=True)
    print("Heroes:")
    fetch_heroes()
    print("UI icons:")
    fetch_ui_icons()
    print("Palette:")
    fetch_palette()


if __name__ == "__main__":
    main()
