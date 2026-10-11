"""Command line entry point: `wbs <command>`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer

from . import pipeline

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _p(obj):
    typer.echo(json.dumps(obj, indent=2, default=str))


@app.command("load-oracles")
def load_oracles(paths: list[Path], all_leagues: bool = False):
    """Import Oracle's Elixir yearly CSVs."""
    from .ingest import oracles

    for p in paths:
        n = pipeline.upsert_games(oracles.load_csv(p, tier1_only=not all_leagues))
        typer.echo(f"{p}: {n} games")


@app.command("scrape-golgg")
def scrape_golgg(season: str = "S16", only: str | None = None, dry_run: bool = False):
    """Scrape Tier 1 + international tournaments for a gol.gg season (e.g. S14, S15, S16)."""
    from .ingest import golgg

    trs = [t["trname"] for t in golgg.tournaments(season) if golgg.is_tier1(t["trname"])]
    if only:
        trs = [t for t in trs if only.lower() in t.lower()]
    for t in trs:
        if dry_run:
            typer.echo(t)
            continue
        rows = golgg.scrape_tournament(t)
        typer.echo(f"{t}: {pipeline.upsert_games(rows)} games")


@app.command("gpr-snapshot")
def gpr_snapshot():
    """Capture Riot's Global Power Rankings with headless Chromium."""
    from .ingest import gpr

    typer.echo(f"stored {pipeline.store_gpr(gpr.fetch_with_browser())} GPR rows")


@app.command("gpr-import")
def gpr_import(path: Path):
    """Import GPR from a CSV with columns team,region,score[,rank]."""
    from .ingest import gpr

    typer.echo(f"stored {pipeline.store_gpr(gpr.load_csv(path))} GPR rows")


@app.command("pm-discover")
def pm_discover():
    typer.echo(f"{pipeline.discover_markets()} markets upserted")


@app.command("pm-poll")
def pm_poll():
    typer.echo(f"{pipeline.poll_prices()} order books stored")


@app.command()
def fit():
    rf = pipeline.fit_and_store()
    typer.echo(
        f"fit on {rf.n_games} games (effective {rf.effective_games:.0f}), "
        f"{len(rf.teams)} teams, converged={rf.extras.get('converged')}"
    )


@app.command()
def simulate(draws: int = 1000, sims_per_draw: int | None = None, seed: int | None = None):
    res = pipeline.simulate_and_store(draws, sims_per_draw, seed)
    champ = sorted(res["teams"]["champion"]["p"].items(), key=lambda x: -x[1])[:8]
    _p({"n_sims": res["n_sims"], "top_champion_odds": champ})


@app.command()
def edges():
    res = pipeline.compute_edges()
    _p(
        [
            {k: r[k] for k in ("question", "kind", "subject", "edge")}
            for r in res["edges"]
            if r["edge"]
        ][:15]
    )
    _p(res["structural"])


@app.command()
def backtest(all_games: bool = False, since: str | None = None):
    res = pipeline.run_backtest(
        international_only=not all_games, since=datetime.fromisoformat(since) if since else None
    )
    res.pop("predictions", None)
    _p(res)


@app.command()
def bootstrap(oracles: str = "../data/oracles/*.csv.gz"):
    """Load match data, fit, backtest, simulate, discover markets, poll prices."""
    import sys

    from . import jobs

    ok = jobs.bootstrap(oracles)
    sys.exit(0 if ok else 1)


@app.command("check-edges")
def check_edges():
    """Build the /api/edges payload exactly as the API does and validate it as JSON."""
    import time

    from fastapi.testclient import TestClient

    from .api.main import create_app

    t = time.time()
    r = TestClient(create_app(), raise_server_exceptions=True).get("/api/edges")
    typer.echo(f"/api/edges -> {r.status_code} in {time.time() - t:.1f}s, {len(r.content)} bytes")
    d = r.json()
    kinds = {}
    for e in d["edges"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    typer.echo(f"kinds: {kinds}")
    for e in d["edges"][:10]:
        typer.echo(f"  {e['question'][:60]:60} {e['kind']:16} {e.get('edge')}")


@app.command()
def tick():
    """One scheduler cycle: poll prices; discover, scrape, refit and backtest when due."""
    from . import jobs

    state = jobs.tick()
    failed = [k for k, v in state["steps"].items() if not v.get("ok")]
    typer.echo(f"tick done; failing steps: {failed or 'none'}")


@app.command()
def demo(clear: bool = False, seed: int = 7):
    """Load SYNTHETIC data to try the app offline. --clear removes it."""
    from . import demo as d

    if clear:
        d.clear()
        typer.echo("synthetic data removed")
        return
    _p(d.generate(seed=seed))
    pipeline.fit_and_store()
    pipeline.simulate_and_store(seed=seed)
    typer.echo("demo loaded: fit + simulation done")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, schedule: bool = False):
    """Run the API (and the built frontend). --schedule starts the background jobs."""
    import uvicorn

    from .api.main import create_app

    uvicorn.run(create_app(schedule=schedule), host=host, port=port)


def main():
    app()


if __name__ == "__main__":
    main()
