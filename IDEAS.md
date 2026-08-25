# Ideas Backlog

A shortlist of things worth building, roughly smallest effort first. Nothing here is
committed — it's a menu.

Sizes: **S** = an evening, **M** = a weekend, **L** = a real project.

---

## Tier 0 — Bugs and papercuts

- [ ] **Match IDs sort as strings.** `1009058275` is our newest match, but string-sorting
      puts it below every 8-digit ID, so "Recent matches" on Home and the top of the Match
      Log are hiding it. Cast to `int` on load. `Home.py:32`, `pages/1_Match_Log.py:13`. **S**
- [ ] **`draft_slot` is hardcoded to `None` for new matches** (`pages/4_Add_Match.py:190`).
      All 82 imported matches have slots 1–12; every match added since loses it. One form
      field to stop the bleed. **S**
- [ ] **`plr_damage_k` and `healing_k` are entered but never displayed anywhere.** We pay
      the data-entry cost and show none of it. Add to player detail + hero tables as
      per-minute rates, alongside the souls/obj-damage rates that already exist. **S**

## Tier 1 — Surface what we already have

- [ ] **Per-minute everything.** `souls_per_min` and `obj_dmg_per_min` exist in
      `matches_to_rows_df` but only appear on two tables. Damage/min and healing/min are
      one line each and make roles comparable across 25-minute stomps and 45-minute slogs. **S**
- [ ] **Lobby-relative stats.** Raw KP% and souls/min are hard to read cold. Show each
      player's value as a delta vs. the lobby average *for that match*, then average the
      deltas. Answers "do I farm well?" instead of "did I play in long games?" **S**
- [ ] **Sortable, formatted tables.** The dataframes are readable but unranked — add
      medal/rank columns, color-scale the win-rate column, freeze the name column. `theme.py`
      already solved contrast-safe hero colors; this is where that pays off. **S**
- [ ] **Match Log readability.** Two side-by-side team tables with hero portraits and the
      winner highlighted, instead of two stacked generic dataframes. **S–M**

## Tier 2 — Fun, social, and bragging rights

- [ ] **Player card.** One screenshot-able block per person: portrait of their top hero,
      W/L, rank badge, signature hero, MVP count, one weird stat. Built for pasting into
      Discord. **M**
- [ ] **Awards / superlatives page.** Auto-computed, deliberately unserious: Farm King
      (souls/min), Feeding Frenzy (most deaths), Pacifist (lowest damage), One-Trick (lowest
      hero variety), Coin Flip (win rate closest to 50%), Ironman (most games). Regenerate
      each session so they rotate. **M**
- [ ] **Streaks and records.** Longest win/loss streak, best single-game KDA, biggest souls
      lead, fastest and longest games. Cheap to compute, disproportionately fun. **S–M**
- [ ] **Head-to-head.** Pick two players: record when on the same team vs. opposite sides.
      Settles arguments; generates new ones. **M**
- [ ] **"Since last week" digest.** After the API date backfill (Tier 4), a Home block
      showing what moved: biggest win-rate swing, new hero picks, streaks broken. Gives
      people a reason to open the app between sessions. **M**

## Tier 3 — Statistical depth

The group can handle real methods; these mostly need a short "here's what this means" caption
rather than simplification.

- [ ] **Shrunk win rates (empirical Bayes).** 80 distinct players, only ~30 with 10+ games.
      The leaderboard currently gates at `MIN_GAMES = 10`, which is honest but throws away
      the tail. Shrinking each player toward the global mean with a Beta prior fit on the
      observed distribution keeps everyone on one board and stops 3-0 players from topping it.
      Show raw and shrunk side by side — the gap between them is itself interesting. **M**
- [ ] **Uncertainty as a first-class visual.** Bootstrap or Beta-posterior intervals drawn
      as error bars / a caterpillar plot instead of point estimates. The single best cure for
      "why is my win rate bouncing around." Also the most useful dataviz exercise on this
      list. **M**
