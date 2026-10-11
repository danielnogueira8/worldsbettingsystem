"""Glue between the database and the model. Every scheduled job and API action ends here."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

import numpy as np
from sqlalchemy import delete, func, select

from .config import settings, worlds_config
from .db import (
    KV,
    EventResult,
    Game,
    GprSnapshot,
    PmMarket,
    PmPriceTick,
    RatingRun,
    SimulationRun,
    session,
)
from .model import backtest as bt
from .model.edge import Quote, evaluate, overround
from .model.markets import classify, model_probability
from .model.ratings import GameRow, RatingFit, RatingParams, fit
from .model.series import score_probs
from .model.tournament import EventState, Format, Simulator
from .teams import resolve, worlds_teams

# ---------------------------------------------------------------------------- games


def upsert_games(rows: list[dict]) -> int:
    with session() as s:
        for r in rows:
            s.merge(Game(**r))
        s.commit()
    return len(rows)


def prune_games(source: str, keep: Callable[[str], bool]) -> int:
    """Delete games from `source` whose tournament name fails `keep`."""
    with session() as s:
        rows = s.execute(select(Game.id, Game.tournament).where(Game.source == source)).all()
        drop = [gid for gid, t in rows if not keep(t or "")]
        if drop:
            s.execute(delete(Game).where(Game.id.in_(drop)))
            s.commit()
    return len(drop)


def _canon(name: str) -> str:
    return resolve(name) or name


def game_rows(before: datetime | None = None) -> list[tuple[str, GameRow]]:
    wt = worlds_teams()
    with session() as s:
        q = select(Game).order_by(Game.date)
        if before:
            q = q.where(Game.date < before)
        out = []
        for g in s.scalars(q):
            b, r = _canon(g.blue_team), _canon(g.red_team)
            out.append(
                (
                    g.id,
                    GameRow(
                        date=g.date,
                        blue=b,
                        red=r,
                        blue_region=wt[b].region if b in wt else g.blue_region,
                        red_region=wt[r].region if r in wt else g.red_region,
                        blue_win=g.blue_win,
                        international=g.is_international,
                    ),
                )
            )
        return out


def game_count() -> int:
    with session() as s:
        return s.scalar(select(func.count()).select_from(Game)) or 0


def is_demo() -> bool:
    with session() as s:
        return bool(
            s.scalar(select(func.count()).select_from(Game).where(Game.source == "synthetic"))
        )


# ---------------------------------------------------------------------------- GPR


def store_gpr(rows: list[dict]) -> int:
    now = datetime.now()
    with session() as s:
        for r in rows:
            s.add(
                GprSnapshot(
                    taken_at=now,
                    team=r["team"],
                    team_code=resolve(r["team"]),
                    region=r.get("region"),
                    rank=r.get("rank"),
                    score=r["score"],
                )
            )
        s.commit()
    return len(rows)


def latest_gpr() -> dict[str, float]:
    with session() as s:
        ts = s.scalar(select(func.max(GprSnapshot.taken_at)))
        if ts is None:
            return {}
        rows = s.scalars(select(GprSnapshot).where(GprSnapshot.taken_at == ts)).all()
        return {(r.team_code or r.team): r.score for r in rows}


# ---------------------------------------------------------------------------- ratings


def rating_params() -> RatingParams:
    st = settings()
    return RatingParams(
        half_life_days=st.half_life_days,
        international_weight=st.international_weight,
        team_prior_sd=st.team_prior_sd,
        region_prior_sd=st.region_prior_sd,
    )


def fit_and_store(as_of: datetime | None = None) -> RatingFit:
    rows = [g for _, g in game_rows()]
    override = {c: t.region for c, t in worlds_teams().items()}
    rf = fit(
        rows,
        as_of=as_of or datetime.now(),
        params=rating_params(),
        gpr=latest_gpr(),
        team_region_override=override,
    )
    with session() as s:
        s.add(
            RatingRun(
                as_of=rf.as_of,
                n_games=rf.n_games,
                params=rf.to_json()["params"],
                result=rf.to_json(),
            )
        )
        s.commit()
    return rf


def latest_fit() -> tuple[int, RatingFit] | None:
    with session() as s:
        run = s.scalars(select(RatingRun).order_by(RatingRun.id.desc()).limit(1)).first()
        return (run.id, RatingFit.from_json(run.result)) if run else None


# ---------------------------------------------------------------------------- event state


def event_state() -> EventState:
    st = EventState()
    with session() as s:
        res = s.scalars(select(EventResult).order_by(EventResult.id)).all()
    swiss: dict[int, list] = {}
    for r in res:
        w = r.winner or None
        if r.stage == "play_in":
            st.play_in[r.round] = (r.team_a, r.team_b, w)
        elif r.stage == "swiss":
            swiss.setdefault(int(r.round), []).append((r.team_a, r.team_b, w))
        elif r.stage == "knockout":
            if r.round.startswith("qf"):
                st.knockout_qf.append((r.team_a, r.team_b))
            if w:
                st.knockout_results[frozenset((r.team_a, r.team_b))] = w
    # only contiguous complete rounds 1..n are usable as fixed pairings
    for k in sorted(swiss):
        if k != len(st.swiss_rounds) + 1:
            break
        st.swiss_rounds.append(swiss[k])
    if len(st.knockout_qf) != 4:
        st.knockout_qf = []
    return st


# ---------------------------------------------------------------------------- simulation


def build_simulator(
    rf: RatingFit, n_draws: int = 1000, sims_per_draw: int = 20, seed: int | None = None
) -> Simulator:
    fmt = Format.from_config(worlds_config())
    rng = np.random.default_rng(seed)
    draws = rf.sample_strengths(fmt.teams, n_draws, rng)
    return Simulator(fmt, draws, state=event_state(), sims_per_draw=sims_per_draw, seed=seed)


def simulate_and_store(
    n_draws: int = 1000, sims_per_draw: int | None = None, seed: int | None = None
) -> dict:
    lf = latest_fit()
    if lf is None:
        fit_and_store()
        lf = latest_fit()
    run_id, rf = lf
    spd = sims_per_draw or max(1, settings().n_sims // n_draws)
    sim = build_simulator(rf, n_draws, spd, seed)
    result = sim.run()
    with session() as s:
        s.add(
            SimulationRun(
                rating_run_id=run_id,
                n_sims=result["n_sims"],
                state=sim.state.to_json(),
                result=result,
            )
        )
        s.commit()
    return result


def latest_simulation() -> dict | None:
    with session() as s:
        run = s.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(1)).first()
        if not run:
            return None
        return {
            "id": run.id,
            "created_at": run.created_at.isoformat(),
            "rating_run_id": run.rating_run_id,
            "state": run.state,
            **run.result,
        }


# ---------------------------------------------------------------------------- markets


def upsert_markets(markets: list[dict]) -> int:
    with session() as s:
        for m in markets:
            c = classify(
                m["question"],
                m.get("event_title") or "",
                m.get("group_item_title") or "",
                m.get("outcomes"),
            )
            existing = s.get(PmMarket, m["id"])
            fields = {
                k: m.get(k)
                for k in (
                    "event_id",
                    "event_title",
                    "event_slug",
                    "slug",
                    "question",
                    "group_item_title",
                    "yes_token",
                    "no_token",
                    "neg_risk",
                    "active",
                    "closed",
                    "end_date",
                    "volume",
                    "liquidity",
                    "fee_rate",
                )
            }
            # parse_market turns endDate into a datetime; JSON columns need plain values.
            raw = json.loads(json.dumps(m, default=str))
            fields.update(kind=c.kind, subject=c.subject, raw=raw)
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                s.add(PmMarket(id=m["id"], tracked=c.kind != "unsupported", **fields))
        s.commit()
    return len(markets)


def discover_markets() -> int:
    from .ingest.polymarket import Client

    return upsert_markets(Client().discover())


def poll_prices() -> int:
    from .ingest.polymarket import Client, summarise_book

    c = Client()
    n = 0
    with session() as s:
        for m in s.scalars(select(PmMarket).where(PmMarket.tracked, ~PmMarket.closed)):
            if not m.yes_token:
                continue
            q = summarise_book(c.book(m.yes_token))
            s.add(PmPriceTick(market_id=m.id, **q))
            n += 1
        s.commit()
    return n


def latest_ticks() -> dict[str, PmPriceTick]:
    with session() as s:
        sub = (
            select(PmPriceTick.market_id, func.max(PmPriceTick.id).label("mx"))
            .group_by(PmPriceTick.market_id)
            .subquery()
        )
        ticks = s.scalars(select(PmPriceTick).join(sub, PmPriceTick.id == sub.c.mx)).all()
        return {t.market_id: t for t in ticks}


def compute_edges() -> dict:
    st = settings()
    sim = latest_simulation()
    lf = latest_fit()
    sim_obj = build_simulator(lf[1], n_draws=400, sims_per_draw=1, seed=0) if lf else None
    ticks = latest_ticks()
    rows, by_event = [], {}
    with session() as s:
        markets = s.scalars(select(PmMarket).where(~PmMarket.closed)).all()
    for m in markets:
        t = ticks.get(m.id)
        c = classify(
            m.question, m.event_title or "", m.group_item_title or "", (m.raw or {}).get("outcomes")
        )
        row = {
            "market_id": m.id,
            "question": m.question,
            "event": m.event_title,
            "kind": c.kind,
            "subject": c.subject,
            "reason": c.reason,
            "volume": m.volume,
            "liquidity": m.liquidity,
            "slug": m.event_slug,
            "best_bid": t.best_bid if t else None,
            "best_ask": t.best_ask if t else None,
            "mid": t.mid if t else None,
            "tick_ts": t.ts.isoformat() if t else None,
            "edge": None,
        }
        mp = model_probability(c, sim, sim_obj) if sim and c.kind != "unsupported" else None
        if mp:
            row["model"] = mp
            if t:
                er = evaluate(
                    mp,
                    Quote(t.best_bid, t.best_ask, t.bid_depth_2c, t.ask_depth_2c),
                    fee=m.fee_rate or st.default_fee,
                    bankroll=st.bankroll,
                    kelly_mult=st.kelly_fraction,
                    max_position_frac=st.max_position_frac,
                )
                row["edge"] = er.to_json()
        rows.append(row)
        if m.neg_risk and m.event_id and t:
            by_event.setdefault(m.event_id, {"title": m.event_title, "asks": [], "bids": []})
            by_event[m.event_id]["asks"].append(t.best_ask or 1.0)
            by_event[m.event_id]["bids"].append(t.best_bid or 0.0)
    rows.sort(key=lambda r: -(r["edge"] or {}).get("edge", -9))
    structural = [
        {"event_id": k, "title": v["title"], "n": len(v["asks"]), **overround(v["asks"], v["bids"])}
        for k, v in by_event.items()
    ]
    return {"edges": rows, "structural": structural, "simulation_id": sim["id"] if sim else None}


# ---------------------------------------------------------------------------- backtest


def run_backtest(international_only: bool = True, since: datetime | None = None) -> dict:
    games = game_rows()

    def target(g: GameRow) -> bool:
        if since and g.date < since:
            return False
        return g.international if international_only else True

    res = bt.run(games, target, params=rating_params(), gpr=None)
    res["config"] = {
        "international_only": international_only,
        "since": since.isoformat() if since else None,
    }
    with session() as s:
        s.merge(KV(key="backtest", value=res))
        s.commit()
    return res


def latest_backtest() -> dict | None:
    with session() as s:
        kv = s.get(KV, "backtest")
        return kv.value if kv else None


def clear_event_results() -> None:
    with session() as s:
        s.execute(delete(EventResult))
        s.commit()


# ---------------------------------------------------------------------------- matches


def matches() -> dict:
    """Every matchup the system knows about, with model and market odds.

    Scheduled: series markets on Polymarket (they reveal real draws), pairings entered in
    the Results tab, and the play-in's other opening match once one is known (four teams,
    two opening matches). Swiss round 1 before its draw: every legal pairing.
    """
    lf = latest_fit()
    if not lf:
        return {"scheduled": [], "played": [], "swiss_r1": None, "message": "no rating fit"}
    rf = lf[1]
    sim = build_simulator(rf, n_draws=400, sims_per_draw=1, seed=0)
    cfg = worlds_config()
    st = settings()
    ticks = latest_ticks()

    def odds(a: str, b: str, bo: int) -> dict:
        m = sim.matchup(a, b, bo)
        g = rf.game_prob(a, b)
        scores = sorted(score_probs(g, bo), key=lambda x: -x[2])
        return {
            **m,
            "game": g,
            "scores": [{"a": sa, "b": sb, "p": round(pr, 4)} for sa, sb, pr in scores],
        }

    found: dict[frozenset, dict] = {}

    def add(a, b, **kw):
        key = frozenset((a, b))
        row = found.setdefault(
            key,
            {
                "a": a,
                "b": b,
                "bo": None,
                "stage": None,
                "round": None,
                "start_time": None,
                "winner": None,
                "markets": [],
            },
        )
        for k, v in kw.items():
            if v is not None and row.get(k) is None:
                row[k] = v
        return row

    with session() as s:
        results = s.scalars(select(EventResult).order_by(EventResult.id)).all()
        pms = s.scalars(select(PmMarket).where(~PmMarket.closed)).all()
    for r in results:
        bo = 5 if r.stage in ("play_in", "knockout") else None
        add(r.team_a, r.team_b, bo=bo, stage=r.stage, round=r.round, winner=r.winner or None)

    for m in pms:
        raw = m.raw or {}
        c = classify(m.question, m.event_title or "", m.group_item_title or "", raw.get("outcomes"))
        if c.kind != "match":
            continue
        a, b, bo = c.subject.split("|")
        stage = "play_in" if "play-in" in (m.event_title or "").lower() else None
        row = add(a, b, stage=stage)
        start = raw.get("start_time")
        if start and not row["start_time"]:
            row["start_time"] = start
        t = ticks.get(m.id)
        mk = {
            "market_id": m.id,
            "question": m.question,
            "bo": int(bo),
            "yes_team": a,
            "best_bid": t.best_bid if t else None,
            "best_ask": t.best_ask if t else None,
            "mid": t.mid if t else None,
            "slug": m.event_slug,
        }
        if int(bo) > 1:
            row["bo"] = row["bo"] or int(bo)
        row["markets"].append(mk)

    # Play-in: four teams, two opening matches. One known opener fixes the other.
    pi = list(cfg["play_in"]["teams"])
    pi_pairs = [k for k, v in found.items() if k <= set(pi) and v["stage"] in ("play_in", None)]
    if len(pi_pairs) == 1 and not any(r.stage == "play_in" and r.winner for r in results):
        rest = sorted(set(pi) - set(pi_pairs[0]))
        if len(rest) == 2:
            add(rest[0], rest[1], bo=5, stage="play_in", round="opening (derived)")
    for k, v in found.items():
        if k <= set(pi) and v["stage"] is None:
            v["stage"] = "play_in"
        if v["stage"] == "play_in":
            v["bo"] = v["bo"] or 5

    scheduled, played = [], []
    for row in found.values():
        a, b = row["a"], row["b"]
        if a not in sim.idx or b not in sim.idx:
            continue
        bo = row["bo"] or 1
        row["bo"] = bo
        row["model"] = odds(a, b, bo)
        row["names"] = {a: worlds_teams()[a].name, b: worlds_teams()[b].name}
        for mk in row["markets"]:
            p = odds(mk["yes_team"], b if mk["yes_team"] == a else a, mk["bo"])
            mk["model"] = p
            if mk["best_bid"] is not None or mk["best_ask"] is not None:
                mk["edge"] = evaluate(
                    p,
                    Quote(mk["best_bid"], mk["best_ask"]),
                    fee=st.default_fee,
                    bankroll=st.bankroll,
                    kelly_mult=st.kelly_fraction,
                    max_position_frac=st.max_position_frac,
                ).to_json()
        (played if row["winner"] else scheduled).append(row)
    scheduled.sort(key=lambda r: (r["start_time"] or "9999", r["stage"] or "z", r["a"]))

    # Swiss round 1 before the draw: pool 1 vs pool 4, pool 2 vs pool 3, no same region.
    swiss_r1 = None
    known_r1 = any(r.stage == "swiss" for r in results)
    if not known_r1:
        pools = {int(k): v for k, v in cfg["swiss"]["pools"].items()}
        region = {c: t.region for c, t in worlds_teams().items()}

        def grid(rows, cols):
            out = []
            for x in rows:
                cells = []
                for y in cols:
                    if y == "PLAYIN_WINNER" or x == "PLAYIN_WINNER":
                        cells.append({"opp": y, "allowed": True, "p": None})
                    else:
                        cells.append(
                            {"opp": y, "allowed": region[x] != region[y], "p": odds(x, y, 1)["p"]}
                        )
                out.append({"team": x, "cells": cells})
            return out

        swiss_r1 = {
            "draw_date": "2026-10-18",
            "grids": [
                {"title": "Pool 1 vs Pool 4", "cols": pools[4], "rows": grid(pools[1], pools[4])},
                {"title": "Pool 2 vs Pool 3", "cols": pools[3], "rows": grid(pools[2], pools[3])},
            ],
        }
    champion = None
    lsim = latest_simulation()
    if lsim:
        c = lsim["teams"]["champion"]
        top = sorted(c["p"].items(), key=lambda x: -x[1])[:4]
        champion = [{"team": t, "p": p, "lo": c["lo"][t], "hi": c["hi"][t]} for t, p in top]
    return {
        "scheduled": scheduled,
        "played": played,
        "swiss_r1": swiss_r1,
        "champion": champion,
        "names": {c: t.name for c, t in worlds_teams().items()},
    }
