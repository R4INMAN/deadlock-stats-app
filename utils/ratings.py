"""Individual player strength, so pair chemistry can be measured against the right baseline.

A pair's raw win rate together answers the wrong question. Two players who each win 60% of
their games will win about 60% of their games together whether or not they have any
chemistry at all - the record is mostly a restatement of who was on the roster. What the
"friendship buff" is supposed to mean is the part their individual records do NOT explain:
how much more than the sum of their parts.

Getting a baseline requires ratings, and ratings from 82 matches are a trap of their own.
Fitting one free parameter per player to 82 outcomes reproduces the data perfectly and
predicts nothing, so this module fits a ridge-penalised Bradley-Terry model - a logistic
regression on (players on side A) minus (players on side B), with every rating pulled
towards average by a prior. The prior's strength is chosen by marginal likelihood rather
than by taste, which lets the data say how much individual skill spread it can support.

Two things are deliberately kept out of the model:

- No hero, souls, or KDA terms. Those are downstream of winning, and a baseline built from
  them would absorb the chemistry it is supposed to leave behind.
- No pair terms. This is the null model that pair effects are measured against; putting
  pairs into it would define the answer to zero.
"""
import collections

import numpy as np

# Powers of two from 0.5 to 1024. lambda is a prior precision: the implied prior SD on a
# player's rating is 1/sqrt(lambda), so the grid spans "individual skill swings a match
# wildly" to "everyone in the pool is interchangeable".
LAMBDA_GRID = tuple(2.0 ** k for k in range(-1, 11))


def sides(matches):
    """(team_a_names, team_b_names, team_a_won) per match, skipping malformed rosters.

    Team A is whichever side name sorts first, held fixed across matches so the model's
    intercept measures a real side advantage rather than an arbitrary labelling.
    """
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


def _design(side_list):
    """Design matrix for the Bradley-Terry fit: +1 per side-A player, -1 per side-B player.

    The last column is a constant carrying any side advantage. It is left unpenalised - the
    prior is a statement about players being similar to each other, not about the map being
    fair.
    """
    players = sorted({p for a, b, _ in side_list for p in a + b})
    index = {p: i for i, p in enumerate(players)}
    x = np.zeros((len(side_list), len(players) + 1))
    y = np.zeros(len(side_list))
    for i, (a, b, a_won) in enumerate(side_list):
        for p in a:
            x[i, index[p]] += 1
        for p in b:
            x[i, index[p]] -= 1
        x[i, -1] = 1.0
        y[i] = a_won
    return x, y, players


def _penalty(width, lam):
    pen = np.full(width, float(lam))
    pen[-1] = 1e-6  # side advantage: effectively unpenalised
    return pen


def _fit_ridge(x, y, lam, iters=100, tol=1e-10):
    """Newton / IRLS for penalised logistic regression.

    The penalty is what makes this solvable at all: with more players than matches the
    unpenalised likelihood is maximised by infinite ratings, and any player who happens to
    be undefeated runs off to infinity.
    """
    pen = _penalty(x.shape[1], lam)
    beta = np.zeros(x.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(x @ beta)))
        w = np.maximum(p * (1 - p), 1e-9)
        hess = x.T @ (x * w[:, None]) + np.diag(pen)
        grad = x.T @ (y - p) - pen * beta
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            break
    return beta


def _log_evidence(x, y, lam, beta):
    """Laplace approximation to log P(results | lambda) - how well a given amount of
    shrinkage explains the season, with the flexibility of the fit charged against it."""
    p = np.clip(1 / (1 + np.exp(-(x @ beta))), 1e-12, 1 - 1e-12)
    w = np.maximum(p * (1 - p), 1e-9)
    pen = _penalty(x.shape[1], lam)
    log_lik = float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))
    log_prior = float(0.5 * np.sum(np.log(pen)) - 0.5 * np.sum(pen * beta ** 2))
    _, log_det = np.linalg.slogdet(x.T @ (x * w[:, None]) + np.diag(pen))
    return log_lik + log_prior - 0.5 * float(log_det)


