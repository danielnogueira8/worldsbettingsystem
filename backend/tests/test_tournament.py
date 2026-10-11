import numpy as np
import pytest

from app.config import worlds_config
from app.model.tournament import EventState, Format, Simulator


@pytest.fixture(scope="module")
def fmt():
    return Format.from_config(worlds_config())


def make(fmt, strengths=None, n_draws=4, spd=250, state=None, seed=1):
    rng = np.random.default_rng(seed)
    base = strengths if strengths is not None else rng.normal(0, 0.7, len(fmt.teams))
    draws = base + rng.normal(0, 0.05, (n_draws, len(fmt.teams)))
    return Simulator(fmt, draws, state=state, sims_per_draw=spd, seed=seed)


def total(block):
    return sum(block["p"].values())


def test_structure_invariants(fmt):
    res = make(fmt).run()
    t = res["teams"]
    assert total(t["champion"]) == pytest.approx(1)
    assert total(t["final"]) == pytest.approx(2)
    assert total(t["semis"]) == pytest.approx(4)
    assert total(t["knockout"]) == pytest.approx(8)
    assert total(t["swiss"]) == pytest.approx(16)
    assert total(t["3-0"]) == pytest.approx(2)
    assert total(t["0-3"]) == pytest.approx(2)
    assert sum(t["swiss"]["p"][x] for x in fmt.play_in) == pytest.approx(1)
    assert sum(v["p"] for v in res["region_champion"].values()) == pytest.approx(1)
    for k in ("champion", "final", "semis", "knockout"):
        for team in fmt.teams:
            assert t[k]["lo"][team] <= t[k]["p"][team] + 1e-9 <= t[k]["hi"][team] + 2e-9


def test_monotone_in_stage(fmt):
    t = make(fmt).run()["teams"]
    for team in fmt.teams:
        assert t["champion"]["p"][team] <= t["final"]["p"][team] <= t["semis"]["p"][team]
        assert t["semis"]["p"][team] <= t["knockout"]["p"][team] <= t["swiss"]["p"][team]


def test_stronger_team_wins_more(fmt):
    s = np.zeros(len(fmt.teams))
    s[fmt.teams.index("GEN")] = 3.0
    t = make(fmt, strengths=s).run()["teams"]
    assert t["champion"]["p"]["GEN"] > 0.5
    assert max(t["champion"]["p"][x] for x in fmt.teams if x != "GEN") < 0.1


def test_round_one_rules_and_bo_lengths(fmt):
    sim = make(fmt, n_draws=1, spd=1)
    played = []
    orig = sim._play

    def spy(a, b, bo):
        played.append((a, b, bo))
        return orig(a, b, bo)

    sim._play = spy
    for _ in range(200):
        played.clear()
        pw = sim._play_in()
        n_pi = len(played)
        records = sim._swiss(pw)
        swiss = played[n_pi:]
        r1 = swiss[:8]
        pools = {k: [pw if t == "PLAYIN_WINNER" else t for t in v] for k, v in fmt.pools.items()}
        for a, b, bo in r1:
            assert bo == 1
            assert fmt.region[a] != fmt.region[b]
            pa = next(k for k, v in pools.items() if a in v)
            pb = next(k for k, v in pools.items() if b in v)
            assert {pa, pb} in ({1, 4}, {2, 3})
        pairs = [frozenset((a, b)) for a, b, _ in swiss]
        assert len(pairs) == len(set(pairs)), "rematch in swiss"
        assert sorted(records.values()).count("3-0") == 2
        assert all(bo == 5 for *_, bo in played[:n_pi])
        assert len(swiss) == 33  # 8 + 8 + 8 + 6 + 3


def test_conditioning_on_known_results(fmt):
    st = EventState(play_in={
        "r1a": ("KC", "C9", "KC"), "r1b": ("MVK", "CBLOL2", "MVK"), "uf": ("KC", "MVK", "KC"),
        "lr1": ("C9", "CBLOL2", "C9"), "lf": ("MVK", "C9", "MVK"), "gf": ("KC", "MVK", "KC"),
    })
    res = make(fmt, state=st).run()["teams"]
    assert res["swiss"]["p"]["KC"] == 1.0
    assert res["swiss"]["p"]["C9"] == 0.0

    # Fix all of Swiss round 1 with GEN losing: GEN can no longer go 3-0
    pools = fmt.pools
    r1 = [("GEN", "CFO", "CFO"), ("AL", "DK", None), ("TL", "IG", None), ("G2", "KC", None),
          ("CBLOL1", "MKOI", None), ("TSW", "T1", None), ("HLE", "TES", None),
          ("BLG", "LYON", None)]
    assert all(a in pools[1] + pools[2] for a, *_ in r1)
    st.swiss_rounds = [r1]
    res = make(fmt, state=st).run()["teams"]
    assert res["3-0"]["p"]["GEN"] == 0.0
    assert res["0-3"]["p"]["CFO"] == 0.0


def test_matchup_interval(fmt):
    sim = make(fmt, n_draws=50)
    m = sim.matchup("GEN", "T1", 5)
    assert m["lo"] <= m["p"] <= m["hi"]
    m2 = sim.matchup("T1", "GEN", 5)
    assert m["p"] + m2["p"] == pytest.approx(1)
