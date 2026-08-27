# Ideas Backlog

A shortlist of things worth building, roughly smallest effort first. Nothing here is
committed — it's a menu.

Sizes: **S** = an evening, **M** = a weekend, **L** = a real project.

---

## Tier 0 — Bugs and papercuts

- [x] **Match IDs sort as strings.** *(done — sorted in `load_matches`)* `100905275` is our newest match, but string-sorting
      puts it below every 8-digit ID, so "Recent matches" on Home and the top of the Match
      Log are hiding it. Cast to `int` on load. `Home.py:32`, `pages/1_Match_Log.py:13`. **S**
- [x] **`draft_slot` is hardcoded to `None` for new matches** (`pages/8_Add_Match.py:198`).
      All 82 imported matches have slots 1–12; every match added since loses it. One form
      field to stop the bleed. **S**
- ~~[ ] **`plr_damage_k` and `healing_k` are entered but never displayed anywhere.** We pay
      the data-entry cost and show none of it. Add to player detail + hero tables as
      per-minute rates, alongside the souls/obj-damage rates that already exist. **S**~~

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

- [x] **Player card.** *(done — `pages/5_Player_Cards.py`)* One screenshot-able block per person: portrait of their top hero,
      W/L, rank badge, signature hero, MVP count, one weird stat. Built for pasting into
      Discord. **M**
- [ ] **Awards / superlatives page.** Auto-computed, deliberately unserious: Farm King
      (souls/min), Feeding Frenzy (most deaths), Pacifist (lowest damage), One-Trick (lowest
      hero variety), Coin Flip (win rate closest to 50%), Ironman (most games). Regenerate
      each session so they rotate. **M**
- [ ] **Streaks and records.** Longest win/loss streak, best single-game KDA, biggest souls
      lead, fastest and longest games. Cheap to compute, disproportionately fun. **S–M**
- [x] **Head-to-head.** *(done — `pages/6_Head_to_Head.py`)* Pick two players: record when on the same team vs. opposite sides.
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
- [~] **~~Elo or TrueSkill over match order.~~** *Declined — we don't want to build our own
      rating system.* The data backs the call anyway: a penalized logistic fit over player
      identity had its cross-validated likelihood maximized by shrinking every rating to
      zero, never beating "always predict 50%". 82 outcomes against 80 players carries no
      identifiable individual signal.
- [ ] **Hero strength vs. player skill.** Hero win rates are confounded — good players pick
      certain heroes. A mixed-effects logistic model (random effect per player, fixed effect
      per hero) separates the two and answers "is Wraith strong, or is Sulley strong?" **L**
- [x] **Synergy and counter matrices.** *(done for players — `pages/7_Chemistry.py`; hero-pair synergy still open)* Pairwise win rate for teammate pairs and opposing
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
**Send a User-Agent.** Python's default `Python-urllib/3.x` is refused with a 403; any
real UA gets 200. Easy to misread as the API having died.

The API reproduced our hand-entered row **exactly**: every K/D/A, `net_worth` 45.1k vs. our
typed 45.0, `duration_s` 1895 → 31:35, and `mvp_rank` 1/2/3 matching our MVP and Key Player
flags. It also carries `start_time`, so the date backfill is real.

- [x] **Backfill match dates.** *(done — all 82, `backfill_match_dates.py`)* Not via the
      per-match endpoint: our PUGs are custom lobbies the API never ingested, so they fall to a
      Steam fetch capped at 3 req/hour per IP, and every Steam fetch attempted returned 503.
      Ruled out along the way — bulk `/v1/matches/metadata` 404s on them, `match-history` across
      all 78 known account_ids covered 0 of 35, and they are absent from `match_salts`,
      `player_match_history` and `match_player` alike. They are simply not in the API's DB.
      What worked: match IDs are sequential in time, so the public Parquet snapshot's 326M
      (match_id, start_time) rows bracket each missing match within seconds. Holdout on the 47
      known: median error 1s, 47/47 correct dates. **S–M**
- [x] **`match_id` 1009058275 could not exist — corrected to `100905275`.** *(done)* The
      largest real match ID on 2026-08-26 was 101,820,190; ours was ten times that, a stray `8`
      typed after `100905`. `100905275` is a PrivateLobby of exactly 23:39 (our recorded game
      length) whose 12 players are *all* known regulars, against 0 overlap for the nearest
      coincidental match. Worth knowing the class exists: a mistyped ID is invisible until
      something tries to look the match up. **S**

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

## Findings so far

**The friendship buff is not detectable in 82 matches.** Every pair is now scored against a
baseline refitted without that pair's own games, so "synergy" means win rate above what the two
players manage apart. Three tests, all null:

- *Cohesion test* — the side whose players had more prior games together won **36 of 81**
  (44.4%) against a 50.6% baseline, p = 0.32. If anything the sign points the wrong way, though
  not significantly.
- *Spread test* — the variation across teammate-pair win rates came in **1.7 SD below** what
  seasons simulated at each match's baseline odds produce (p = 0.98). Pairs are more uniform
  than chance, not less.
- Only **2 of 135** qualifying pairs clear p < 0.05 against the fitted baseline (7 of 135 against
  the credulous face-value one), where chance alone predicts about 7 either way.

Power is the caveat that keeps this honest: at 81 matches there's a 78% chance of catching a
large effect (a 65/35 edge) but only 44% for a moderate one. A null here rules out a *big*
friendship buff, not a subtle one. Revisit at ~200 matches.

Related: **individual player skill is also not identifiable at this sample size.** An
L2-penalized logistic model over player identity had its cross-validated log-likelihood
minimized by shrinking every rating to zero — it never beat "always predict 50%". With 82
binary outcomes and 80 players there simply isn't enough signal — which is a second reason,
beyond not wanting to maintain one, that a homegrown Elo isn't worth building. The marginal
likelihood agrees: over a grid of prior precisions it rises monotonically toward maximum
shrinkage, so the fitted baseline on the Chemistry page sits within a point or two of a coin
flip for everyone.

Stronger still, **win rates point slightly the wrong way.** Scoring each match from win rates
that exclude it, the logistic slope on the two sides' summed rating gap is **−0.60** where 1.0
would mean records predict exactly as advertised (p ≈ 0.06 against coin-flip seasons run through
the same leave-one-out pipeline, which land at −0.06, not 0). Consistent with balanced drafting
plus mean reversion: whoever is hot gets a worse team next week. It also means the usual
objection to the leaderboard — "that pair only looks good because one of them wins a lot" — has
no statistical footing here. What the pair leaderboard actually reflects is 5-game samples: the
top pair, Kobbert + Maeko, is 5–0 together, and Maeko's headline 66.7% win rate *is* those five
games — 42.9% apart from Kobbert.

## Notes

- Hosted on Streamlit Cloud, edit-gated by password, read-only for the group — so
  presentation work is worth real investment; everyone sees it.
- `utils/theme.py` already vendors the game's palette with WCAG contrast lifting. New charts
  should pull from it rather than inventing colors.
- At 82 matches, almost every per-hero and per-pair cut is small-sample. Prefer showing
  uncertainty over hiding thin data behind a threshold.
