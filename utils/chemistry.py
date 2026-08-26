"""The "friendship buff": do certain people win more together than they do apart?

The tempting version of this page is a big grid of pair win rates, sorted, with the top of
the list crowned. That grid is misleading twice over, and it is worth being precise about
both.

**It is mostly noise.** There are 850 distinct teammate pairs in 82 matches. Nearly half of
them have played together exactly once. Even for a pair with 10 games, a 50/50 coin lands
outside 19%-81% about one time in twenty - so with 850 pairs to look at, dozens will show a
"huge" edge that is nothing but variance.

**It is mostly not about the pair.** A pair's win rate together is dominated by who the two
players are, not by anything that happens between them. Put a 60% player next to a 60%
player and they will post a good record whether or not they have ever spoken. Ranking pairs
by raw win rate is therefore a ranking of individual records with extra steps, and the
"chemistry" at the top of it belongs to whoever happened to be winning.

The fix for the second problem is a baseline: what would these two be expected to win
together, given how they do apart, against the opponents they actually faced? Subtract that
from what they did win and what is left - the synergy - is the part that is genuinely about
the pairing. `utils.ratings` builds the baseline; everything here measures against it.

So this module does five things:

1. `pair_records` - the raw counts, with a Wilson confidence interval, so a pair's record is
   always shown next to how much it is worth trusting.
2. `pair_synergy` - the same pairs, minus their baseline. This is the "more than the sum of
   their parts" number, with an exact Poisson-binomial p-value for it.
3. `opponent_edge` - the same arithmetic across the net: how two players do when they are
   on OPPOSITE sides, minus what the baseline expected of those matchups. A "kryptonite" is
   the most negative of these, and it earns more suspicion than a synergy number, not less.
4. `chemistry_test` - a parametric bootstrap answering the global question: is there MORE
   spread across pairs than individual skill and luck alone produce? This is the honest
   version of "is the friendship buff real", and it costs nothing to be wrong about a
   single pair.
5. `cohesion_test` - a far better-powered test of the same theory. Instead of estimating 850
   pair effects from 82 outcomes, it asks one question: does the side with more shared
   history beat its baseline? One parameter against 82 matches has real statistical power,
   where the per-pair view has almost none.

Everything here is computed from match results alone; no per-player box score is involved.
"""
import collections
import itertools
import math

import numpy as np

from utils import ratings

MIN_GAMES_DEFAULT = 5

# How much credit a player's own record gets when building the baseline.
#
# "model"   - ratings from the ridge Bradley-Terry model over all twelve players in each
#             match, with the amount of shrinkage chosen by marginal likelihood. If the
#             pool's win rates are indistinguishable from coin flips, this correctly hands
#             back a baseline near 50% and the raw record stands as the synergy estimate.
# "records" - the two players' own win rates apart from each other, taken literally and
#             added on the log-odds scale. Deliberately credulous: it assumes every hot
#             streak is real skill, and ignores the other ten players in the lobby. It is
#             the ceiling on how much of a pair's record their individual reputations could
#             possibly explain, which makes it the right thing to check a "they are just two
#             good players" objection against.
BASELINE_MODEL = "model"
BASELINE_RECORDS = "records"
BASELINE_MODES = (BASELINE_MODEL, BASELINE_RECORDS)

# Beta(2,2)-equivalent smoothing for face-value ratings: a 3-0 player is worth a modest edge,
# not an infinite one.
FACE_VALUE_PRIOR_GAMES = 4.0


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


def poisson_binomial_tails(wins, probs):
    """(P(K <= wins), P(K >= wins)) for a sum of independent, differently-weighted coins.

    A pair's games are not exchangeable once a baseline exists: one match might have been a
    65% spot and the next a 40% spot. The plain binomial test cannot express that, so the
    null distribution is built by convolution instead - exact, and cheap at these sizes.
    """
    pmf = np.zeros(len(probs) + 1)
    pmf[0] = 1.0
    for p in probs:
        pmf[1:] = pmf[1:] * (1 - p) + pmf[:-1] * p
        pmf[0] *= (1 - p)
    return float(pmf[:wins + 1].sum()), float(pmf[wins:].sum())


def _two_sided_p(wins, probs):
    lower, upper = poisson_binomial_tails(wins, probs)
    return min(1.0, 2 * min(lower, upper))


def _pair_appearances(side_list):
    """pair -> list of (match index, True if the pair was on side A)."""
    out = collections.defaultdict(list)
    for i, (a, b, _) in enumerate(side_list):
        for team, is_a in ((a, True), (b, False)):
            for pair in itertools.combinations(team, 2):
                out[pair].append((i, is_a))
    return out


