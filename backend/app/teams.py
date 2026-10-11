"""Team identity: one canonical code per team, many aliases from many sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import worlds_config


@dataclass(frozen=True)
class Team:
    code: str
    name: str
    region: str
    aliases: tuple[str, ...]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache
def worlds_teams() -> dict[str, Team]:
    cfg = worlds_config()
    out = {}
    for code, t in cfg["teams"].items():
        aliases = tuple(t.get("aliases") or []) + (t["name"], code)
        out[code] = Team(code=code, name=t["name"], region=t["region"], aliases=aliases)
    return out


@lru_cache
def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for code, team in worlds_teams().items():
        for a in team.aliases:
            idx[_norm(a)] = code
    return idx


def resolve(name: str) -> str | None:
    """Map any source's team name to a Worlds team code, or None if it's not a Worlds team."""
    return _alias_index().get(_norm(name))


def find_in_text(text: str) -> list[str]:
    """Worlds team codes mentioned in free text (e.g. a Polymarket question).

    Longest aliases are matched first so 'Team Liquid' doesn't also count as 'TL'.
    Short aliases (<=3 chars) need word boundaries to avoid false hits.
    """
    found: list[str] = []
    remaining = text
    pairs = sorted(
        ((a, code) for code, t in worlds_teams().items() for a in t.aliases if a),
        key=lambda p: -len(p[0]),
    )
    for alias, code in pairs:
        pat = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
        if re.search(pat, remaining, flags=re.IGNORECASE):
            if code not in found:
                found.append(code)
            remaining = re.sub(pat, " ", remaining, flags=re.IGNORECASE)
    return found
