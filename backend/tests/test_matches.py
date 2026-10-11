from fastapi.testclient import TestClient


def test_matches_from_series_market_and_derived_play_in():
    from app import demo, pipeline
    from app.api.main import create_app
    from app.ingest.polymarket import parse_market

    demo.generate(seed=5, days=60)
    pipeline.fit_and_store()
    ev = {"id": 501, "title": "LoL: Cloud9 vs Karmine Corp (BO5) - Worlds Play-In",
          "slug": "lol-c9-kc"}
    series = parse_market({"id": "pm-c9kc", "question": ev["title"],
                           "outcomes": '["Cloud9", "Karmine Corp"]',
                           "clobTokenIds": '["1", "2"]',
                           "gameStartTime": "2026-10-15T17:00:00Z"}, ev)
    game3 = parse_market({"id": "pm-c9kc-g3",
                          "question": "LoL: Cloud9 vs Karmine Corp - Game 3 Winner",
                          "outcomes": '["Cloud9", "Karmine Corp"]',
                          "clobTokenIds": '["3", "4"]'}, ev)
    pipeline.upsert_markets([series, game3])
    try:
        d = TestClient(create_app()).get("/api/matches").json()
        pairs = {frozenset((m["a"], m["b"])): m for m in d["scheduled"]}
        c9kc = pairs[frozenset(("C9", "KC"))]
        assert c9kc["bo"] == 5 and c9kc["stage"] == "play_in"
        assert c9kc["start_time"].startswith("2026-10-15")
        assert {mk["bo"] for mk in c9kc["markets"]} == {5, 1}
        m = c9kc["model"]
        assert 0 < m["p"] < 1 and m["lo"] <= m["p"] <= m["hi"]
        # the other opener is implied: four play-in teams, two opening matches
        derived = pairs[frozenset(("MVK", "FURIA"))]
        assert derived["bo"] == 5 and "derived" in derived["round"]
        # Swiss round 1 grids: 4x4 each, same-region pairings disallowed
        g1, g2 = d["swiss_r1"]["grids"]
        assert len(g1["rows"]) == 4 and len(g1["rows"][0]["cells"]) == 4
        gen = next(r for r in g1["rows"] if r["team"] == "GEN")
        dk = next(c for c in gen["cells"] if c["opp"] == "DK")
        assert dk["allowed"] is False  # both LCK
        cfo = next(c for c in gen["cells"] if c["opp"] == "CFO")
        assert cfo["allowed"] and 0 < cfo["p"] < 1
    finally:
        from app.db import PmMarket, session

        with session() as s:
            s.query(PmMarket).filter(PmMarket.id.in_(["pm-c9kc", "pm-c9kc-g3"])).delete()
            s.commit()
        demo.clear()