def _opponent_appearances(side_list):
    """pair -> list of (match index, True if the pair's FIRST player was on side A).

    Deliberately the same shape as `_pair_appearances`, so everything downstream - the win
    count, the baseline, the Poisson-binomial p-value - works on either without knowing
    which side of the net it is looking at. The only difference is that here the two are
    opponents, so `is_a` orients the row on pair[0] rather than on the pair as a unit.
    """
    out = collections.defaultdict(list)
    for i, (a, b, _) in enumerate(side_list):
        for x in a:
            for y in b:
                pair = (x, y) if x < y else (y, x)
                out[pair].append((i, pair[0] == x))
    return out


def pair_records(matches, min_games=MIN_GAMES_DEFAULT, side_list=None):
    """Every teammate pair's record together, filtered to min_games.

    Returns a list of dicts sorted by win rate, then by games played, so that a pair with a
    longer track record outranks a short hot streak at the same rate.
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    rows = []
    for pair, appearances in _pair_appearances(side_list).items():
        games = len(appearances)
        if games < min_games:
            continue
        wins = sum(1 for i, is_a in appearances if side_list[i][2] == is_a)
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


# ------------------------------------------------------------------ baselines

def _record_logit(games, wins):
    """A win rate as log-odds, smoothed so that 3-0 is a modest edge rather than infinite."""
    k = FACE_VALUE_PRIOR_GAMES
    q = (wins + k * 0.5) / (games + k)
    return math.log(q / (1 - q))


def _records_probability(a_record, b_record):
    """The literal sum of two parts: each player's apart-edge in log-odds, added.

    Two 60% players come out at 70% together, which is what "their individual records
    explain it" actually implies. It is an aggressive baseline - it treats both records as
    pure skill and ignores the other ten players - and that is the point: a pair that clears
    it is not merely two winners standing next to each other.
    """
    logit = _record_logit(*a_record) + _record_logit(*b_record)
    return 1 / (1 + math.exp(-logit))


def _matchup_probability(a_record, b_record):
    """The opponent mirror of `_records_probability`: two apart-edges subtracted, not added.

    Across the net the two records work against each other, so a 60% player facing a 40%
    player comes out around 70% - the same credulous "their reputations explain it all"
    baseline, pointed the other way.
    """
    logit = _record_logit(*a_record) - _record_logit(*b_record)
    return 1 / (1 + math.exp(-logit))


def baseline_lambda(matches, side_list=None):
    """The shrinkage the season's results actually support, reused across every pair fit.

    Re-searching lambda inside each leave-pair-out fit would let a pair's absence change the
    rules of its own baseline, and costs 850 evidence sweeps for a number that barely moves.
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    return ratings.fit(matches, side_list=side_list)["lam"]


def _apart_record(side_list, player, exclude):
    """A player's record in the matches NOT in `exclude` - the "without you" half of WOWY."""
    games = wins = 0
    for i, (a, b, a_won) in enumerate(side_list):
        if i in exclude:
            continue
        if player in a:
            games, wins = games + 1, wins + int(a_won)
        elif player in b:
            games, wins = games + 1, wins + int(not a_won)
    return games, wins


def _baselined_rows(matches, appearances, combine, min_games, mode, lam, side_list):
    """Shared core of `pair_synergy` and `opponent_edge`.

    Both ask one question of one fit - what did these two do across the games they shared,
    against what the baseline expected of exactly those games - and differ only in which
    games count as shared (`appearances`) and in how two apart-records combine into a single
    expectation (`combine`). `is_a` orients each row, so "wins" always counts the matches
    pair[0]'s side won: for teammates that is both of them, for opponents it is the first.
    """
    rows = []
    for pair, appears in appearances.items():
        if len(appears) < min_games:
            continue
        drop = [i for i, _ in appears]
        exclude = set(drop)
        a_games, a_wins = _apart_record(side_list, pair[0], exclude)
        b_games, b_wins = _apart_record(side_list, pair[1], exclude)

        if mode == BASELINE_RECORDS:
            # One number for the pairing, so every shared match carries the same expectation.
            probs = np.full(len(drop), combine((a_games, a_wins), (b_games, b_wins)))
        else:
            model = ratings.fit(matches, lam=lam, drop=drop, side_list=side_list)
            # Re-orient from "side A wins" to "pair[0]'s side wins".
            probs = np.array([
                ratings.win_probability(model, side_list[i][0], side_list[i][1]) if is_a
                else 1 - ratings.win_probability(model, side_list[i][0], side_list[i][1])
                for i, is_a in appears
            ])

        games = len(appears)
        wins = sum(1 for i, is_a in appears if side_list[i][2] == is_a)
        expected = float(probs.mean())
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
            "beats_noise": lo > 0.5 or hi < 0.5,
            "expected": expected,
            "expected_wins": float(probs.sum()),
            # The headline: win rate above what these two were due, in percentage points.
            "edge": wins / games - expected,
            "edge_low": lo - expected,
            "edge_high": hi - expected,
            "p_value": _two_sided_p(wins, probs),
            # WOWY context, so the baseline is legible without trusting the model.
            "a_apart_games": a_games,
            "a_apart_rate": (a_wins / a_games) if a_games else None,
            "b_apart_games": b_games,
            "b_apart_rate": (b_wins / b_games) if b_games else None,
        })
    return rows


