"""SYNTHETIC demo data, for exercising the app without network access.

Everything written here is fake and tagged: games have source="synthetic", markets have
ids starting with "demo-". The API reports demo=true whenever synthetic games exist and
the frontend shows a banner. Never mix this with real data you intend to bet on:
`wbs demo --clear` removes it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import delete

from .db import Game, PmMarket, PmPriceTick, session
from .teams import worlds_teams

FILLER_PER_REGION = 6


def generate(seed: int = 7, days: int = 300, now: datetime | None = None) -> dict:
    rng = np.random.default_rng(seed)
    now = now or datetime.now()
    wt = worlds_teams()
    region_true = {"LCK": 0.9, "LPL": 0.8, "LEC": 0.1, "LCS": -0.3, "LCP": -0.4, "CBLOL": -0.7}
    teams = {c: t.region for c, t in wt.items()}
    for g in region_true:
        for i in range(FILLER_PER_REGION):
            teams[f"{g}-filler-{i}"] = g
    true = {t: region_true[g] + rng.normal(0, 0.45) for t, g in teams.items()}
    rows = []
    gid = 0
    for day in range(days):
        date = now - timedelta(days=days - day)
        for g in region_true:
            members = [t for t, r in teams.items() if r == g]
            for _ in range(2):
                a, b = rng.choice(members, 2, replace=False)
                for _ in range(rng.choice([1, 3, 5], p=[0.2, 0.6, 0.2]) // 2 + 1):
                    gid += 1
                    p = 1 / (1 + np.exp(-(true[a] - true[b] + 0.1)))
                    rows.append(_game(gid, date, a, b, teams, rng.random() < p, False))
        if day % 60 in range(50, 57):  # an international event every ~2 months
            pool = [t for t in teams if "filler" not in t or rng.random() < 0.1]
            for _ in range(6):
                a, b = rng.choice(pool, 2, replace=False)
                gid += 1
                p = 1 / (1 + np.exp(-(true[a] - true[b] + 0.1)))
                rows.append(_game(gid, date, a, b, teams, rng.random() < p, True))
    with session() as s:
        for r in rows:
            s.merge(Game(**r))
        _markets(s, rng, true, now)
        s.commit()
    return {"games": len(rows), "teams": len(teams)}


def _game(gid, date, a, b, teams, blue_win, intl):
    return {
        "id": f"synthetic:{gid}",
        "source": "synthetic",
        "date": date,
        "league": "SYNTH-INTL" if intl else f"SYNTH-{teams[a]}",
        "tournament": "synthetic",
        "is_international": bool(intl),
        "patch": None,
        "blue_team": a,
        "red_team": b,
        "blue_region": teams[a],
        "red_region": teams[b],
        "blue_win": bool(blue_win),
        "duration_s": None,
        "gold_diff_15": None,
        "series_id": None,
    }


def _markets(s, rng, true, now):
    wt = worlds_teams()
    strength = np.array([true[c] for c in wt])
    fair = np.exp(2.2 * strength)
    fair = fair / fair.sum()
    for i, (code, team) in enumerate(wt.items()):
        noisy = float(np.clip(fair[i] * np.exp(rng.normal(0, 0.35)), 0.002, 0.95))
        mid = round(noisy, 3)
        m = PmMarket(
            id=f"demo-win-{code}",
            event_id="demo-winner",
            event_title="Worlds 2026: Winner (DEMO)",
            event_slug="demo",
            slug=f"demo-{code}",
            question=f"Will {team.name} win Worlds 2026?",
            group_item_title=team.name,
            yes_token=None,
            no_token=None,
            neg_risk=True,
            active=True,
            closed=False,
            volume=float(rng.integers(5_000, 500_000)),
            liquidity=float(rng.integers(1_000, 50_000)),
            kind="champion",
            subject=code,
            tracked=True,
            raw={"outcomes": ["Yes", "No"], "demo": True},
        )
        s.merge(m)
        for k in range(24):
            drift = mid * float(np.exp(rng.normal(0, 0.03) * (24 - k) ** 0.5))
            bid = max(0.001, round(drift - 0.005, 3))
            ask = min(0.999, round(drift + 0.005, 3))
            s.add(
                PmPriceTick(
                    market_id=m.id,
                    ts=now - timedelta(hours=24 - k),
                    best_bid=bid,
                    best_ask=ask,
                    mid=(bid + ask) / 2,
                    bid_depth_2c=float(rng.integers(50, 3000)),
                    ask_depth_2c=float(rng.integers(50, 3000)),
                )
            )


def clear() -> None:
    with session() as s:
        s.execute(delete(PmPriceTick).where(PmPriceTick.market_id.like("demo-%")))
        s.execute(delete(PmMarket).where(PmMarket.id.like("demo-%")))
        s.execute(delete(Game).where(Game.source == "synthetic"))
        s.commit()
