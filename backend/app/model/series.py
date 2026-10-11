"""Game win probability -> series win probability.

Assumes games are independent with a constant per-game probability p. That's a known
simplification (momentum, draft adaptation, side selection), but the error is small and
roughly symmetric. The backtest checks it on real Bo5s.
"""

from __future__ import annotations

from math import comb

import numpy as np


def series_win_prob(p, best_of: int):
    """P(win a best-of-n series) given single-game win prob p. Works on scalars or arrays.

    First to n = (best_of + 1) // 2 wins:
        sum_{k=0}^{n-1} C(n-1+k, k) p^n (1-p)^k
    """
    if best_of < 1 or best_of % 2 == 0:
        raise ValueError(f"best_of must be a positive odd number, got {best_of}")
    p = np.asarray(p, dtype=float)
    q = 1.0 - p
    n = (best_of + 1) // 2
    total = np.zeros_like(p)
    for k in range(n):
        total = total + comb(n - 1 + k, k) * p**n * q**k
    return total if total.ndim else float(total)


def game_prob_from_series(ps: float, best_of: int, tol: float = 1e-10) -> float:
    """Inverse of series_win_prob: the per-game p implied by a series price. Bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if series_win_prob(mid, best_of) < ps:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def score_probs(p: float, best_of: int) -> list[tuple[int, int, float]]:
    """Probability of each final series score, from team A's per-game win probability.

    Returns (a_wins, b_wins, prob) for every possible final score, summing to 1. A team
    that wins n games has played n-1+k games before the last, any k of which it lost.
    """
    n = (best_of + 1) // 2
    q = 1.0 - p
    out = []
    for k in range(n):
        out.append((n, k, comb(n - 1 + k, k) * p**n * q**k))
        out.append((k, n, comb(n - 1 + k, k) * q**n * p**k))
    return out
