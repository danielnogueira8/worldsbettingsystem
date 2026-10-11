import numpy as np
import pytest

from app.model.series import game_prob_from_series, series_win_prob


@pytest.mark.parametrize("p", [0.0, 0.1, 0.35, 0.5, 0.6, 0.9, 1.0])
def test_closed_forms(p):
    assert series_win_prob(p, 1) == pytest.approx(p)
    assert series_win_prob(p, 3) == pytest.approx(p**2 * (3 - 2 * p))
    assert series_win_prob(p, 5) == pytest.approx(p**3 * (10 - 15 * p + 6 * p**2))


def test_symmetry_and_amplification():
    ps = np.linspace(0, 1, 101)
    for bo in (1, 3, 5, 7):
        np.testing.assert_allclose(series_win_prob(ps, bo) + series_win_prob(1 - ps, bo), 1)
    # longer series favour the favourite
    assert series_win_prob(0.6, 5) > series_win_prob(0.6, 3) > 0.6


def test_inverse():
    for bo in (3, 5):
        for p in (0.3, 0.55, 0.8):
            assert game_prob_from_series(series_win_prob(p, bo), bo) == pytest.approx(p, abs=1e-8)


def test_rejects_even():
    with pytest.raises(ValueError):
        series_win_prob(0.5, 2)


def test_score_probs():
    from app.model.series import score_probs

    for bo in (1, 3, 5):
        for p in (0.2, 0.5, 0.7):
            sp = score_probs(p, bo)
            assert sum(x[2] for x in sp) == pytest.approx(1)
            a_wins = sum(x[2] for x in sp if x[0] > x[1])
            assert a_wins == pytest.approx(series_win_prob(p, bo))
    sp = {(a, b): pr for a, b, pr in score_probs(0.6, 5)}
    assert sp[(3, 0)] == pytest.approx(0.6**3)
    assert len(sp) == 6
