"""SQLAlchemy schema. SQLite by default; any SQLAlchemy URL works."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Game(Base):
    """One game (map). The atomic unit the rating model is fit on."""

    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # source-prefixed id
    source: Mapped[str] = mapped_column(String)  # golgg | oracles | manual
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    league: Mapped[str] = mapped_column(String, index=True)
    tournament: Mapped[str] = mapped_column(String, default="")
    is_international: Mapped[bool] = mapped_column(Boolean, default=False)
    patch: Mapped[str | None] = mapped_column(String, nullable=True)
    blue_team: Mapped[str] = mapped_column(String, index=True)
    red_team: Mapped[str] = mapped_column(String, index=True)
    blue_region: Mapped[str] = mapped_column(String)
    red_region: Mapped[str] = mapped_column(String)
    blue_win: Mapped[bool] = mapped_column(Boolean)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gold_diff_15: Mapped[float | None] = mapped_column(Float, nullable=True)  # blue minus red
    series_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class GprSnapshot(Base):
    __tablename__ = "gpr_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    team: Mapped[str] = mapped_column(String)  # name as Riot shows it
    team_code: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float)


class PmMarket(Base):
    __tablename__ = "pm_markets"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # gamma market id
    event_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    event_title: Mapped[str | None] = mapped_column(String, nullable=True)
    event_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    question: Mapped[str] = mapped_column(String)
    group_item_title: Mapped[str | None] = mapped_column(String, nullable=True)
    yes_token: Mapped[str | None] = mapped_column(String, nullable=True)
    no_token: Mapped[str | None] = mapped_column(String, nullable=True)
    neg_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # What the market is about, as understood by app.model.markets.classify
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PmPriceTick(Base):
    __tablename__ = "pm_price_ticks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("pm_markets.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_depth_2c: Mapped[float | None] = mapped_column(Float, nullable=True)  # $ within 2c
    ask_depth_2c: Mapped[float | None] = mapped_column(Float, nullable=True)


class RatingRun(Base):
    __tablename__ = "rating_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    as_of: Mapped[datetime] = mapped_column(DateTime)
    n_games: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)  # teams, regions, covariance, side term


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    rating_run_id: Mapped[int | None] = mapped_column(ForeignKey("rating_runs.id"))
    n_sims: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSON)  # known results the sim conditioned on
    result: Mapped[dict] = mapped_column(JSON)


class EventResult(Base):
    """Actual results entered during the event, so the simulator conditions on reality."""

    __tablename__ = "event_results"
    __table_args__ = (UniqueConstraint("stage", "round", "team_a", "team_b"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String)  # play_in | swiss | knockout
    round: Mapped[str] = mapped_column(String)  # e.g. "1", "upper_final", "qf"
    team_a: Mapped[str] = mapped_column(String)
    team_b: Mapped[str] = mapped_column(String)
    winner: Mapped[str] = mapped_column(String, default="")  # "" = drawn, not yet played
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KV(Base):
    """Small JSON store for things like the latest backtest report."""

    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Bet(Base):
    __tablename__ = "bets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    market_id: Mapped[str] = mapped_column(ForeignKey("pm_markets.id"))
    side: Mapped[str] = mapped_column(String)  # YES | NO
    price: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    model_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)  # WON | LOST | VOID
    note: Mapped[str | None] = mapped_column(String, nullable=True)


_engine = None
_Session = None


def engine():
    global _engine, _Session
    if _engine is None:
        url = settings().db_url
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, **kw)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session() -> Session:
    engine()
    return _Session()


def reset_engine_for_tests(url: str) -> None:
    global _engine, _Session
    _engine = create_engine(url)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False)
