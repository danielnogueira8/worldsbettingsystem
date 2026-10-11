"""Mispricing detection and position sizing.

Edges are measured against executable prices, not the midpoint:
  buying YES costs the YES ask
  buying NO  costs (1 - YES bid)   (a NO share is the complement of a YES share)

A bet is flagged only if the edge survives three haircuts:
  1. the fee,
  2. the model's own uncertainty: the conservative end of the 90% interval must still
     beat the price,
  3. a minimum edge threshold.

Sizing is fractional Kelly. For a binary contract bought at price c with true prob p:
    f* = (p - c) / (1 - c)
Stake = kelly_fraction * f* * bankroll, capped by max_position and by book depth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Quote:
    best_bid: float | None
    best_ask: float | None
    bid_depth: float | None = None  # $ available within 2c of best bid
    ask_depth: float | None = None


@dataclass
class EdgeResult:
    side: str | None  # YES | NO | None
    price: float | None
    model_p: float
    model_lo: float
    model_hi: float
    edge: float  # model prob of the side minus price paid, after fee
    conservative_edge: float  # same, using the pessimistic end of the interval
    kelly_f: float
    stake: float
    flagged: bool
    reason: str

    def to_json(self):
        return asdict(self)


def kelly_fraction(p: float, price: float) -> float:
    if price <= 0 or price >= 1:
        return 0.0
    return max(0.0, (p - price) / (1 - price))


def evaluate(
    model: dict,
    quote: Quote,
    fee: float = 0.0,
    min_edge: float = 0.03,
    bankroll: float = 1000.0,
    kelly_mult: float = 0.25,
    max_position_frac: float = 0.05,
) -> EdgeResult:
    p, lo, hi = model["p"], model.get("lo", model["p"]), model.get("hi", model["p"])
    cands = []
    if quote.best_ask is not None and 0 < quote.best_ask < 1:
        c = quote.best_ask + fee
        cands.append(("YES", c, p - c, lo - c, p, quote.ask_depth))
    if quote.best_bid is not None and 0 < quote.best_bid < 1:
        c = (1 - quote.best_bid) + fee
        cands.append(("NO", c, (1 - p) - c, (1 - hi) - c, 1 - p, quote.bid_depth))
    if not cands:
        return EdgeResult(None, None, p, lo, hi, 0, 0, 0, 0, False, "no executable quote")

    side, price, edge, cons, p_side, depth = max(cands, key=lambda x: x[2])
    f = kelly_fraction(p_side, price)
    stake = kelly_mult * f * bankroll
    stake = min(stake, max_position_frac * bankroll)
    if depth is not None:
        stake = min(stake, depth)

    if edge < min_edge:
        reason, flagged = f"edge {edge:+.3f} below threshold {min_edge:.3f}", False
    elif cons <= 0:
        reason, flagged = "edge does not survive model uncertainty", False
    else:
        reason, flagged = "edge survives fee and uncertainty", True
    if not flagged:
        stake = 0.0
    return EdgeResult(side, price, p, lo, hi, edge, cons, f, round(stake, 2), flagged, reason)


def overround(yes_asks: list[float], yes_bids: list[float]) -> dict:
    """Structural check on a mutually exclusive, exhaustive set of YES markets.

    sum(asks) < 1 -> buy every YES for less than the guaranteed $1 payout.
    sum(bids) > 1 -> buy every NO (sell every YES) for a guaranteed profit.
    Only valid when the set is truly exhaustive (e.g. every team in a negRisk winner event).
    """
    sa, sb = sum(yes_asks), sum(yes_bids)
    return {
        "sum_asks": sa,
        "sum_bids": sb,
        "buy_all_yes_profit": 1 - sa,
        "buy_all_no_profit": sb - 1,
        "arb": sa < 1 or sb > 1,
    }
