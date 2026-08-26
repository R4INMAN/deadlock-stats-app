"""The "friendship buff": do certain people win more when they play together?

The tempting version of this page is a big grid of pair win rates, sorted, with the top of
the list crowned. That grid is mostly noise, and it is worth being precise about why.

There are 850 distinct teammate pairs in 82 matches. Nearly half of them have played
together exactly once. Even for a pair with 10 games, a 50/50 coin lands outside 19%-81%
about one time in twenty - so with 850 pairs to look at, dozens will show a "huge" edge
that is nothing but variance. Ranking pairs by raw win rate and reading the top of the list
is close to a machine for manufacturing false friendships.

So this module does three things:

1. `pair_records` - the raw counts, with a Wilson confidence interval, so a pair's record is
   always shown next to how much it is worth trusting.
2. `chemistry_test` - a parametric bootstrap answering the global question: is there MORE
   spread across pairs than coin-flips alone would produce? This is the honest version of
   "is the friendship buff real", and it costs nothing to be wrong about a single pair.
3. `cohesion_test` - a far better-powered test of the same theory. Instead of estimating 850
   pair effects from 82 outcomes, it asks one question: does the side with more shared
   history win more often? One parameter against 82 matches has real statistical power,
   where the per-pair view has almost none.

Everything here is computed from match results alone; no per-player stats are involved.
"""
import collections
import itertools
import math

import numpy as np

MIN_GAMES_DEFAULT = 5


def _sides(matches):
    """(team_a_names, team_b_names, team_a_won) per match, skipping malformed rosters."""
    out = []
    for m in matches:
        byteam = collections.defaultdict(list)
        for p in m["players"]:
            byteam[p["team"]].append(p)
        if len(byteam) != 2:
            continue
        names = sorted(byteam)
        a, b = byteam[names[0]], byteam[names[1]]
        out.append((
            sorted(p["player"] for p in a),
            sorted(p["player"] for p in b),
            bool(a[0]["win"]),
        ))
    return out


