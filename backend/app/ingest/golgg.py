"""gol.gg scraper.

UNVERIFIED: this sandbox could not reach gol.gg, so the URL patterns and selectors below
are from memory of the site's structure, not from a live check. Every parser fails loudly
with the cached file path when a selector misses, so fixing it is a one-line change.
Prefer Oracle's Elixir CSVs (ingest/oracles.py) when they're available: same data,
no scraping.

Flow:
  1. tournaments(season)       POST /tournament/ajax.trlist.php  -> JSON list
  2. match_list(tournament)    GET  /tournament/tournament-matchlist/{name}/
  3. series_games(summary_id)  GET  /game/stats/{id}/page-summary/ -> game ids in series
  4. game(game_id)             GET  /game/stats/{id}/page-game/   -> teams, winner, time
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from .http import get_cached
from .leagues import TIER1, is_international, region_of_league

BASE = "https://gol.gg"


class ParseError(RuntimeError):
    pass


@dataclass
class MatchRow:
    summary_id: str
    team_a: str
    team_b: str
    score: str
    date: datetime | None
    tournament: str


def tournaments(season: str = "S16") -> list[dict]:
    txt = get_cached(
        f"{BASE}/tournament/ajax.trlist.php",
        method="POST",
        data={"season": season},
        max_age_s=6 * 3600,
    )
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise ParseError(f"tournament list for {season} was not JSON") from e


def is_world_championship(trname: str) -> bool:
    """The World Championship itself, not the Esports World Cup or a regional qualifier."""
    t = trname.lower()
    return ("world championship" in t or re.match(r"^worlds\b", t) is not None) and (
        "cup" not in t and "qualifier" not in t
    )


def is_tier1(trname: str) -> bool:
    head = trname.split(" 20")[0].strip()
    return head in TIER1 or is_international(trname) or region_of_league(trname) is not None


def match_list(trname: str, max_age_s: float | None = 3600) -> list[MatchRow]:
    url = f"{BASE}/tournament/tournament-matchlist/{quote(trname)}/"
    soup = BeautifulSoup(get_cached(url, max_age_s=max_age_s), "lxml")
    rows = []
    for tr in soup.select("table tr"):
        a = tr.find("a", href=re.compile(r"/game/stats/\d+/page-summary/"))
        if not a:
            continue
        sid = re.search(r"/game/stats/(\d+)/", a["href"]).group(1)
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        date = None
        for c in cells:
            m = re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)
            if m:
                date = datetime.fromisoformat(c)
        score = next((c for c in cells if re.fullmatch(r"\d\s*-\s*\d", c)), "")
        teams = [c for c in cells if c and c not in (score,) and not re.fullmatch(r"[\d\-: ]+", c)]
        # first cell is usually the match label ("A vs B"); team cells follow
        names = re.split(r"\s+vs\.?\s+", a.get_text(" ", strip=True))
        if len(names) == 2:
            ta, tb = names
        elif len(teams) >= 2:
            ta, tb = teams[-2], teams[-1]
        else:
            continue
        rows.append(MatchRow(sid, ta, tb, score, date, trname))
    if not rows:
        raise ParseError(f"no matches parsed from {url}; selector likely changed")
    return rows


def series_games(summary_id: str) -> list[str]:
    url = f"{BASE}/game/stats/{summary_id}/page-summary/"
    html = get_cached(url)
    ids = list(dict.fromkeys(re.findall(r"/game/stats/(\d+)/page-game/", html)))
    if not ids:
        # single-game series often link the game page as itself
        ids = [summary_id]
    return ids


def game(game_id: str) -> dict:
    url = f"{BASE}/game/stats/{game_id}/page-game/"
    html = get_cached(url)
    soup = BeautifulSoup(html, "lxml")
    blue = soup.select_one(".blue-line-header")
    red = soup.select_one(".red-line-header")
    if not blue or not red:
        raise ParseError(f"side headers not found in {url}")
    bt, rt = blue.get_text(" ", strip=True), red.get_text(" ", strip=True)

    def team_and_result(s: str) -> tuple[str, str]:
        m = re.match(r"(.+?)\s*-\s*(WIN|LOSS)\b", s, re.IGNORECASE)
        if not m:
            raise ParseError(f"cannot parse side header '{s}' in {url}")
        return m.group(1).strip(), m.group(2).upper()

    blue_team, bres = team_and_result(bt)
    red_team, _ = team_and_result(rt)
    dur = None
    m = re.search(r"Game Time\D*?(\d{1,2}):(\d{2})", soup.get_text(" ", strip=True))
    if m:
        dur = int(m.group(1)) * 60 + int(m.group(2))
    patch = None
    m = re.search(r"\bv(\d+\.\d+)\b", html)
    if m:
        patch = m.group(1)
    return {
        "blue_team": blue_team,
        "red_team": red_team,
        "blue_win": bres == "WIN",
        "duration_s": dur,
        "patch": patch,
    }


def scrape_tournament(trname: str, team_region: dict[str, str] | None = None) -> list[dict]:
    """All games in a tournament as dicts ready for the games table."""
    intl = is_international(trname)
    reg = region_of_league(trname)
    out = []
    for m in match_list(trname):
        for gid in series_games(m.summary_id):
            g = game(gid)
            br = (team_region or {}).get(g["blue_team"]) or (None if intl else reg) or "UNKNOWN"
            rr = (team_region or {}).get(g["red_team"]) or (None if intl else reg) or "UNKNOWN"
            out.append(
                {
                    "id": f"golgg:{gid}",
                    "source": "golgg",
                    "date": m.date or datetime.now(),
                    "league": trname.split(" 20")[0],
                    "tournament": trname,
                    "is_international": intl,
                    "patch": g["patch"],
                    "blue_team": g["blue_team"],
                    "red_team": g["red_team"],
                    "blue_region": br,
                    "red_region": rr,
                    "blue_win": g["blue_win"],
                    "duration_s": g["duration_s"],
                    "gold_diff_15": None,
                    "series_id": f"golgg:{m.summary_id}",
                }
            )
    return out
