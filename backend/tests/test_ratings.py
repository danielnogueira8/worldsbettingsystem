from datetime import datetime, timedelta

import numpy as np

from app.model.ratings import GameRow, RatingParams, fit


def synth(seed=0, n_days=200, region_true=None):
    rng = np.random.default_rng(seed)
    region_true = region_true or {"A": 0.8, "B": 0.0, "C": -0.8}
    teams = {f"{g}{i}": g for g in region_true for i in range(8)}
    true = {t: region_true[g] + rng.normal(0, 0.5) for t, g in teams.items()}
    t0 = datetime(2026, 1, 1)
    games = []
    for d in range(n_days):
        date = t0 + timedelta(days=d)
        for g in region_true:
            mem = [t for t in teams if teams[t] == g]
            for _ in range(4):
                a, b = rng.choice(mem, 2, replace=False)
                p = 1 / (1 + np.exp(-(true[a] - true[b])))
                games.append(GameRow(date, a, b, g, g, bool(rng.random() < p)))
        if d % 20 == 0:
            for _ in range(15):
                a, b = rng.choice(list(teams), 2, replace=False)
                p = 1 / (1 + np.exp(-(true[a] - true[b])))
                games.append(GameRow(date, a, b, teams[a], teams[b], bool(rng.random() < p), True))
    return games, true, teams


def test_recovers_strengths_across_regions():
    games, true, teams = synth()
    rf = fit(games, params=RatingParams(half_life_days=10_000))
    names = list(true)
    est, _ = rf.strength(names)
    corr = np.corrcoef(est, [true[t] for t in names])[0, 1]
    assert corr > 0.9, corr
    rho = dict(zip(rf.regions, rf.rho, strict=True))
    assert rho["A"] > rho["B"] > rho["C"]
    assert rf.extras["converged"]


def test_no_leakage():
    games, _, _ = synth(n_days=50)
    cut = games[len(games) // 2].date
    rf = fit(games, as_of=cut)
    assert rf.n_games == sum(g.date < cut for g in games)


def test_uncertainty_shrinks_with_data():
    g_small, _, _ = synth(n_days=20)
    g_big, _, _ = synth(n_days=200)
    p = RatingParams(half_life_days=10_000)
    sd_small = np.sqrt(np.diag(fit(g_small, params=p).cov)).mean()
    sd_big = np.sqrt(np.diag(fit(g_big, params=p).cov)).mean()
    assert sd_big < sd_small


def test_unseen_team_gets_prior_and_gpr_moves_it():
    games, _, _ = synth(n_days=30)
    rf = fit(games, team_region_override={"NEW": "A"})
    m, cov = rf.strength(["NEW"])
    assert cov[0, 0] > 0.5  # wide prior
    rf2 = fit(games, team_region_override={"NEW": "A"},
              gpr={"NEW": 2000.0, "A0": 1000.0, "B0": 1000.0, "C0": 1000.0})
    assert rf2.strength(["NEW"])[0][0] > m[0]


def test_game_prob_symmetry():
    games, _, _ = synth(n_days=30)
    rf = fit(games)
    assert abs(rf.game_prob("A0", "B0") + rf.game_prob("B0", "A0") - 1) < 1e-9
