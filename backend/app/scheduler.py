"""Background jobs. Each job logs and swallows its own errors so one bad source
doesn't stop the others."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from . import pipeline

log = logging.getLogger("wbs.scheduler")


def _safe(name, fn):
    def run():
        try:
            log.info("%s: %s", name, fn())
        except Exception:
            log.exception("%s failed", name)

    return run


def _refit_and_sim():
    pipeline.fit_and_store()
    return pipeline.simulate_and_store()["n_sims"]


def _scrape_worlds():
    """Pull this season's Worlds games so ratings learn from the event as it happens."""
    from .ingest import golgg

    n = 0
    for t in golgg.tournaments("S16"):
        if "world" in t["trname"].lower():
            n += pipeline.upsert_games(golgg.scrape_tournament(t["trname"]))
    return n


def start() -> BackgroundScheduler:
    now = datetime.now()
    s = BackgroundScheduler()
    s.add_job(
        _safe("pm-discover", pipeline.discover_markets), "interval", hours=1, next_run_time=now
    )
    s.add_job(
        _safe("pm-poll", pipeline.poll_prices),
        "interval",
        minutes=2,
        next_run_time=now + timedelta(seconds=30),
    )
    s.add_job(
        _safe("golgg-worlds", _scrape_worlds),
        "interval",
        hours=1,
        next_run_time=now + timedelta(minutes=1),
    )
    s.add_job(
        _safe("refit+simulate", _refit_and_sim),
        "interval",
        hours=2,
        next_run_time=now + timedelta(minutes=5),
    )
    s.start()
    return s
