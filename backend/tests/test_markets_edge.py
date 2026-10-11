import json

import pytest

from app.ingest.polymarket import is_worlds_event, parse_market, summarise_book
from app.model.edge import Quote, evaluate, kelly_fraction, overround
from app.model.markets import classify
from app.teams import find_in_text, resolve


def test_team_resolution():
    assert resolve("Gen.G") == "GEN"
    assert resolve("Team Liquid Alienware") == "TL"
    assert resolve("Some Academy Team") is None
    assert find_in_text("Will Team Liquid win Worlds 2026?") == ["TL"]
    assert find_in_text("Will T1 win Worlds 2026?") == ["T1"]
    assert find_in_text("Final: something") == []  # "AL" must not match inside words


@pytest.mark.parametrize("q,group,kind,subject", [
    ("Will Gen.G win Worlds 2026?", "Gen.G", "champion", "GEN"),
    ("Worlds 2026: Winner", "T1", "champion", "T1"),
    ("Will G2 Esports reach the final at Worlds 2026?", "", "final", "G2"),
    ("Will BLG make the semifinals at Worlds 2026?", "", "semis", "BLG"),
    ("Will HLE advance to the knockout stage of Worlds 2026?", "", "knockout", "HLE"),
    ("Will Dplus KIA go 3-0 in the Worlds 2026 Swiss Stage?", "", "swiss_3_0", "DK"),
    ("Worlds 2026 Winning Region", "LCK (South Korea)", "region_champion", "LCK"),
    ("Will a Western team win Worlds 2026?", "", "western_champion", "WEST"),
    ("Worlds 2026: Finals MVP", "Faker", "unsupported", None),
    ("Will Gen.G win the LCK 2026?", "", "unsupported", None),
])
def test_classify(q, group, kind, subject):
    c = classify(q, "", group)
    assert c.kind == kind, c
    if subject:
        assert c.subject == subject


def test_classify_match():
    c = classify("LoL: Gen.G vs T1 (BO5) - Worlds 2026 Quarterfinal", "", "", ["Gen.G", "T1"])
    assert (c.kind, c.subject) == ("match", "GEN|T1|5")
    c = classify("LoL: Gen.G vs T1 - Worlds 2026", "", "", ["Gen.G", "T1"])
    assert c.kind == "unsupported"


def test_parse_market_string_fields():
    raw = {"id": 1, "question": "Will T1 win Worlds 2026?", "outcomes": '["Yes", "No"]',
           "outcomePrices": '["0.18", "0.82"]', "clobTokenIds": json.dumps(["111", "222"]),
           "negRisk": True, "active": True, "closed": False, "volumeNum": 1234.5,
           "endDate": "2026-11-14T00:00:00Z"}
    m = parse_market(raw, {"id": 9, "title": "Worlds 2026: Winner", "slug": "worlds-2026"})
    assert m["yes_token"] == "111" and m["no_token"] == "222"
    assert m["outcome_prices"] == [0.18, 0.82]
    assert m["neg_risk"] and m["event_id"] == "9"
    assert m["end_date"].year == 2026


def test_is_worlds_event():
    assert is_worlds_event({"title": "LoL Worlds 2026: Winner"})
    assert not is_worlds_event({"title": "Valorant Champions 2026"})
    assert not is_worlds_event({"title": "Club World Championship 2025"})


def test_summarise_book():
    b = {"bids": [{"price": "0.40", "size": "100"}, {"price": "0.37", "size": "50"}],
         "asks": [{"price": "0.43", "size": "200"}, {"price": "0.44", "size": "10"}]}
    s = summarise_book(b)
    assert s["best_bid"] == 0.40 and s["best_ask"] == 0.43
    assert s["mid"] == pytest.approx(0.415)
    assert s["bid_depth_2c"] == pytest.approx(40.0)
    assert s["ask_depth_2c"] == pytest.approx(86 + 4.4)


def test_kelly():
    assert kelly_fraction(0.6, 0.5) == pytest.approx(0.2)
    assert kelly_fraction(0.4, 0.5) == 0.0


