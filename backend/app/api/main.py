"""HTTP API for the frontend. Also serves the built frontend from frontend/dist."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import pipeline
from ..config import ROOT, settings, worlds_config
from ..db import Bet, EventResult, Game, GprSnapshot, PmMarket, PmPriceTick, RatingRun, session
from ..teams import worlds_teams


class ResultIn(BaseModel):
    stage: str
    round: str
    team_a: str
    team_b: str
    winner: str = ""


class BetIn(BaseModel):
    market_id: str
    side: str
    price: float
    stake: float
    model_p: float | None = None
    note: str | None = None


class BetPatch(BaseModel):
    closing_price: float | None = None
    outcome: str | None = None
    note: str | None = None


class SimIn(BaseModel):
    draws: int = 1000
    sims_per_draw: int | None = None


class BacktestIn(BaseModel):
    international_only: bool = True
    since: str | None = None


def create_app(schedule: bool = False) -> FastAPI:
    app = FastAPI(title="Worlds Betting System")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.exception_handler(Exception)
    async def _unhandled(request, exc: Exception):
        # Surface the real cause in the dashboard instead of a bare "500".
        import logging
        import traceback

        logging.getLogger("wbs.api").error("".join(traceback.format_exception(exc)))
        return JSONResponse(
            status_code=500,
            content={"detail": f"{request.url.path}: {type(exc).__name__}: {exc}"[:500]},
        )

    if schedule:
        from ..scheduler import start

        @app.on_event("startup")
        def _start():
            app.state.scheduler = start()

    @app.get("/api/status")
    def status():
        with session() as s:
            n_games = s.scalar(select(func.count()).select_from(Game))
            last_game = s.scalar(select(func.max(Game.date)))
            n_markets = s.scalar(select(func.count()).select_from(PmMarket))
            last_tick = s.scalar(select(func.max(PmPriceTick.ts)))
            last_gpr = s.scalar(select(func.max(GprSnapshot.taken_at)))
            last_fit = s.scalar(select(func.max(RatingRun.created_at)))
        sim = pipeline.latest_simulation()
        bt = pipeline.latest_backtest()
        st = settings()
        from ..jobs import status as pipeline_status

        return {
            "demo": pipeline.is_demo(),
            "games": n_games,
            "last_game": last_game,
            "markets": n_markets,
            "last_price_tick": last_tick,
            "last_gpr": last_gpr,
            "last_fit": last_fit,
            "last_simulation": sim["created_at"] if sim else None,
            "backtest_verdict": (bt or {}).get("verdict"),
            "bankroll": st.bankroll,
            "kelly_fraction": st.kelly_fraction,
            "max_position": st.max_position_frac,
            "pipeline": pipeline_status(),
        }

    @app.get("/api/teams")
    def teams():
        cfg = worlds_config()
        pool_of = {t: int(k) for k, v in cfg["swiss"]["pools"].items() for t in v}
        for t in cfg["play_in"]["teams"]:
            pool_of[t] = 0
        lf = pipeline.latest_fit()
        gpr = pipeline.latest_gpr()
        out = []
        codes = list(worlds_teams())
        mean, cov = lf[1].strength(codes) if lf else (None, None)
        for i, (c, t) in enumerate(worlds_teams().items()):
            out.append(
                {
                    "code": c,
                    "name": t.name,
                    "region": t.region,
                    "pool": pool_of.get(c),
                    "strength": float(mean[i]) if lf else None,
                    "sd": float(cov[i, i] ** 0.5) if lf else None,
                    "gpr": gpr.get(c),
                }
            )
        out.sort(key=lambda r: -(r["strength"] or -99))
        return {
            "teams": out,
            "regions": dict(zip(lf[1].regions, lf[1].rho.tolist(), strict=True)) if lf else {},
            "side": lf[1].beta_side if lf else None,
            "n_games": lf[1].n_games if lf else 0,
        }

    @app.get("/api/matchup")
    def matchup(a: str, b: str, bo: int = 5):
        lf = pipeline.latest_fit()
        if not lf:
            raise HTTPException(404, "no rating fit yet")
        sim = pipeline.build_simulator(lf[1], n_draws=400, sims_per_draw=1, seed=0)
        if a not in sim.idx or b not in sim.idx:
            raise HTTPException(400, "unknown team code")
        return {"a": a, "b": b, "bo": bo, "game": lf[1].game_prob(a, b), **sim.matchup(a, b, bo)}

    @app.get("/api/simulation")
    def simulation():
        return pipeline.latest_simulation() or {}

    @app.post("/api/simulation/run")
    def run_simulation(body: SimIn):
        pipeline.simulate_and_store(body.draws, body.sims_per_draw)
        return pipeline.latest_simulation()

    @app.post("/api/fit")
    def run_fit():
        rf = pipeline.fit_and_store()
        return {"n_games": rf.n_games, "converged": rf.extras.get("converged")}

    @app.get("/api/edges")
    def edges():
        return pipeline.compute_edges()

    @app.get("/api/markets/{market_id}/ticks")
    def ticks(market_id: str, limit: int = 2000):
        with session() as s:
            rows = s.scalars(
                select(PmPriceTick)
                .where(PmPriceTick.market_id == market_id)
                .order_by(PmPriceTick.ts.desc())
                .limit(limit)
            ).all()
        return [
            {"ts": r.ts, "bid": r.best_bid, "ask": r.best_ask, "mid": r.mid} for r in reversed(rows)
        ]

    @app.post("/api/markets/discover")
    def discover():
        return {"upserted": pipeline.discover_markets()}

    @app.post("/api/markets/poll")
    def poll():
        return {"ticks": pipeline.poll_prices()}

    @app.get("/api/backtest")
    def backtest():
        return pipeline.latest_backtest() or {}

    @app.post("/api/backtest/run")
    def run_backtest(body: BacktestIn):
        since = datetime.fromisoformat(body.since) if body.since else None
        return pipeline.run_backtest(body.international_only, since)

    # -- event results ---------------------------------------------------------

    @app.get("/api/results")
    def results():
        with session() as s:
            return [
                {
                    "id": r.id,
                    "stage": r.stage,
                    "round": r.round,
                    "team_a": r.team_a,
                    "team_b": r.team_b,
                    "winner": r.winner,
                }
                for r in s.scalars(select(EventResult).order_by(EventResult.id))
            ]

    @app.post("/api/results")
    def add_result(body: ResultIn):
        codes = set(worlds_teams())
        if body.team_a not in codes or body.team_b not in codes:
            raise HTTPException(400, "team codes must be Worlds team codes")
        if body.winner and body.winner not in (body.team_a, body.team_b):
            raise HTTPException(400, "winner must be one of the two teams")
        with session() as s:
            existing = s.scalars(
                select(EventResult).where(
                    EventResult.stage == body.stage,
                    EventResult.round == body.round,
                    EventResult.team_a == body.team_a,
                    EventResult.team_b == body.team_b,
                )
            ).first()
            if existing:
                existing.winner = body.winner
            else:
                s.add(EventResult(**body.model_dump()))
            s.commit()
        return {"ok": True}

    @app.delete("/api/results/{rid}")
    def del_result(rid: int):
        with session() as s:
            r = s.get(EventResult, rid)
            if r:
                s.delete(r)
                s.commit()
        return {"ok": True}

    # -- bet journal -----------------------------------------------------------

    def _bet_json(b: Bet, q: str | None):
        clv = None
        if b.closing_price is not None:
            # closing line value: how much better our price was than the close, in prob pts
            clv = (
                (b.closing_price - b.price)
                if b.side == "YES"
                else ((1 - b.closing_price) - b.price)
            )
        pnl = None
        if b.outcome == "WON":
            pnl = b.stake * (1 / b.price - 1)
        elif b.outcome == "LOST":
            pnl = -b.stake
        elif b.outcome == "VOID":
            pnl = 0.0
        return {
            "id": b.id,
            "placed_at": b.placed_at,
            "market_id": b.market_id,
            "question": q,
            "side": b.side,
            "price": b.price,
            "stake": b.stake,
            "model_p": b.model_p,
            "closing_price": b.closing_price,
            "outcome": b.outcome,
            "note": b.note,
            "clv": clv,
            "pnl": pnl,
        }

    @app.get("/api/bets")
    def bets():
        with session() as s:
            rows = s.execute(
                select(Bet, PmMarket.question)
                .join(PmMarket, PmMarket.id == Bet.market_id, isouter=True)
                .order_by(Bet.placed_at.desc())
            ).all()
            return [_bet_json(b, q) for b, q in rows]

    @app.post("/api/bets")
    def add_bet(body: BetIn):
        if body.side not in ("YES", "NO") or not 0 < body.price < 1 or body.stake <= 0:
            raise HTTPException(400, "side YES|NO, 0<price<1, stake>0")
        with session() as s:
            if not s.get(PmMarket, body.market_id):
                raise HTTPException(400, "unknown market")
            b = Bet(**body.model_dump())
            s.add(b)
            s.commit()
            return {"id": b.id}

    @app.patch("/api/bets/{bid}")
    def patch_bet(bid: int, body: BetPatch):
        with session() as s:
            b = s.get(Bet, bid)
            if not b:
                raise HTTPException(404)
            for k, v in body.model_dump(exclude_unset=True).items():
                setattr(b, k, v)
            s.commit()
        return {"ok": True}

    # -- frontend --------------------------------------------------------------

    dist = Path(ROOT) / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = dist / path
            return FileResponse(f if path and f.is_file() else dist / "index.html")

    return app


app = create_app()