def pair_synergy(matches, min_games=MIN_GAMES_DEFAULT, mode=BASELINE_MODEL, lam=None,
                 side_list=None):
    """Every qualifying pair, measured against what the two would be expected to win anyway.

    For each pair, the baseline is refitted with their shared games removed, then used to
    score exactly those games. Removing them matters: a pair's wins together are already
    inside both players' individual records, so a baseline fitted on everything would credit
    the pair's own success to the two players separately and then report no synergy left.

    `synergy` is (their actual win rate) - (the baseline's expected win rate) over the same
    games, in percentage points of win rate. Positive means more than the sum of their parts.
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    if not side_list:
        return []
    if lam is None and mode == BASELINE_MODEL:
        lam = baseline_lambda(matches, side_list)

    rows = _baselined_rows(matches, _pair_appearances(side_list), _records_probability,
                           min_games, mode, lam, side_list)
    # "Edge" is the neutral word the shared core uses; between teammates it has a better one.
    for r in rows:
        r["synergy"] = r.pop("edge")
        r["synergy_low"] = r.pop("edge_low")
        r["synergy_high"] = r.pop("edge_high")
    rows.sort(key=lambda r: (-r["synergy"], -r["games"]))
    return rows


def opponent_edge(matches, min_games=MIN_GAMES_DEFAULT, mode=BASELINE_MODEL, lam=None,
                  side_list=None):
    """Every pair who have faced each other, measured against what the matchup was due.

    `pair_synergy` across the net: refit the baseline without the games the two spent on
    opposite sides, score exactly those games, subtract. `edge` is player_a's win rate in
    the matchup minus the baseline's expectation for it, in percentage points.

    Dropping the shared games matters more here than it does for teammates. Every match in a
    head-to-head record is a win for one of them and a loss for the other, so leaving those
    games in the fit lifts the winner's rating and sinks the loser's using the very games
    the baseline is about to be scored on. The model would then expect the result it had
    already been shown, and every matchup would come back flat.

    Read the output with more suspicion than a synergy figure, not less. Each of the two is
    one player in twelve, they meet only because someone sorted the teams that way, and
    results-only data cannot separate "that player has their number" from the pair having
    landed on lopsided sides whenever they met.
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    if not side_list:
        return []
    if lam is None and mode == BASELINE_MODEL:
        lam = baseline_lambda(matches, side_list)

    rows = _baselined_rows(matches, _opponent_appearances(side_list), _matchup_probability,
                           min_games, mode, lam, side_list)
    rows.sort(key=lambda r: (-r["edge"], -r["games"]))
    return rows


def player_pair_records(matches, player, min_games=MIN_GAMES_DEFAULT, mode=BASELINE_MODEL,
                        rows=None):
    """One player's pairs, best first - "who do I actually win more with than without".

    Sorted by synergy rather than raw win rate, so a teammate does not top the list purely
    for being good.
    """
    rows = pair_synergy(matches, min_games, mode) if rows is None else rows
    mine = [dict(r) for r in rows if player in (r["player_a"], r["player_b"])]
    for r in mine:
        r["teammate"] = r["player_b"] if r["player_a"] == player else r["player_a"]
        r["teammate_apart_rate"] = (r["b_apart_rate"] if r["player_a"] == player
                                    else r["a_apart_rate"])
    return mine


def _from_b_side(row):
    """An `opponent_edge` row rewritten from player_b's end of the matchup.

    Rows leave the core oriented on player_a, so half of any one player's matchups arrive
    backwards. Everything with a direction gets mirrored; `games`, `p_value` and
    `beats_noise` are the same fact seen from either end, so they are left alone.
    """
    games, wins = row["games"], row["losses"]
    expected = 1 - row["expected"]
    lo, hi = wilson_interval(wins, games)
    return {
        **row,
        "wins": wins,
        "losses": row["wins"],
        "win_rate": wins / games,
        "ci_low": lo,
        "ci_high": hi,
        "expected": expected,
        "expected_wins": games - row["expected_wins"],
        "edge": wins / games - expected,
        "edge_low": lo - expected,
        "edge_high": hi - expected,
    }