- [ ] **Elo or TrueSkill over match order.** Per-player rating updated match by match, with
      a rating-history chart. Fixed 6v6 in-house games with shuffled rosters is close to the
      ideal setting for this, and it handles opponent strength in a way raw win rate cannot.
      Also gives a defensible auto-balance signal for team-making. **M–L**
- [ ] **Hero strength vs. player skill.** Hero win rates are confounded — good players pick
      certain heroes. A mixed-effects logistic model (random effect per player, fixed effect
      per hero) separates the two and answers "is Wraith strong, or is Sulley strong?" **L**
- [ ] **Synergy and counter matrices.** Pairwise win rate for teammate pairs and opposing
      pairs, against the baseline predicted by each hero's solo rate. Needs shrinkage badly
      at 82 matches — most cells will have 1–3 games — so present it with a sample-size gate
      and an explicit "not enough data" state. **M–L**
- [ ] **Does the draft decide the game?** Logistic regression on draft composition alone
      (heroes + first-pick order + bans), reported as out-of-sample accuracy. If it lands
      near 50%, that's a genuinely fun result to publish: our drafts don't matter. **M**
- [ ] **Rank calibration.** Compare reported Deadlock rank against in-house performance.
      Who over/under-performs their badge? `ranks.json` and `rank_tiers.json` are already
      there and currently power nothing but a table. **M**

## Tier 4 — The big one: auto-import from the Deadlock API

**Verified working 2026-08-25** against match `99935534`:
`https://api.deadlock-api.com/v1/matches/{match_id}/metadata` — no auth, HTTP 200.

The API reproduced our hand-entered row **exactly**: every K/D/A, `net_worth` 45.1k vs. our
typed 45.0, `duration_s` 1895 → 31:35, and `mvp_rank` 1/2/3 matching our MVP and Key Player
flags. It also carries `start_time`, so the date backfill is real.

- [ ] **Backfill match dates.** `start_time` (unix) for all 82 matches. Unblocks every
      calendar-based feature — season splits, "this month," real time-axis charts instead of
      match-order proxies. **S–M**
- [ ] **Replace the 12-player form with "paste a match ID."** K/D/A, souls, heroes, teams,
      win, duration, and MVP all arrive from the API. This is the single biggest
      quality-of-life change available. **M–L**
- [ ] **Two prerequisites**, both one-time:
      - *Identity map.* We key players by nickname, the API keys them by Steam `account_id`.
        Needs a `player → account_id` mapping table, filled in once per person.
      - *Hero aliases.* API says `Mo & Krill`, we say `Mo and Krill`. Small alias map against
        `https://assets.deadlock-api.com/v2/heroes`.
- [ ] **Bans and first picks stay manual.** `banned_hero_ids` came back **empty** — we draft
      on statlocker.gg, outside the game, so the API never sees it. Whatever the import looks
      like, the draft section of the form has to survive. **Worth confirming across a few more
      match IDs before building.**

### Data the API has that we can't currently collect by hand

Available per match, none of it in `matches.json` today:

- `death_details` — killer and timestamp for every death → **first blood, nemesis pairs,
  "who kills you most"**
- `damage_matrix` — who dealt damage to whom → rivalry heatmaps
- `objectives` + `mid_boss` with destruction timings → tower/walker/Rejuv pacing
- `assigned_lane` → lane matchups and lane win rates
- `last_hits` / `denies` / `level` → laning-phase stats we've never had
- `match_paths` — positional traces → movement heatmaps (**L**, and the most visually
  impressive thing on this list)

---

## Notes

- Hosted on Streamlit Cloud, edit-gated by password, read-only for the group — so
  presentation work is worth real investment; everyone sees it.
- `utils/theme.py` already vendors the game's palette with WCAG contrast lifting. New charts
  should pull from it rather than inventing colors.
- At 82 matches, almost every per-hero and per-pair cut is small-sample. Prefer showing
  uncertainty over hiding thin data behind a threshold.
