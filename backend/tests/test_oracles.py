import csv
import gzip

from app.ingest.oracles import load_csv

COLS = [
    "gameid",
    "league",
    "year",
    "split",
    "playoffs",
    "date",
    "patch",
    "side",
    "position",
    "teamname",
    "result",
    "gamelength",
    "golddiffat15",
]


def _game(gid, league, date, blue, red, blue_wins):
    return [
        [gid, league, 2026, "", 0, date, "26.1", "Blue", "team", blue, int(blue_wins), 1800, 500],
        [
            gid,
            league,
            2026,
            "",
            0,
            date,
            "26.1",
            "Red",
            "team",
            red,
            int(not blue_wins),
            1800,
            -500,
        ],
        [gid, league, 2026, "", 0, date, "26.1", "Blue", "top", "player", int(blue_wins), 1800, 0],
    ]


def test_loader_regions_and_single_region_qualifier(tmp_path):
    rows = []
    rows += _game("g1", "LPL", "2026-03-01 10:00:00", "Top Esports", "JD Gaming", True)
    rows += _game("g2", "LCK", "2026-03-01 11:00:00", "T1", "Gen.G", False)
    rows += _game("g3", "WLDs", "2026-09-17 10:00:00", "Top Esports", "JD Gaming", True)
    rows += _game("g4", "MSI", "2026-07-01 10:00:00", "Top Esports", "T1", False)
    rows += _game("g5", "LCKC", "2026-03-02 10:00:00", "T1 Academy", "Gen.G Global", True)
    path = tmp_path / "oe.csv.gz"
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)

    games = {g["id"]: g for g in load_csv(path)}
    assert set(games) == {"oe:g1", "oe:g2", "oe:g3", "oe:g4"}  # academy league dropped
    assert games["oe:g4"]["is_international"]  # MSI: two regions
    assert not games["oe:g3"]["is_international"]  # LPL-only qualifier filed as WLDs
    assert games["oe:g3"]["blue_region"] == "LPL"
    assert games["oe:g4"]["blue_region"] == "LPL" and games["oe:g4"]["red_region"] == "LCK"
    assert games["oe:g2"]["blue_win"] is False and games["oe:g1"]["blue_win"] is True
    assert games["oe:g1"]["gold_diff_15"] == 500.0


def test_world_championship_filter():
    from app.ingest.golgg import is_world_championship

    assert is_world_championship("World Championship 2026")
    assert is_world_championship("Worlds 2026 Play-In")
    assert not is_world_championship("Esports World Cup 2026")
    assert not is_world_championship("LPL 2026 Worlds Qualifier")
    assert not is_world_championship("LCK 2026 Rounds 1-2")


def test_prune_games_drops_other_tournaments_only():
    from datetime import datetime

    from app import pipeline
    from app.ingest.golgg import is_world_championship

    base = {"source": "golgg", "date": datetime(2026, 7, 1), "league": "x",
            "is_international": True, "patch": None, "blue_team": "T1", "red_team": "G2",
            "blue_region": "LCK", "red_region": "LEC", "blue_win": True, "duration_s": None,
            "gold_diff_15": None, "series_id": None}
    pipeline.upsert_games([
        {**base, "id": "golgg:t1", "tournament": "Esports World Cup 2026"},
        {**base, "id": "golgg:t2", "tournament": "World Championship 2026"},
        {**base, "id": "oe:t3", "source": "oracles", "tournament": "EWC 2026"},
    ])
    before = pipeline.game_count()
    assert pipeline.prune_games("golgg", is_world_championship) == 1
    assert pipeline.game_count() == before - 1
    assert pipeline.prune_games("golgg", is_world_championship) == 0
    pipeline.prune_games("golgg", lambda t: False)
    pipeline.prune_games("oracles", lambda t: t != "EWC 2026")