def wilson_interval(wins, n, z=1.96):
    """Wilson score interval - behaves sanely at small n and at 0%/100%, where the textbook
    normal interval produces nonsense like a 100% win rate with zero width."""
    if n == 0:
        return (0.0, 1.0)
    phat = wins / n
    denom = 1 + z**2 / n
    centre = (phat + z**2 / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def significant_threshold(n, z=1.96):
    """The win rate a pair with n games must beat before it is distinguishable from a coin.

    This is the number that makes the noise problem concrete: at 5 games together you need
    to have won essentially all of them, which is why a 5-game minimum filters volume but
    not luck.
    """
    if n <= 0:
        return 1.0
    return 0.5 + z * math.sqrt(0.25 / n)


def pair_records(matches, min_games=MIN_GAMES_DEFAULT):
    """Every teammate pair's record together, filtered to min_games.

    Returns a list of dicts sorted by win rate, then by games played, so that a pair with a
    longer track record outranks a short hot streak at the same rate.
    """
    n = collections.Counter()
    w = collections.Counter()
    for a, b, a_won in _sides(matches):
        for team, won in ((a, a_won), (b, not a_won)):
            for pair in itertools.combinations(team, 2):
                n[pair] += 1
                if won:
                    w[pair] += 1

    rows = []
    for pair, games in n.items():
        if games < min_games:
            continue
        wins = w[pair]
        lo, hi = wilson_interval(wins, games)
        rows.append({
            "player_a": pair[0],
            "player_b": pair[1],
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "win_rate": wins / games,
            "ci_low": lo,
            "ci_high": hi,
            # True only when the whole interval sits clear of a coin flip.
            "beats_noise": lo > 0.5 or hi < 0.5,
        })
    rows.sort(key=lambda r: (-r["win_rate"], -r["games"]))
    return rows


def player_pair_records(matches, player, min_games=MIN_GAMES_DEFAULT):
    """One player's pairs, best first - 'who do I actually win with'."""
    rows = [r for r in pair_records(matches, min_games)
            if player in (r["player_a"], r["player_b"])]
    for r in rows:
        r["teammate"] = r["player_b"] if r["player_a"] == player else r["player_a"]
    return rows


def chemistry_test(matches, min_games=MIN_GAMES_DEFAULT, n_boot=1000, seed=0):
    """Is there more pair-to-pair spread in win rates than chance alone produces?

    Null hypothesis: every match is a coin flip, and which pair happens to be on the winning
    side carries no information. We simulate that world `n_boot` times and compare a
    games-weighted spread statistic against what we actually observed.

    Simulating whole matches (rather than shuffling pairs) matters: all 15 pairs on a team
    share one outcome, so pair records are heavily correlated. A test that ignored that
    correlation would call almost any group "significant".
    """
    sides = _sides(matches)
    if not sides:
        return None

    def spread(results):
        n = collections.Counter()
        w = collections.Counter()
        for (a, b, _), a_won in zip(sides, results):
            for team, won in ((a, a_won), (b, not a_won)):
                for pair in itertools.combinations(team, 2):
                    n[pair] += 1
                    if won:
                        w[pair] += 1
        keys = [k for k in n if n[k] >= min_games]
        if not keys:
            return 0.0
        counts = np.array([n[k] for k in keys], dtype=float)
        rates = np.array([w[k] / n[k] for k in keys], dtype=float)
        return float(np.sum(counts * (rates - 0.5) ** 2))

    observed = spread([s[2] for s in sides])
    rng = np.random.default_rng(seed)
    null = np.array([spread(rng.random(len(sides)) < 0.5) for _ in range(n_boot)])
    p_value = float((np.sum(null >= observed) + 1) / (n_boot + 1))
    return {
        "observed": observed,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "p_value": p_value,
        "n_matches": len(sides),
        "n_boot": n_boot,
    }


def cohesion_test(matches):
    """Does the side with more shared history win more often?

    For each match, each side's cohesion is the mean number of PRIOR games its 15 teammate
    pairs had played together. Prior-only matters - counting the current match would let the
    score peek at the result it is supposed to predict.

    This is the same theory as the per-pair view but with one parameter instead of 850, so
    it is the version with enough power to actually answer the question.
    """
    together = collections.Counter()
    diffs, results = [], []
    for a, b, a_won in _sides(matches):
        if len(a) != 6 or len(b) != 6:
            continue

        def cohesion(team):
            pairs = list(itertools.combinations(team, 2))
            return sum(together[p] for p in pairs) / len(pairs)

        diffs.append(cohesion(a) - cohesion(b))
        results.append(a_won)
        for team in (a, b):
            for pair in itertools.combinations(team, 2):
                together[pair] += 1

    diffs = np.array(diffs)
    results = np.array(results)
    decided = diffs != 0
    n = int(decided.sum())
    if n == 0:
        return None

    wins = int(np.sum((diffs[decided] > 0) == results[decided]))
    # Two-sided binomial test against a coin.
    tail = sum(math.comb(n, k) for k in range(min(wins, n - wins) + 1)) / 2**n
    return {
        "n_matches": n,
        "cohesive_side_wins": wins,
        "cohesive_side_win_rate": wins / n,
        "p_value": min(2 * tail, 1.0),
        "mean_abs_gap": float(np.abs(diffs[decided]).mean()),
    }


def detection_power(n_matches, true_rate):
    """Power of the cohesion test to notice a real edge of `true_rate` at n matches.

    Used to say what a null result does and does not rule out - "we found nothing" means
    something very different at 20% power than at 90%.
    """
    if n_matches <= 0:
        return 0.0
    crit = 1.96 * math.sqrt(0.25 / n_matches)
    se = math.sqrt(true_rate * (1 - true_rate) / n_matches)
    z = (abs(true_rate - 0.5) - crit) / se
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
