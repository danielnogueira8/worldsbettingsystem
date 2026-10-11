"""Walk-forward backtest. The model only ever sees games before the one it predicts.

For every target game we refit (at most once per calendar day, for speed) on all games
strictly before that day, then predict. Elo runs in parallel as the baseline.

Reports log loss, Brier score and a calibration table for both. If market prices for the
same games are supplied (a dict game_id -> implied prob of blue winning), those are
scored too. That comparison is the gate: no edge over the market, no bets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .elo import Elo
from .ratings import GameRow, RatingParams, fit
from .series import sigmoid


@dataclass
class Prediction:
    game_id: str
    date: datetime
    blue: str
    red: str
    y: int
    model: float
    elo: float
    market: float | None = None


def _ll(y, p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def _brier(y, p):
    return float(((np.asarray(p, float) - np.asarray(y, float)) ** 2).mean())


def calibration(y, p, bins: int = 10) -> list[dict]:
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if m.sum():
            out.append(
                {
                    "bin": f"{edges[i]:.1f}-{edges[i + 1]:.1f}",
                    "n": int(m.sum()),
                    "pred": float(p[m].mean()),
                    "actual": float(y[m].mean()),
                }
            )
    return out


def run(
    games: list[tuple[str, GameRow]],
    is_target: Callable[[GameRow], bool],
    params: RatingParams | None = None,
    gpr: dict[str, float] | None = None,
    market: dict[str, float] | None = None,
) -> dict:
    games = sorted(games, key=lambda x: x[1].date)
    elo = Elo()
    preds: list[Prediction] = []
    cache_day = None
    rf = None
    for gid, g in games:
        if is_target(g):
            day = g.date.date()
            if day != cache_day:
                hist = [x for _, x in games if x.date.date() < day]
                if hist:
                    rf = fit(
                        hist,
                        as_of=datetime.combine(day, datetime.min.time()),
                        params=params,
                        gpr=gpr,
                    )
                cache_day = day
            if rf is not None and g.blue in rf.team_region and g.red in rf.team_region:
                mean, cov = rf.strength([g.blue, g.red])
                mu = mean[0] - mean[1] + rf.beta_side
                var = cov[0, 0] + cov[1, 1] - 2 * cov[0, 1]
                pm = float(sigmoid(mu / np.sqrt(1 + np.pi * var / 8)))
                preds.append(
                    Prediction(
                        gid,
                        g.date,
                        g.blue,
                        g.red,
                        int(g.blue_win),
                        pm,
                        elo.prob(g.blue, g.red),
                        (market or {}).get(gid),
                    )
                )
        elo.update(g)

    if not preds:
        return {"n": 0, "message": "no target games with history"}
    y = [p.y for p in preds]
    res = {
        "n": len(preds),
        "model": {
            "log_loss": _ll(y, [p.model for p in preds]),
            "brier": _brier(y, [p.model for p in preds]),
            "calibration": calibration(y, [p.model for p in preds]),
        },
        "elo": {
            "log_loss": _ll(y, [p.elo for p in preds]),
            "brier": _brier(y, [p.elo for p in preds]),
            "calibration": calibration(y, [p.elo for p in preds]),
        },
        "coin_flip_log_loss": float(np.log(2)),
    }
    with_mkt = [p for p in preds if p.market is not None]
    if with_mkt:
        ym = [p.y for p in with_mkt]
        res["market"] = {
            "n": len(with_mkt),
            "log_loss": _ll(ym, [p.market for p in with_mkt]),
            "model_log_loss_same_games": _ll(ym, [p.model for p in with_mkt]),
            "brier": _brier(ym, [p.market for p in with_mkt]),
        }
    beats_elo = res["model"]["log_loss"] < res["elo"]["log_loss"]
    beats_mkt = (
        res["market"]["model_log_loss_same_games"] < res["market"]["log_loss"]
        if "market" in res
        else None
    )
    res["verdict"] = {
        "beats_elo": beats_elo,
        "beats_market": beats_mkt,
        "trust": bool(beats_elo and beats_mkt),
        "note": (
            "No market prices supplied: model is unproven against the market."
            if beats_mkt is None
            else ""
        ),
    }
    res["predictions"] = [
        {
            "game_id": p.game_id,
            "date": p.date.isoformat(),
            "blue": p.blue,
            "red": p.red,
            "y": p.y,
            "model": round(p.model, 4),
            "elo": round(p.elo, 4),
            "market": p.market,
        }
        for p in preds
    ]
    return res
