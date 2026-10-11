"""Monte Carlo simulator for the Worlds 2026 format.

Stages (per Riot's 2026 primer; see app/data/worlds2026.yaml):

* Play-In: 4 teams, double elimination, all Bo5, 1 team advances to Swiss pool 4.
* Swiss: 16 teams, first to 3 wins advances, 3 losses eliminated. Bo3 when the match
  decides advancement or elimination (either team on 2 wins or 2 losses), else Bo1.
  Round 1 is pool 1 vs pool 4 and pool 2 vs pool 3 with no same-region matchups.
  Later rounds pair teams with the same record, no rematches.
* Knockout: 8 teams, single elimination Bo5. Each 3-0 team is drawn against a 3-2 team.
  The remaining four (three 3-1s and one 3-2) are paired at random. The two 3-0 teams
  are placed in opposite halves.

Uncertainty: the simulator takes a matrix of strength samples, shape (n_draws, n_teams),
drawn from the rating posterior. It runs `sims_per_draw` tournaments for each draw. The
average over everything is the predictive probability. The spread of per-draw averages is
the parameter uncertainty, which the edge filter uses to avoid betting on noise.

Conditioning on reality: `EventState` holds results already played. Known play-in results
and known Swiss rounds (pairings and any winners) are replayed exactly; the rest is
simulated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .series import series_win_prob, sigmoid

SWISS_RECORDS = ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"]


@dataclass
class EventState:
    # play-in: round name -> (team_a, team_b, winner or None)
    # rounds: r1a, r1b, uf, lr1, lf, gf
    play_in: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)
    # swiss: list of rounds; each round is a list of (team_a, team_b, winner or None)
    swiss_rounds: list[list[tuple[str, str, str | None]]] = field(default_factory=list)
    # knockout: quarterfinal pairs in bracket order (qf1, qf2 feed sf1; qf3, qf4 feed sf2)
    knockout_qf: list[tuple[str, str]] = field(default_factory=list)
    # knockout results: frozenset({a, b}) -> winner
    knockout_results: dict[frozenset, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: dict | None) -> EventState:
        if not d:
            return cls()
        return cls(
            play_in={k: tuple(v) for k, v in (d.get("play_in") or {}).items()},
            swiss_rounds=[[tuple(m) for m in r] for r in (d.get("swiss_rounds") or [])],
            knockout_qf=[tuple(p) for p in (d.get("knockout_qf") or [])],
            knockout_results={
                frozenset((a, b)): w for a, b, w in (d.get("knockout_results") or [])
            },
        )

    def to_json(self) -> dict:
        return {
            "play_in": {k: list(v) for k, v in self.play_in.items()},
            "swiss_rounds": [[list(m) for m in r] for r in self.swiss_rounds],
            "knockout_qf": [list(p) for p in self.knockout_qf],
            "knockout_results": [[*sorted(k), v] for k, v in self.knockout_results.items()],
        }


@dataclass
class Format:
    teams: list[str]
    region: dict[str, str]
    pools: dict[int, list[str]]  # pool 4 includes the literal "PLAYIN_WINNER"
    play_in: list[str]
    western_regions: set[str]

    @classmethod
    def from_config(cls, cfg: dict) -> Format:
        teams = list(cfg["teams"])
        return cls(
            teams=teams,
            region={c: t["region"] for c, t in cfg["teams"].items()},
            pools={int(k): list(v) for k, v in cfg["swiss"]["pools"].items()},
            play_in=list(cfg["play_in"]["teams"]),
            western_regions=set(cfg.get("western_regions") or []),
        )


def _interval(frac: np.ndarray, n: int, z: float = 1.645):
    """Mean and 90% interval of P(event | team strengths) across posterior draws.

    frac has shape (n_draws, k): the share of the n tournaments run for each draw in which
    the event happened. Its spread across draws mixes two things: real parameter
    uncertainty, and binomial noise from running only n tournaments per draw. Many draws
    with few tournaments each gives the most stable mean for a fixed budget, but then the
    binomial noise dominates the raw spread. So subtract it: the within-draw variance of a
    share is p(1-p)/n, estimated without bias by frac(1-frac)/(n-1).
    """
    mean = frac.mean(axis=0)
    if frac.shape[0] < 2:
        return mean, mean, mean
    total = frac.var(axis=0, ddof=1)
    within = (frac * (1 - frac)).mean(axis=0) / max(n - 1, 1)
    sd = np.sqrt(np.clip(total - within, 0, None))
    return mean, np.clip(mean - z * sd, 0, 1), np.clip(mean + z * sd, 0, 1)


class _NoPairing(Exception):
    pass


class Simulator:
    def __init__(
        self,
        fmt: Format,
        strength_draws: np.ndarray,
        state: EventState | None = None,
        sims_per_draw: int = 500,
        seed: int | None = None,
    ):
        self.f = fmt
        self.idx = {t: i for i, t in enumerate(fmt.teams)}
        self.draws = strength_draws
        self.state = state or EventState()
        self.sims_per_draw = sims_per_draw
        self.rng = np.random.default_rng(seed)
        # series win prob tensors per draw, keyed by best_of: (n_draws, T, T)
        diff = strength_draws[:, :, None] - strength_draws[:, None, :]
        pg = sigmoid(diff)
        self.p = {bo: series_win_prob(pg, bo) for bo in (1, 3, 5)}
        self._d = 0  # current draw

    # -- primitives --------------------------------------------------------------

    def _play(self, a: str, b: str, bo: int) -> str:
        pa = self.p[bo][self._d, self.idx[a], self.idx[b]]
        return a if self.rng.random() < pa else b

    def _resolve(self, a: str, b: str, bo: int, known: str | None) -> str:
        if known is not None:
            if known not in (a, b):
                raise ValueError(f"known winner {known} not in match {a} vs {b}")
            return known
        return self._play(a, b, bo)

    # -- play-in -----------------------------------------------------------------

    def _play_in(self) -> str:
        st = self.state.play_in
        teams = list(self.f.play_in)
        if "r1a" in st and "r1b" in st:
            a1, b1, _ = st["r1a"]
            a2, b2, _ = st["r1b"]
        else:
            self.rng.shuffle(teams)
            a1, b1, a2, b2 = teams

        def m(name, a, b):
            known = st.get(name)
            w = known[2] if known and set(known[:2]) == {a, b} else None
            winner = self._resolve(a, b, 5, w)
            return winner, (b if winner == a else a)

        w1, l1 = m("r1a", a1, b1)
        w2, l2 = m("r1b", a2, b2)
        wu, lu = m("uf", w1, w2)
        wl1, _ = m("lr1", l1, l2)
        wlf, _ = m("lf", lu, wl1)
        champ, _ = m("gf", wu, wlf)
        return champ

    # -- swiss -------------------------------------------------------------------

    def _pair(self, teams: list[str], ok) -> list[tuple[str, str]]:
        """Random perfect matching of `teams` under constraint ok(a, b). Backtracking."""
        teams = list(teams)
        self.rng.shuffle(teams)

        def rec(rem):
            if not rem:
                return []
            a = rem[0]
            cands = rem[1:]
            order = self.rng.permutation(len(cands))
            for j in order:
                b = cands[j]
                if ok(a, b):
                    rest = rec([t for t in cands if t != b])
                    if rest is not None:
                        return [(a, b), *rest]
            return None

        out = rec(teams)
        if out is None:
            raise _NoPairing
        return out

    def _swiss(self, playin_winner: str):
        pools = {
            k: [playin_winner if t == "PLAYIN_WINNER" else t for t in v]
            for k, v in self.f.pools.items()
        }
        all_teams = [t for v in pools.values() for t in v]
        W = dict.fromkeys(all_teams, 0)
        L = dict.fromkeys(all_teams, 0)
        played: set[frozenset] = set()
        reg = self.f.region

        for rnd in range(5):
            active = [t for t in all_teams if W[t] < 3 and L[t] < 3]
            if not active:
                break
            known_round = (
                self.state.swiss_rounds[rnd] if rnd < len(self.state.swiss_rounds) else None
            )
            if known_round:
                pairs = [(a, b) for a, b, _ in known_round]
                known = {frozenset((a, b)): w for a, b, w in known_round}
            else:
                known = {}
                if rnd == 0:
                    side1 = pools[1] + pools[2]
                    side2 = pools[4] + pools[3]
                    allowed = {frozenset((x, y)) for x in pools[1] for y in pools[4]} | {
                        frozenset((x, y)) for x in pools[2] for y in pools[3]
                    }

                    def ok0(a, b, allowed=allowed):
                        return frozenset((a, b)) in allowed and reg[a] != reg[b]

                    try:
                        pairs = self._pair(side1 + side2, ok0)
                    except _NoPairing:
                        pairs = self._pair(
                            side1 + side2, lambda a, b, al=allowed: frozenset((a, b)) in al
                        )
                else:
                    groups: dict[tuple[int, int], list[str]] = defaultdict(list)
                    for t in active:
                        groups[(W[t], L[t])].append(t)
                    pairs = []
                    for g in groups.values():
                        try:
                            pairs += self._pair(
                                g, lambda a, b, pl=played: frozenset((a, b)) not in pl
                            )
                        except _NoPairing:
                            # Rematch unavoidable in this bucket; real draw would float a team.
                            pairs += self._pair(g, lambda a, b: True)
            for a, b in pairs:
                decisive = W[a] == 2 or W[b] == 2 or L[a] == 2 or L[b] == 2
                bo = 3 if decisive else 1
                w = self._resolve(a, b, bo, known.get(frozenset((a, b))))
                loser = b if w == a else a
                W[w] += 1
                L[loser] += 1
                played.add(frozenset((a, b)))
        return {t: f"{W[t]}-{L[t]}" for t in all_teams}

    # -- knockout ----------------------------------------------------------------

    def _knockout(self, records: dict[str, str]) -> tuple[list[str], list[str], list[str], str]:
        """Returns (quarterfinalists, semifinalists, finalists, champion)."""
        if self.state.knockout_qf:
            qf = list(self.state.knockout_qf)
        else:
            r30 = [t for t, r in records.items() if r == "3-0"]
            r31 = [t for t, r in records.items() if r == "3-1"]
            r32 = [t for t, r in records.items() if r == "3-2"]
            self.rng.shuffle(r30)
            self.rng.shuffle(r31)
            self.rng.shuffle(r32)
            others = r31 + r32[len(r30) :]
            self.rng.shuffle(others)
            seeded = list(zip(r30, r32[: len(r30)], strict=True))
            rest = [(others[i], others[i + 1]) for i in range(0, len(others), 2)]
            # 3-0 teams in opposite halves: qf1 and qf3
            qf = [seeded[0], rest[0], seeded[1], rest[1]] if len(seeded) == 2 else seeded + rest
        known = self.state.knockout_results
        qf_w = [self._resolve(a, b, 5, known.get(frozenset((a, b)))) for a, b in qf]
        sf = [(qf_w[0], qf_w[1]), (qf_w[2], qf_w[3])]
        sf_w = [self._resolve(a, b, 5, known.get(frozenset((a, b)))) for a, b in sf]
        champ = self._resolve(sf_w[0], sf_w[1], 5, known.get(frozenset(sf_w)))
        return [t for p in qf for t in p], qf_w, sf_w, champ

    # -- driver ------------------------------------------------------------------

    def run(self) -> dict:
        n_draws = self.draws.shape[0]
        teams = self.f.teams
        # per-draw counters so we can report parameter uncertainty
        keys = ["swiss", "knockout", "semis", "final", "champion", *SWISS_RECORDS]
        per_draw = {k: np.zeros((n_draws, len(teams))) for k in keys}
        region_champ_draw = defaultdict(lambda: np.zeros(n_draws))
        western_draw = np.zeros(n_draws)
        ti = self.idx

        for d in range(n_draws):
            self._d = d
            for _ in range(self.sims_per_draw):
                pw = self._play_in()
                records = self._swiss(pw)
                for t, r in records.items():
                    per_draw["swiss"][d, ti[t]] += 1
                    per_draw[r][d, ti[t]] += 1
                ko, semis, finalists, champ = self._knockout(records)
                for t in ko:
                    per_draw["knockout"][d, ti[t]] += 1
                for t in semis:
                    per_draw["semis"][d, ti[t]] += 1
                for t in finalists:
                    per_draw["final"][d, ti[t]] += 1
                per_draw["champion"][d, ti[champ]] += 1
                g = self.f.region[champ]
                region_champ_draw[g][d] += 1
                if g in self.f.western_regions:
                    western_draw[d] += 1
        n = self.sims_per_draw
        out_teams = {}
        for k, arr in per_draw.items():
            mean, lo, hi = _interval(arr / n, n)
            out_teams[k] = {
                "p": dict(zip(teams, mean.round(5).tolist(), strict=True)),
                "lo": dict(zip(teams, lo.round(5).tolist(), strict=True)),
                "hi": dict(zip(teams, hi.round(5).tolist(), strict=True)),
            }
        regions = sorted(set(self.f.region.values()))

        def summ(arr):
            mean, lo, hi = _interval((arr / n)[:, None], n)
            return {
                "p": round(float(mean[0]), 5),
                "lo": round(float(lo[0]), 5),
                "hi": round(float(hi[0]), 5),
            }

        return {
            "n_sims": n_draws * n,
            "n_draws": n_draws,
            "sims_per_draw": n,
            "teams": out_teams,
            "region_champion": {g: summ(region_champ_draw[g]) for g in regions},
            "western_champion": summ(western_draw),
        }

    # -- head to head ------------------------------------------------------------

    def matchup(self, a: str, b: str, bo: int) -> dict:
        arr = self.p[bo][:, self.idx[a], self.idx[b]]
        return {
            "p": float(arr.mean()),
            "lo": float(np.quantile(arr, 0.05)),
            "hi": float(np.quantile(arr, 0.95)),
        }
