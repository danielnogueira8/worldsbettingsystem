"""Paths and tunables. Everything overridable through environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DATA = Path(__file__).resolve().parent / "data"
ON_VERCEL = bool(os.getenv("VERCEL"))

# Vercel's filesystem is read-only except /tmp, and /tmp does not survive between
# invocations. Anything that must persist (games, prices, bets) needs a real database:
# set DATABASE_URL (or WBS_DB_URL) to a Postgres URL.
_DEFAULT_DATA = Path("/tmp/wbs") if ON_VERCEL else ROOT / "data"
_DATA_DIR = Path(os.getenv("WBS_DATA_DIR", _DEFAULT_DATA))


def _db_url() -> str:
    for var in ("WBS_DB_URL", "DATABASE_URL", "POSTGRES_URL"):
        if os.getenv(var):
            return os.environ[var]
    return f"sqlite:///{_DATA_DIR / 'wbs.sqlite'}"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = _DATA_DIR
    db_url: str = _db_url()
    worlds_config: Path = Path(os.getenv("WBS_WORLDS_CONFIG", PACKAGE_DATA / "worlds2026.yaml"))

    # Scraping
    http_delay_s: float = float(os.getenv("WBS_HTTP_DELAY", "2.0"))
    user_agent: str = os.getenv(
        "WBS_USER_AGENT", "worlds-betting-system/0.1 (personal research; polite scraper)"
    )

    # Rating model
    half_life_days: float = float(os.getenv("WBS_HALF_LIFE_DAYS", "180"))
    international_weight: float = float(os.getenv("WBS_INTL_WEIGHT", "1.0"))
    team_prior_sd: float = float(os.getenv("WBS_TEAM_PRIOR_SD", "1.0"))
    region_prior_sd: float = float(os.getenv("WBS_REGION_PRIOR_SD", "0.5"))

    # Simulation
    n_sims: int = int(os.getenv("WBS_N_SIMS", "20000"))

    # Betting
    kelly_fraction: float = float(os.getenv("WBS_KELLY_FRACTION", "0.25"))
    max_position_frac: float = float(os.getenv("WBS_MAX_POSITION", "0.05"))
    bankroll: float = float(os.getenv("WBS_BANKROLL", "1000"))
    default_fee: float = float(os.getenv("WBS_DEFAULT_FEE", "0.0"))

    extra: dict = field(default_factory=dict)

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@lru_cache
def settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    return s


@lru_cache
def worlds_config() -> dict:
    with open(settings().worlds_config) as f:
        return yaml.safe_load(f)
