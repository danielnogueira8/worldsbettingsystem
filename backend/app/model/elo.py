"""Plain Elo baseline. The rating model has to beat this, and the market, to be trusted."""

from __future__ import annotations

from collections import defaultdict

from .ratings import GameRow


class Elo:
    def __init__(self, k: float = 24.0, base: float = 1500.0, intl_k_mult: float = 1.5):
        self.k = k
        self.intl_k_mult = intl_k_mult
        self.r: dict[str, float] = defaultdict(lambda: base)

    def prob(self, a: str, b: str) -> float:
        return 1.0 / (1.0 + 10 ** ((self.r[b] - self.r[a]) / 400))

    def update(self, g: GameRow) -> None:
        p = self.prob(g.blue, g.red)
        k = self.k * (self.intl_k_mult if g.international else 1.0)
        d = k * ((1.0 if g.blue_win else 0.0) - p)
        self.r[g.blue] += d
        self.r[g.red] -= d
