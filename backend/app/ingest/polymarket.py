"""Polymarket read-only client: Gamma API for discovery, CLOB API for order books.

No auth needed for reads. Field handling follows docs.polymarket.com:
`outcomes`, `outcomePrices` and `clobTokenIds` arrive as JSON-encoded strings, aligned by
index. For Yes/No markets index 0 is YES.

UNVERIFIED against a live response from this sandbox (egress blocked). Parsing tolerates
both string-encoded and plain-list forms.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

SEARCH_TERMS = ["worlds 2026", "lol worlds", "league of legends worlds"]


def _list(v):
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            return []
    return list(v)


def _dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_worlds_event(ev: dict) -> bool:
    t = f"{ev.get('title', '')} {ev.get('slug', '')}".lower()
    return (
        ("worlds" in t or "world championship" in t)
        and ("lol" in t or "league of legends" in t or "2026" in t)
        and "valorant" not in t
        and "cs2" not in t
        and "counter" not in t
    )


def parse_market(m: dict, ev: dict | None = None) -> dict:
    outcomes = _list(m.get("outcomes"))
    tokens = _list(m.get("clobTokenIds"))
    prices = [_f(x) for x in _list(m.get("outcomePrices"))]
    fee_bps = _f(m.get("takerBaseFee"))
    return {
        "id": str(m.get("id")),
        "event_id": str(ev["id"]) if ev and ev.get("id") is not None else None,
        "event_title": (ev or {}).get("title"),
        "event_slug": (ev or {}).get("slug"),
        "slug": m.get("slug"),
        "question": m.get("question") or "",
        "group_item_title": m.get("groupItemTitle"),
        "outcomes": outcomes,
        "outcome_prices": prices,
        "yes_token": tokens[0] if len(tokens) > 0 else None,
        "no_token": tokens[1] if len(tokens) > 1 else None,
        "neg_risk": bool(m.get("negRisk") or (ev or {}).get("negRisk")),
        "active": bool(m.get("active", True)),
        "closed": bool(m.get("closed", False)),
        "end_date": _dt(m.get("endDate") or (ev or {}).get("endDate")),
        # Sports markets carry the scheduled start of the match itself.
        "start_time": _dt(m.get("gameStartTime") or (ev or {}).get("startTime")),
        "volume": _f(m.get("volumeNum") or m.get("volume")),
        "liquidity": _f(m.get("liquidityNum") or m.get("liquidity")),
        "fee_rate": fee_bps / 10000 if fee_bps else None,
    }


class Client:
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=20, headers={"User-Agent": "wbs/0.1"})

    def search_events(self, q: str) -> list[dict]:
        r = self.http.get(f"{GAMMA}/public-search", params={"q": q})
        r.raise_for_status()
        return r.json().get("events") or []

    def event(self, event_id: str) -> dict:
        r = self.http.get(f"{GAMMA}/events/{event_id}")
        r.raise_for_status()
        return r.json()

    def discover(self) -> list[dict]:
        """All markets in open Worlds 2026 events, de-duplicated."""
        seen_ev, out = set(), {}
        for term in SEARCH_TERMS:
            for ev in self.search_events(term):
                if ev.get("id") in seen_ev or not is_worlds_event(ev) or ev.get("closed"):
                    continue
                seen_ev.add(ev.get("id"))
                full = ev if ev.get("markets") else self.event(ev["id"])
                for m in full.get("markets") or []:
                    pm = parse_market(m, full)
                    out[pm["id"]] = pm
        return list(out.values())

    def book(self, token_id: str) -> dict:
        r = self.http.get(f"{CLOB}/book", params={"token_id": token_id})
        r.raise_for_status()
        return r.json()


def summarise_book(book: dict, window: float = 0.02) -> dict:
    bids = [(float(x["price"]), float(x["size"])) for x in book.get("bids") or []]
    asks = [(float(x["price"]), float(x["size"])) for x in book.get("asks") or []]
    bb = max((p for p, _ in bids), default=None)
    ba = min((p for p, _ in asks), default=None)
    mid = (bb + ba) / 2 if bb is not None and ba is not None else None
    bid_depth = sum(p * s for p, s in bids if bb is not None and p >= bb - window) if bids else 0
    ask_depth = sum(p * s for p, s in asks if ba is not None and p <= ba + window) if asks else 0
    return {
        "best_bid": bb,
        "best_ask": ba,
        "mid": mid,
        "bid_depth_2c": round(bid_depth, 2),
        "ask_depth_2c": round(ask_depth, 2),
    }