def test_evaluate_picks_side_and_respects_uncertainty():
    q = Quote(best_bid=0.30, best_ask=0.32, bid_depth=1e6, ask_depth=1e6)
    r = evaluate({"p": 0.45, "lo": 0.40, "hi": 0.50}, q, bankroll=1000)
    assert r.side == "YES" and r.flagged and r.stake > 0
    assert r.stake <= 50  # 5% cap
    r = evaluate({"p": 0.45, "lo": 0.20, "hi": 0.60}, q)
    assert r.side == "YES" and not r.flagged and r.stake == 0
    r = evaluate({"p": 0.15, "lo": 0.12, "hi": 0.18}, q)
    assert r.side == "NO" and r.flagged
    r = evaluate({"p": 0.31, "lo": 0.3, "hi": 0.32}, q)
    assert not r.flagged


def test_fee_reduces_edge():
    q = Quote(0.30, 0.32)
    assert evaluate({"p": 0.4}, q, fee=0.02).edge == pytest.approx(evaluate({"p": 0.4}, q).edge
                                                                 - 0.02)


def test_overround():
    assert overround([0.3, 0.3, 0.3], [0.29, 0.29, 0.29])["arb"]
    o = overround([0.35, 0.35, 0.35], [0.33, 0.33, 0.33])
    assert not o["arb"] and o["buy_all_yes_profit"] < 0


def test_postgres_url_normalised_and_config_shipped_in_package():
    from app.config import PACKAGE_DATA, worlds_config
    from app.db import normalise_url

    assert normalise_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_url("sqlite:///x.db") == "sqlite:///x.db"
    # The backend service deploys only backend/, so the team config must live inside it.
    assert (PACKAGE_DATA / "worlds2026.yaml").is_file()
    assert len(worlds_config()["teams"]) == 19


def test_postgres_engine_options_suit_serverless_pooler():
    from app.db import engine_kwargs

    kw = engine_kwargs("postgresql+psycopg://u:p@h-pooler/db?sslmode=require")
    assert kw["pool_pre_ping"] is True
    assert kw["connect_args"] == {"prepare_threshold": None}
    assert engine_kwargs("sqlite:///x.db") == {"connect_args": {"check_same_thread": False}}


def test_discovered_markets_store_and_price():
    """parse_market output, including its datetime end_date, must round-trip the DB."""
    from app import pipeline
    from app.ingest.polymarket import parse_market

    ev = {"id": 77, "title": "LoL Worlds 2026: Winner", "slug": "lol-worlds-2026-winner",
          "negRisk": True}
    raw = {"id": "m-gen", "question": "Will Gen.G win Worlds 2026?", "groupItemTitle": "Gen.G",
           "outcomes": '["Yes", "No"]', "outcomePrices": '["0.33", "0.67"]',
           "clobTokenIds": '["1", "2"]', "endDate": "2026-11-14T00:00:00Z", "active": True}
    m = parse_market(raw, ev)
    assert pipeline.upsert_markets([m]) == 1
    assert pipeline.upsert_markets([m]) == 1  # second pass updates in place
    from app.db import PmMarket, session

    with session() as s:
        row = s.get(PmMarket, "m-gen")
        assert row.kind == "champion" and row.subject == "GEN"
        assert row.end_date.year == 2026 and row.raw["end_date"].startswith("2026-11-14")


def test_classify_qualification_and_single_games():
    assert classify("Will FURIA Qualify for Worlds 2026?", "Team to Qualify for Worlds 2026?",
                    "").kind == "unsupported"
    ev = "LoL: Cloud9 vs Karmine Corp (BO5) - Worlds Play-In"
    c = classify("LoL: Cloud9 vs Karmine Corp - Game 3 Winner", ev, "", ["Cloud9", "Karmine Corp"])
    assert (c.kind, c.subject) == ("match", "C9|KC|1")
    c = classify(ev, ev, "", ["Cloud9", "Karmine Corp"])
    assert (c.kind, c.subject) == ("match", "C9|KC|5")


def test_api_errors_carry_their_cause(monkeypatch):
    from fastapi.testclient import TestClient

    from app import pipeline
    from app.api.main import create_app

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(pipeline, "compute_edges", boom)
    r = TestClient(create_app(), raise_server_exceptions=False).get("/api/edges")
    assert r.status_code == 500
    assert r.json()["detail"] == "/api/edges: RuntimeError: kaboom"
