"""Refresh vendored hero colors + minimap icons from the community Deadlock assets API.

Run manually when Valve adds/reworks heroes:  python fetch_hero_assets.py
Vendoring keeps the app working with no network access at page-render time.
"""
import json
import os
import re
import urllib.request

API_URL = "https://api.deadlock-api.com/v1/assets/heroes"
# The assets API and its CDN reject the default urllib agent.
UA = "deadlock-stats-app/1.0 (hero asset refresh)"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
ICON_DIR = os.path.join(ROOT, "assets", "heroes")
VISUALS_FILE = os.path.join(DATA_DIR, "hero_visuals.json")


def norm(name):
    """'Mo & Krill' / 'The Doorman' -> a key that matches our own hero spellings."""
    n = name.lower().replace("&", "and")
    n = re.sub(r"^the ", "", n)
    return re.sub(r"[^a-z0-9]", "", n)


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}))


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    with get(API_URL) as resp:
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
        color = (api_hero.get("colors") or {}).get("style_hex")
        minimap_url = (api_hero.get("images") or {}).get("minimap_image")
        icon_name = None
        if minimap_url:
            icon_name = f"{norm(hero)}.png"
            with get(minimap_url) as img, open(os.path.join(ICON_DIR, icon_name), "wb") as out:
                out.write(img.read())
        visuals[hero] = {"color": color, "icon": icon_name}
        print(f"{hero:14s} {color}  {icon_name}")

    with open(VISUALS_FILE, "w") as f:
        json.dump(visuals, f, indent=2, sort_keys=True)

    print(f"\nWrote {len(visuals)} heroes to {VISUALS_FILE}")
    if missing:
        print(f"No API match (will fall back to a generated color): {missing}")


if __name__ == "__main__":
    main()
