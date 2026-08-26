# Deadlock PUG Stats Tracker

## Run it
```
pip install -r requirements.txt
streamlit run Home.py
```

## Structure
- `data/*.json` — your data (matches, players, heroes, rank history). Edit by hand or through the app.
- `utils/data_io.py` — load/save helpers
- `utils/stats.py` — all win rate / ban rate / pick rate / MVP calculations, computed live from matches.json
- `pages/` — the 7 pages: Match Log, Player, Hero Summary, Add Match, Add Player/Hero, Player Ranks, Leaderboard
- `utils/theme.py` — the game's palette, plus the contrast rules that decide when a hero color is safe to show
- `utils/ui.py` — shared page furniture: the header mark, hero portraits, side sigils, award trophies
- `assets/` + `data/palette.json`, `data/hero_visuals.json` — art and colors vendored from the Deadlock assets API
- `.streamlit/config.toml` — the app theme, using the game's own colors
- `fetch_deadlock_assets.py` — re-run to refresh vendored art and colors when Valve adds or reworks heroes
- `convert_csv.py` — the one-time import script that built data/*.json from your old Google Sheet CSVs (kept for reference, not needed to run the app)

Your 82 historical matches, 83 players, and 38 heroes are already imported.

## Art and theming

All art and color come from the community [Deadlock assets API](https://api.deadlock-api.com),
vendored into the repo so no page render needs the network. Refresh it with:

```
python fetch_deadlock_assets.py
```

That pulls each hero's 128px portrait and official color, the two side sigils (the Hidden King's
crown and the Archmother's keyhole hand), the post-game award trophies, Viscous' Puddle Punch
ability icon — the group's mark — and the subset of the game's named colors the theme uses.

One thing worth knowing before changing colors: the game tunes its hero colors for a lit 3D
scene, and flat on a dark page 7 of the 38 fall below a 3:1 contrast ratio, where readable text
wants 4.5:1. `utils/theme.py` lifts lightness until a color clears an actual contrast target,
keeping the hue so heroes stay tellable apart. Get hero colors from `theme.hero_color` /
`theme.hero_text_color` rather than reading `hero_visuals.json` directly.
