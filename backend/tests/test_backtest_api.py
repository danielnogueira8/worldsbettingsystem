from datetime import timedelta

from fastapi.testclient import TestClient

from app.model import backtest as bt

from .test_ratings import synth


def test_backtest_beats_coin_flip_and_elo_runs():
    games, _, _ = synth(n_days=200)
    rows = [(f"g{i}", g) for i, g in enumerate(games)]
    start = games[0].date + timedelta(days=120)
    res = bt.run(rows, lambda g: g.date >= start)
    assert res["n"] > 100
    assert res["model"]["log_loss"] < res["coin_flip_log_loss"]
    assert res["verdict"]["beats_market"] is None
    assert not res["verdict"]["trust"]  # never trusted without market comparison


def test_api_demo_flow():
    from app import demo, pipeline
    from app.api.main import create_app

    demo.generate(seed=3, days=120)
    pipeline.fit_and_store()
    pipeline.simulate_and_store(n_draws=8, sims_per_draw=50, seed=1)
    c = TestClient(create_app())
    st = c.get("/api/status").json()
    assert st["demo"] is True and st["games"] > 0
    teams = c.get("/api/teams").json()["teams"]
    assert len(teams) == 19 and all(t["strength"] is not None for t in teams)
    sim = c.get("/api/simulation").json()
    assert abs(sum(sim["teams"]["champion"]["p"].values()) - 1) < 1e-6
    edges = c.get("/api/edges").json()
    champ = [e for e in edges["edges"] if e["kind"] == "champion"]
    assert len(champ) == 19 and all(e["model"] for e in champ)
    assert edges["structural"] and edges["structural"][0]["n"] == 19
    m = c.get("/api/matchup", params={"a": "GEN", "b": "T1", "bo": 5}).json()
    assert 0 < m["p"] < 1
    r = c.post("/api/results", json={"stage": "swiss", "round": "1", "team_a": "GEN",
                                     "team_b": "CFO", "winner": "CFO"})
    assert r.status_code == 200
    assert c.post("/api/results", json={"stage": "swiss", "round": "1", "team_a": "GEN",
                                        "team_b": "XXX"}).status_code == 400
    b = c.post("/api/bets", json={"market_id": "demo-win-GEN", "side": "YES", "price": 0.3,
                                  "stake": 10, "model_p": 0.35})
    assert b.status_code == 200
    c.patch(f"/api/bets/{b.json()['id']}", json={"closing_price": 0.34, "outcome": "LOST"})
    bet = c.get("/api/bets").json()[0]
    assert abs(bet["clv"] - 0.04) < 1e-9 and bet["pnl"] == -10
    demo.clear()
    pipeline.clear_event_results()
    assert c.get("/api/status").json()["demo"] is False
