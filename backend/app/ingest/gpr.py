"""Riot Global Power Rankings.

The GPR page is a JavaScript app. We load it in headless Chromium and capture every JSON
response, then look for one that's a list of teams with a numeric score. If Riot's JSON
shape changes, the fallback reads the rendered table text. If both fail, import a CSV
by hand (team,region,score) with `wbs gpr-import`.

UNVERIFIED: the sandbox this was written in could not reach lolesports.com.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

GPR_URL = "https://lolesports.com/en-US/gpr/2026/current"

NAME_KEYS = ("teamName", "name", "team", "displayName", "code", "acronym")
SCORE_KEYS = ("score", "points", "powerScore", "power_score", "rating", "value")


def _extract(obj) -> list[dict]:
    """Recursively find lists of dicts that look like {name, score} rows."""
    found = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        rows = []
        for x in obj:
            name = next((x[k] for k in NAME_KEYS if isinstance(x.get(k), str)), None)
            if name is None and isinstance(x.get("team"), dict):
                t = x["team"]
                name = next((t[k] for k in NAME_KEYS if isinstance(t.get(k), str)), None)
            score = next((x[k] for k in SCORE_KEYS if isinstance(x.get(k), (int, float))), None)
            if name and score is not None:
                rows.append(
                    {
                        "team": name,
                        "score": float(score),
                        "rank": x.get("rank") or x.get("position"),
                        "region": x.get("region") or x.get("league"),
                    }
                )
        if len(rows) >= 10:
            found.append(rows)
    if isinstance(obj, dict):
        for v in obj.values():
            found += _extract(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _extract(v)
    return found


def fetch_with_browser(url: str = GPR_URL, timeout_ms: int = 45000) -> list[dict]:
    from playwright.sync_api import sync_playwright

    captured = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()

        def on_response(r):
            if "json" in (r.headers.get("content-type") or ""):
                try:
                    captured.append(r.json())
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        text = page.inner_text("body")
        b.close()

    candidates = [rows for j in captured for rows in _extract(j)]
    if candidates:
        return max(candidates, key=len)
    rows = parse_rendered_text(text)
    if not rows:
        raise RuntimeError("GPR: no JSON or table rows recognised; use gpr-import with a CSV")
    return rows


def parse_rendered_text(text: str) -> list[dict]:
    """Fallback: lines like '1  Gen.G  LCK  1650.2'."""
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{1,3})\s+(.+?)\s+([A-Z]{2,6})\s+(\d{3,5}(?:\.\d+)?)\s*$", line)
        if m:
            rows.append(
                {
                    "rank": int(m.group(1)),
                    "team": m.group(2),
                    "region": m.group(3),
                    "score": float(m.group(4)),
                }
            )
    return rows


def load_csv(path: str | Path) -> list[dict]:
    with open(path) as f:
        return [
            {
                "team": r["team"],
                "region": r.get("region"),
                "score": float(r["score"]),
                "rank": int(r["rank"]) if r.get("rank") else None,
            }
            for r in csv.DictReader(f)
        ]
