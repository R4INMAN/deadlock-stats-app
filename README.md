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
- `pages/` — the 6 pages: Match Log, Player, Hero Summary, Add Match, Add Player/Hero, Player Ranks
- `convert_csv.py` — the one-time import script that built data/*.json from your old Google Sheet CSVs (kept for reference, not needed to run the app)

Your 82 historical matches, 83 players, and 38 heroes are already imported.
