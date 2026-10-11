"""Turn a Polymarket market into something the model can price.

Polymarket questions are free text, so this is pattern matching. Anything we can't
classify confidently is marked `unsupported` and never gets an edge. Better to miss a
market than to price the wrong thing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..teams import find_in_text

REGION_WORDS = {
    "LCK": ["lck", "korea", "south korea"],
    "LPL": ["lpl", "china"],
    "LEC": ["lec", "europe", "emea"],
    "LCS": ["lcs", "north america"],
    "CBLOL": ["cblol", "brazil"],
    "LCP": ["lcp", "pacific", "vietnam", "taiwan", "japan"],
}


@dataclass
class Classified:
    kind: str  # champion | final | semis | knockout | swiss_3_0 | swiss_0_3 | region_champion
    #            | western_champion | match | unsupported
    subject: str | None = None  # team code, region, or "A|B|bo"
    reason: str = ""


def _has(text: str, *pats: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in pats)


def classify(
    question: str,
    event_title: str = "",
    group_item_title: str = "",
    outcomes: list[str] | None = None,
) -> Classified:
    q = question or ""
    ctx = f"{event_title} {q}"
    if not _has(ctx, r"worlds", r"world championship"):
        return Classified("unsupported", reason="not a Worlds market")
    if _has(
        ctx,
        r"\bmvp\b",
        r"\bplayer\b",
        r"\bkills?\b",
        r"\bdragons?\b",
        r"\bbaron\b",
        r"handicap",
        r"total maps",
        r"over/under",
        r"o/u",
    ):
        return Classified("unsupported", reason="prop market, no player/prop model")

    # Head-to-head match: outcomes are the two team names, or "A vs B" in the question.
    if outcomes and len(outcomes) == 2 and not {o.lower() for o in outcomes} <= {"yes", "no"}:
        a = find_in_text(outcomes[0])
        b = find_in_text(outcomes[1])
        if len(a) == 1 and len(b) == 1:
            bo = re.search(r"\bbo\s?([135])\b", ctx, re.IGNORECASE)
            if not bo:
                return Classified("unsupported", reason="match market without Bo length")
            return Classified("match", f"{a[0]}|{b[0]}|{bo.group(1)}")

    target = group_item_title or q
    teams = find_in_text(target) or find_in_text(q)

    if _has(ctx, r"western"):
        return Classified("western_champion", "WEST")
    if _has(ctx, r"winning region", r"region win", r"which region"):
        for region, words in REGION_WORDS.items():
            if _has(target, *[rf"\b{re.escape(w)}\b" for w in words]):
                return Classified("region_champion", region)
        return Classified("unsupported", reason="region market, region not recognised")
    if len(teams) != 1:
        return Classified("unsupported", reason=f"expected 1 team, found {teams}")
    t = teams[0]
    if _has(ctx, r"3-0"):
        return Classified("swiss_3_0", t)
    if _has(ctx, r"0-3"):
        return Classified("swiss_0_3", t)
    if _has(ctx, r"semi"):
        return Classified("semis", t)
    if _has(ctx, r"\bfinals?\b", r"make the final", r"reach the final") and not _has(ctx, r"win"):
        return Classified("final", t)
    if _has(ctx, r"knockout", r"quarter", r"playoffs?", r"advance", r"qualify", r"top 8"):
        return Classified("knockout", t)
    if _has(ctx, r"\bwin", r"winner", r"champion"):
        return Classified("champion", t)
    return Classified("unsupported", reason="unrecognised market type")


KIND_TO_SIM_KEY = {
    "champion": "champion",
    "final": "final",
    "semis": "semis",
    "knockout": "knockout",
    "swiss_3_0": "3-0",
    "swiss_0_3": "0-3",
}


def model_probability(c: Classified, sim: dict, sim_obj=None) -> dict | None:
    """Model P(YES) with a 90% interval, from a simulation result dict.

    Match markets need the live Simulator object (for posterior matchup probabilities).
    """
    if c.kind in KIND_TO_SIM_KEY:
        block = sim["teams"][KIND_TO_SIM_KEY[c.kind]]
        if c.subject not in block["p"]:
            return None
        return {k: block[k][c.subject] for k in ("p", "lo", "hi")}
    if c.kind == "region_champion":
        return sim["region_champion"].get(c.subject)
    if c.kind == "western_champion":
        return sim["western_champion"]
    if c.kind == "match" and sim_obj is not None:
        a, b, bo = c.subject.split("|")
        if a in sim_obj.idx and b in sim_obj.idx:
            return sim_obj.matchup(a, b, int(bo))
    return None
