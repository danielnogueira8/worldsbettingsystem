"""Load Oracle's Elixir match-data CSVs (https://oracleselixir.com/tools/downloads).

One CSV per year, 12 rows per game: 10 players + 2 team rows (position == "team").
We use the team rows only. Download the yearly files by hand and point the CLI at them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .leagues import TIER1, is_international, region_of_league

COLS = [
    "gameid",
    "league",
    "date",
    "patch",
    "side",
    "position",
    "teamname",
    "result",
    "gamelength",
    "golddiffat15",
    "split",
    "playoffs",
    "year",
]


def load_csv(path: str | Path, tier1_only: bool = True) -> list[dict]:
    df = pd.read_csv(path, low_memory=False, usecols=lambda c: c in COLS)
    df = df[df["position"] == "team"]
    if tier1_only:
        df = df[df["league"].isin(TIER1)]
    blue = df[df["side"] == "Blue"].set_index("gameid")
    red = df[df["side"] == "Red"].set_index("gameid")
    both = blue.join(red, lsuffix="_b", rsuffix="_r", how="inner")

    # Team region = the regional league they play most in this file.
    regional = df[~df["league"].map(is_international)]
    home = (
        regional.groupby("teamname")["league"]
        .agg(lambda s: s.value_counts().index[0])
        .map(region_of_league)
        .to_dict()
    )

    # A league code can be "international" by name yet hold a single region's games, e.g.
    # the LPL's Worlds qualifier is filed as WLDs. Only count an event as international
    # when its teams come from more than one region.
    single_region: dict[str, str] = {}
    for league, g in df[df["league"].map(is_international)].groupby("league"):
        regions = {home.get(t) for t in g["teamname"]} - {None}
        if len(regions) == 1:
            single_region[league] = regions.pop()

    out = []
    for gid, r in both.iterrows():
        league = r["league_b"]
        intl = is_international(league) and league not in single_region
        fallback = single_region.get(league) or region_of_league(league) or "UNKNOWN"
        br = home.get(r["teamname_b"]) or fallback
        rr = home.get(r["teamname_r"]) or fallback
        gd = r.get("golddiffat15_b")
        out.append(
            {
                "id": f"oe:{gid}",
                "source": "oracles",
                "date": pd.to_datetime(r["date_b"]).to_pydatetime(),
                "league": league,
                "tournament": " ".join(
                    str(x) for x in (league, r.get("year_b"), r.get("split_b")) if pd.notna(x)
                ),
                "is_international": intl,
                "patch": None if pd.isna(r.get("patch_b")) else str(r["patch_b"]),
                "blue_team": r["teamname_b"],
                "red_team": r["teamname_r"],
                "blue_region": br,
                "red_region": rr,
                "blue_win": bool(int(r["result_b"]) == 1),
                "duration_s": None if pd.isna(r.get("gamelength_b")) else int(r["gamelength_b"]),
                "gold_diff_15": None if gd is None or pd.isna(gd) else float(gd),
                "series_id": None,
            }
        )
    return out


def parse_date(s: str) -> datetime:
    return pd.to_datetime(s).to_pydatetime()
