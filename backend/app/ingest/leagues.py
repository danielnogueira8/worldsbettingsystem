"""League naming across sources -> region, and which events count as international."""

from __future__ import annotations

import re

# Oracle's Elixir league codes and gol.gg tournament-name prefixes -> region.
LEAGUE_REGION = {
    "LCK": "LCK",
    "LPL": "LPL",
    "LEC": "LEC",
    "LCS": "LCS",
    "LTA N": "LCS",
    "LTA North": "LCS",
    "CBLOL": "CBLOL",
    "LTA S": "CBLOL",
    "LTA South": "CBLOL",
    "LCP": "LCP",
    "PCS": "LCP",
    "VCS": "LCP",
    "LJL": "LCP",
}

INTERNATIONAL = {
    "WLDs",
    "MSI",
    "FST",
    "EWC",
    "Worlds",
    "World Championship",
    "Mid-Season Invitational",
    "First Stand",
    "Esports World Cup",
}

TIER1 = set(LEAGUE_REGION) | INTERNATIONAL | {"LTA"}


def is_international(league_or_tournament: str) -> bool:
    s = league_or_tournament or ""
    return any(re.search(rf"\b{re.escape(k)}\b", s, re.IGNORECASE) for k in INTERNATIONAL)


def region_of_league(league_or_tournament: str) -> str | None:
    s = league_or_tournament or ""
    # longest key first so "LTA North" beats "LTA"
    for k in sorted(LEAGUE_REGION, key=len, reverse=True):
        if re.search(rf"(^|\b){re.escape(k)}\b", s, re.IGNORECASE):
            return LEAGUE_REGION[k]
    return None