def player_opponent_records(matches, player, min_games=MIN_GAMES_DEFAULT, mode=BASELINE_MODEL,
                            rows=None):
    """One player's matchups, worst first - "who beats me more than they should".

    Every row is oriented so its fields read from `player`'s end of the matchup, and the
    sort is by edge ascending, so the head of the list is the opponent this player loses to
    beyond the baseline rather than simply the strongest opponent they have faced.
    """
    rows = opponent_edge(matches, min_games, mode) if rows is None else rows
    mine = []
    for r in rows:
        if r["player_a"] == player:
            row = dict(r)
            row["opponent"] = r["player_b"]
            row["opponent_apart_rate"] = r["b_apart_rate"]
        elif r["player_b"] == player:
            row = _from_b_side(r)
            row["opponent"] = r["player_a"]
            row["opponent_apart_rate"] = r["a_apart_rate"]
        else:
            continue
        mine.append(row)
    mine.sort(key=lambda r: (r["edge"], -r["games"]))
    return mine


# ------------------------------------------------------------------ global tests

def chemistry_test(matches, min_games=MIN_GAMES_DEFAULT, n_boot=1000, seed=0,
                   side_list=None):
    """Is there more pair-to-pair spread in win rates than individual skill and luck produce?

    Null hypothesis: each match is decided by a coin weighted by the baseline - the players
    on each side and the side advantage - and which pair happens to be on the winning side
    carries no extra information. We simulate that world `n_boot` times and compare a
    games-weighted spread statistic against what we actually observed.

    Simulating whole matches (rather than shuffling pairs) matters: all 15 pairs on a team
    share one outcome, so pair records are heavily correlated. A test that ignored that
    correlation would call almost any group "significant".
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    if not side_list:
        return None

    model = ratings.fit(matches, side_list=side_list)
    base_a = ratings.match_probabilities(model, side_list)

    appearances = _pair_appearances(side_list)
    keys = [k for k, v in appearances.items() if len(v) >= min_games]
    if not keys:
        return None
    counts = np.array([len(appearances[k]) for k in keys], dtype=float)
    # Each pair's expected win rate under the baseline, held fixed across simulations.
    expected = np.array([
        np.mean([base_a[i] if is_a else 1 - base_a[i] for i, is_a in appearances[k]])
        for k in keys
    ])

    def spread(results):
        rates = np.array([
            sum(1 for i, is_a in appearances[k] if results[i] == is_a) / len(appearances[k])
            for k in keys
        ])
        return float(np.sum(counts * (rates - expected) ** 2))

    observed = spread([s[2] for s in side_list])
    rng = np.random.default_rng(seed)
    null = np.array([spread(rng.random(len(side_list)) < base_a) for _ in range(n_boot)])
    p_value = float((np.sum(null >= observed) + 1) / (n_boot + 1))
    return {
        "observed": observed,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "p_value": p_value,
        "n_matches": len(side_list),
        "n_pairs": len(keys),
        "n_boot": n_boot,
        "baseline_sd": model["rating_sd"],
    }


def cohesion_test(matches, side_list=None):
    """Does the side with more shared history beat its baseline?

    For each match, each side's cohesion is the mean number of PRIOR games its 15 teammate
    pairs had played together. Prior-only matters - counting the current match would let the
    score peek at the result it is supposed to predict.

    The comparison is against the baseline rather than against a coin, so a stacked side that
    is also the stronger side does not get credited for chemistry it does not have. With one
    parameter instead of 850, this is the version of the theory with enough power to answer.
    """
    side_list = ratings.sides(matches) if side_list is None else side_list
    if not side_list:
        return None

    model = ratings.fit(matches, side_list=side_list)
    base_a = ratings.match_probabilities(model, side_list)

    together = collections.Counter()
    diffs, results, probs = [], [], []
    for idx, (a, b, a_won) in enumerate(side_list):
        if len(a) != 6 or len(b) != 6:
            continue

        def cohesion(team):
            pairs = list(itertools.combinations(team, 2))
            return sum(together[p] for p in pairs) / len(pairs)

        diffs.append(cohesion(a) - cohesion(b))
        results.append(a_won)
        probs.append(base_a[idx])
        for team in (a, b):
            for pair in itertools.combinations(team, 2):
                together[pair] += 1

    diffs = np.array(diffs)
    results = np.array(results)
    probs = np.array(probs)
    decided = diffs != 0
    n = int(decided.sum())
    if n == 0:
        return None

    # Orient every match so "us" is the more-cohesive side.
    a_is_cohesive = diffs[decided] > 0
    wins = int(np.sum(a_is_cohesive == results[decided]))
    cohesive_probs = np.where(a_is_cohesive, probs[decided], 1 - probs[decided])
    expected = float(cohesive_probs.sum())
    return {
        "n_matches": n,
        "cohesive_side_wins": wins,
        "cohesive_side_win_rate": wins / n,
        "expected_wins": expected,
        "expected_win_rate": expected / n,
        "excess_win_rate": wins / n - expected / n,
        "p_value": _two_sided_p(wins, cohesive_probs),
        "mean_abs_gap": float(np.abs(diffs[decided]).mean()),
        "baseline_sd": model["rating_sd"],
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