def fit(matches, lam=None, drop=(), side_list=None):
    """Ridge Bradley-Terry ratings.

    `lam` fixes the prior precision; leaving it None picks the value with the highest
    marginal likelihood over LAMBDA_GRID.

    `drop` is a set of match indices to leave out of the fit while keeping every player's
    column. It is how a pair's baseline gets built without letting their games together vote
    on their own individual ratings - a player whose only games are with that partner drops
    all the way back to average, which is the honest answer to "how good are they apart".
    """
    side_list = sides(matches) if side_list is None else side_list
    x, y, players = _design(side_list)
    if len(drop):
        keep = np.ones(len(side_list), dtype=bool)
        keep[list(drop)] = False
        x_fit, y_fit = x[keep], y[keep]
    else:
        x_fit, y_fit = x, y

    evidence = None
    if lam is None:
        evidence = [(lam_i, _log_evidence(x_fit, y_fit, lam_i, _fit_ridge(x_fit, y_fit, lam_i)))
                    for lam_i in LAMBDA_GRID]
        lam = max(evidence, key=lambda kv: kv[1])[0]

    beta = _fit_ridge(x_fit, y_fit, lam)
    return {
        "ratings": dict(zip(players, beta[:-1])),
        "side_advantage": float(beta[-1]),
        "lam": float(lam),
        "prior_sd": float(1 / np.sqrt(lam)),
        "rating_sd": float(np.std(beta[:-1])) if len(beta) > 1 else 0.0,
        "n_matches": int(len(y_fit)),
        "evidence": evidence,
        "players": players,
    }


def win_probability(model, team_a, team_b):
    """P(team_a wins), where team_a is the side that sorts first - the side the advantage
    term is measured for."""
    r = model["ratings"]
    logit = (sum(r.get(p, 0.0) for p in team_a) - sum(r.get(p, 0.0) for p in team_b)
             + model["side_advantage"])
    return float(1 / (1 + np.exp(-logit)))


def match_probabilities(model, side_list):
    """P(side A wins) for every match, aligned with `side_list`."""
    return np.array([win_probability(model, a, b) for a, b, _ in side_list])


# ------------------------------------------------------------------ diagnostics

def _loo_rating_gap(side_list, results, prior_games=4.0):
    """Per match: side A's summed win-rate logits minus side B's, with each player's win
    rate computed WITHOUT the match being scored.

    Leaving the match out is the whole point. A player's win rate includes the game you are
    trying to predict, so scoring matches with all-games win rates grades the answer sheet
    against itself - in this data that alone turns a null result into a four-sigma one.
    """
    n = collections.Counter()
    w = collections.Counter()
    for (a, b, _), a_won in zip(side_list, results):
        for team, won in ((a, a_won), (b, not a_won)):
            for p in team:
                n[p] += 1
                if won:
                    w[p] += 1

    def logit(games, wins):
        # Beta(2,2)-ish smoothing, so a 3-0 player is not worth infinite logits.
        q = (wins + prior_games * 0.5) / (games + prior_games)
        return float(np.log(q / (1 - q)))

    gaps = []
    for (a, b, _), a_won in zip(side_list, results):
        gaps.append(sum(logit(n[p] - 1, w[p] - (1 if a_won else 0)) for p in a)
                    - sum(logit(n[p] - 1, w[p] - (0 if a_won else 1)) for p in b))
    return np.array(gaps)


def _logistic_slope(gaps, results, iters=200):
    """Slope from a two-parameter logistic fit of results on the rating gap."""
    z = np.column_stack([gaps, np.ones(len(gaps))])
    y = np.asarray(results, dtype=float)
    beta = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(z @ beta)))
        w = np.maximum(p * (1 - p), 1e-9)
        step = np.linalg.solve(z.T @ (z * w[:, None]) + 1e-8 * np.eye(2), z.T @ (y - p))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(beta[0])


def record_calibration(matches, n_perm=400, seed=0, side_list=None):
    """Do the players with better records actually win more? A slope, and a null for it.

    A slope of 1 means win rates predict outcomes exactly as advertised; 0 means a player's
    record says nothing about the next match; below 0 means it points the wrong way.

    The null is not "slope = 0". Leaving each match out of its own ratings induces a small
    negative slope even when results are pure coin flips, because the wins and losses in the
    pool have to add up. So the comparison is against simulated coin-flip seasons run
    through the identical pipeline.
    """
    side_list = sides(matches) if side_list is None else side_list
    if len(side_list) < 10:
        return None
    results = [s[2] for s in side_list]
    observed = _logistic_slope(_loo_rating_gap(side_list, results), results)

    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for i in range(n_perm):
        sim = rng.random(len(side_list)) < 0.5
        null[i] = _logistic_slope(_loo_rating_gap(side_list, sim), sim)
    centre = float(null.mean())
    p_value = float((np.sum(np.abs(null - centre) >= abs(observed - centre)) + 1) / (n_perm + 1))
    return {
        "slope": observed,
        "null_mean": centre,
        "null_sd": float(null.std()),
        "p_value": p_value,
        "n_matches": len(side_list),
        "n_perm": n_perm,
    }
