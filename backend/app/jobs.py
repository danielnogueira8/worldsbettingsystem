"""Unattended jobs for CI runners: a one-off bootstrap and a frequent tick.

Each step records its outcome in the KV table under "pipeline", which the API exposes in
/api/status and the dashboard turns into a warning banner. A failing step never stops
the others, and `tick` exits 0 even when a step fails: a scheduled workflow that fails
every ten minutes would bury the owner in failure emails. The dashboard is where
failures show up.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from datetime import datetime, timedelta
from glob import glob

from . import pipeline
from .db import KV, session

DISCOVER_EVERY = timedelta(minutes=55)
SCRAPE_EVERY = timedelta(minutes=55)
REFIT_EVERY = timedelta(hours=2)
BACKTEST_EVERY = timedelta(hours=24)


def _state() -> dict:
    with session() as s:
        kv = s.get(KV, "pipeline")
        return dict(kv.value) if kv else {"steps": {}}


def _save(state: dict) -> None:
    with session() as s:
        s.merge(KV(key="pipeline", value=state))
        s.commit()


def _due(state: dict, step: str, every: timedelta, now: datetime) -> bool:
    last = (state["steps"].get(step) or {}).get("ok_at")
    return last is None or now - datetime.fromisoformat(last) >= every


def _run(state: dict, step: str, fn: Callable[[], object]) -> bool:
    now = datetime.now().isoformat(timespec="seconds")
    rec = dict(state["steps"].get(step) or {})
    try:
        result = fn()
        rec.update(ok=True, ok_at=now, at=now, result=str(result)[:300], error=None)
        print(f"[ok]   {step}: {result}")
    except Exception as e:  # noqa: BLE001 - every failure is recorded and reported
        rec.update(ok=False, at=now, error=f"{type(e).__name__}: {e}"[:500])
        print(f"[fail] {step}: {e}")
        traceback.print_exc()
    state["steps"][step] = rec
    _save(state)
    return rec["ok"]


def _refit_and_simulate() -> str:
    rf = pipeline.fit_and_store()
    sim = pipeline.simulate_and_store()
    top = sorted(sim["teams"]["champion"]["p"].items(), key=lambda x: -x[1])[:3]
    return f"{rf.n_games} games; top: " + ", ".join(f"{t} {p:.1%}" for t, p in top)


def _backtest() -> str:
    r = pipeline.run_backtest()
    if not r.get("n"):
        return "no international games to test"
    return f"n={r['n']} model={r['model']['log_loss']:.4f} elo={r['elo']['log_loss']:.4f}"


def _scrape_worlds() -> int:
    from .scheduler import _scrape_worlds as scrape

    return scrape()


def bootstrap(oracles_glob: str) -> bool:
    from .ingest import oracles

    state = _state()

    def load_games() -> int:
        paths = sorted(glob(oracles_glob))
        if not paths:
            raise FileNotFoundError(f"no files match {oracles_glob}")
        return sum(pipeline.upsert_games(oracles.load_csv(p)) for p in paths)

    ok = _run(state, "load_games", load_games)
    ok &= _run(state, "refit_simulate", _refit_and_simulate)
    ok &= _run(state, "backtest", _backtest)
    ok &= _run(state, "pm_discover", pipeline.discover_markets)
    ok &= _run(state, "pm_poll", pipeline.poll_prices)
    state["last_bootstrap"] = datetime.now().isoformat(timespec="seconds")
    _save(state)
    return ok


def tick() -> dict:
    now = datetime.now()
    state = _state()
    new_games = False
    if _due(state, "pm_discover", DISCOVER_EVERY, now):
        _run(state, "pm_discover", pipeline.discover_markets)
    _run(state, "pm_poll", pipeline.poll_prices)
    if _due(state, "golgg_worlds", SCRAPE_EVERY, now):
        before = state["steps"].get("golgg_worlds", {}).get("result")
        if _run(state, "golgg_worlds", _scrape_worlds):
            new_games = state["steps"]["golgg_worlds"]["result"] != before
    if new_games or _due(state, "refit_simulate", REFIT_EVERY, now):
        _run(state, "refit_simulate", _refit_and_simulate)
    if _due(state, "backtest", BACKTEST_EVERY, now):
        _run(state, "backtest", _backtest)
    state["last_tick"] = now.isoformat(timespec="seconds")
    _save(state)
    return state


def status() -> dict:
    return _state()
