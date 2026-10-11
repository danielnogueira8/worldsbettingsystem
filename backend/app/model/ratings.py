"""Bayesian Bradley-Terry team ratings with time decay, region offsets and a GPR prior.

Model for one game between blue team b and red team r:

    logit P(blue wins) = (theta_b + rho_region(b)) - (theta_r + rho_region(r)) + beta_side

* theta_t   within-region team strength, prior N(mu_t, team_prior_sd^2)
* rho_g     region strength offset,      prior N(nu_g, region_prior_sd^2)
* beta_side blue-side advantage,         prior N(0, 0.25^2)

Each game's log-likelihood is weighted by exp(-ln2 * age / half_life) and multiplied by
`international_weight` for international events, because those are the only games that
inform the region offsets.

Fit is MAP via L-BFGS with an analytic gradient. Uncertainty is a Laplace approximation:
the inverse Hessian at the mode is the posterior covariance. Team "strength" reported to
the rest of the app is s_t = theta_t + rho_region(t), in logit units per game.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

import numpy as np
from scipy.optimize import minimize

from .series import sigmoid

LN2 = np.log(2.0)


@dataclass
class GameRow:
    date: datetime
    blue: str
    red: str
    blue_region: str
    red_region: str
    blue_win: bool
    international: bool = False


@dataclass
class RatingParams:
    half_life_days: float = 180.0
    international_weight: float = 2.5
    team_prior_sd: float = 1.0
    region_prior_sd: float = 0.5
    side_prior_sd: float = 0.25
    # GPR prior: a team's prior strength = gpr_scale * zscore(GPR score)
    gpr_scale: float = 0.6


@dataclass
class RatingFit:
    as_of: datetime
    params: RatingParams
    teams: list[str]
    team_region: dict[str, str]
    regions: list[str]
    theta: np.ndarray
    rho: np.ndarray
    beta_side: float
    cov: np.ndarray  # full posterior covariance over [theta, rho, beta]
    n_games: int
    effective_games: float
    extras: dict = field(default_factory=dict)

    # -- derived -------------------------------------------------------------------

    def _team_index(self) -> dict[str, int]:
        return {t: i for i, t in enumerate(self.teams)}

    def strength_transform(self, teams: list[str]) -> np.ndarray:
        """Matrix A so that s = A @ params gives strengths for `teams`."""
        ti = self._team_index()
        ri = {g: i for i, g in enumerate(self.regions)}
        n_t, n_r = len(self.teams), len(self.regions)
        A = np.zeros((len(teams), n_t + n_r + 1))
        for k, t in enumerate(teams):
            A[k, ti[t]] = 1.0
            A[k, n_t + ri[self.team_region[t]]] = 1.0
        return A

    def params_vector(self) -> np.ndarray:
        return np.concatenate([self.theta, self.rho, [self.beta_side]])

    def strength(self, teams: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Posterior mean and covariance of strengths for `teams`."""
        A = self.strength_transform(teams)
        return A @ self.params_vector(), A @ self.cov @ A.T

    def sample_strengths(self, teams: list[str], n: int, rng: np.random.Generator) -> np.ndarray:
        mean, cov = self.strength(teams)
        cov = (cov + cov.T) / 2 + 1e-9 * np.eye(len(teams))
        return rng.multivariate_normal(mean, cov, size=n)

    def game_prob(self, a: str, b: str) -> float:
        """Neutral-side single-game P(a beats b), integrating over posterior uncertainty.

        Uses the probit approximation E[sigmoid(X)] ~ sigmoid(mu / sqrt(1 + pi*var/8)).
        """
        mean, cov = self.strength([a, b])
        mu = mean[0] - mean[1]
        var = cov[0, 0] + cov[1, 1] - 2 * cov[0, 1]
        return float(sigmoid(mu / np.sqrt(1 + np.pi * var / 8)))

    def to_json(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "params": asdict(self.params),
            "teams": self.teams,
            "team_region": self.team_region,
            "regions": self.regions,
            "theta": self.theta.tolist(),
            "rho": self.rho.tolist(),
            "beta_side": self.beta_side,
            "cov": self.cov.tolist(),
            "n_games": self.n_games,
            "effective_games": self.effective_games,
            "extras": self.extras,
        }

    @classmethod
    def from_json(cls, d: dict) -> RatingFit:
        return cls(
            as_of=datetime.fromisoformat(d["as_of"]),
            params=RatingParams(**d["params"]),
            teams=d["teams"],
            team_region=d["team_region"],
            regions=d["regions"],
            theta=np.array(d["theta"]),
            rho=np.array(d["rho"]),
            beta_side=d["beta_side"],
            cov=np.array(d["cov"]),
            n_games=d["n_games"],
            effective_games=d["effective_games"],
            extras=d.get("extras", {}),
        )


def _priors(
    teams: list[str],
    team_region: dict[str, str],
    regions: list[str],
    gpr: dict[str, float] | None,
    p: RatingParams,
) -> tuple[np.ndarray, np.ndarray]:
    """Prior means for theta and rho.

    Without GPR everything centres on 0. With GPR, each team's total prior strength is
    gpr_scale * z(GPR). That total is split into a region part (mean of the region's teams
    with a GPR score) and a within-region remainder, so theta and rho each get a sensible
    centre instead of the prior double-counting region strength.
    """
    mu = np.zeros(len(teams))
    nu = np.zeros(len(regions))
    if not gpr:
        return mu, nu
    scores = np.array(list(gpr.values()), dtype=float)
    m, sd = scores.mean(), scores.std() or 1.0
    total = {t: p.gpr_scale * (s - m) / sd for t, s in gpr.items()}
    for gi, g in enumerate(regions):
        vals = [total[t] for t in teams if team_region[t] == g and t in total]
        if vals:
            nu[gi] = float(np.mean(vals))
    ri = {g: i for i, g in enumerate(regions)}
    for ti, t in enumerate(teams):
        if t in total:
            mu[ti] = total[t] - nu[ri[team_region[t]]]
    return mu, nu


def fit(
    games: list[GameRow],
    as_of: datetime | None = None,
    params: RatingParams | None = None,
    gpr: dict[str, float] | None = None,
    team_region_override: dict[str, str] | None = None,
) -> RatingFit:
    """Fit ratings on games strictly before `as_of` (default: after the latest game)."""
    p = params or RatingParams()
    if as_of is None:
        as_of = max(g.date for g in games) if games else datetime.now()
    games = [g for g in games if g.date < as_of] if games else []

    # Region per team: latest region seen, unless overridden.
    team_region: dict[str, str] = {}
    for g in sorted(games, key=lambda g: g.date):
        team_region[g.blue] = g.blue_region
        team_region[g.red] = g.red_region
    if team_region_override:
        team_region.update({t: r for t, r in team_region_override.items()})
    for t in gpr or {}:
        team_region.setdefault(t, "UNKNOWN")

    teams = sorted(team_region)
    regions = sorted(set(team_region.values()))
    ti = {t: i for i, t in enumerate(teams)}
    ri = {g: i for i, g in enumerate(regions)}
    n_t, n_r = len(teams), len(regions)
    n_p = n_t + n_r + 1

    if games:
        b_idx = np.array([ti[g.blue] for g in games])
        r_idx = np.array([ti[g.red] for g in games])
        br_idx = np.array([ri[team_region[g.blue]] for g in games])
        rr_idx = np.array([ri[team_region[g.red]] for g in games])
        y = np.array([1.0 if g.blue_win else 0.0 for g in games])
        age = np.array([(as_of - g.date).total_seconds() / 86400 for g in games])
        w = np.exp(-LN2 * age / p.half_life_days)
        w = w * np.where([g.international for g in games], p.international_weight, 1.0)
    else:
        b_idx = r_idx = br_idx = rr_idx = np.array([], dtype=int)
        y = w = np.array([])

    # Design matrix X (n_games x n_p), sparse in spirit, dense here (a few thousand rows).
    X = np.zeros((len(y), n_p))
    rows = np.arange(len(y))
    if len(y):
        np.add.at(X, (rows, b_idx), 1.0)
        np.add.at(X, (rows, r_idx), -1.0)
        np.add.at(X, (rows, n_t + br_idx), 1.0)
        np.add.at(X, (rows, n_t + rr_idx), -1.0)  # same-region games cancel, as they should
        X[:, -1] = 1.0

    mu, nu = _priors(teams, team_region, regions, gpr, p)
    prior_mean = np.concatenate([mu, nu, [0.0]])
    prior_prec = np.concatenate(
        [
            np.full(n_t, 1 / p.team_prior_sd**2),
            np.full(n_r, 1 / p.region_prior_sd**2),
            [1 / p.side_prior_sd**2],
        ]
    )

    def nll(x):
        z = X @ x
        # weighted Bernoulli log-likelihood, numerically stable
        ll = w * (y * z - np.logaddexp(0, z))
        d = x - prior_mean
        return -ll.sum() + 0.5 * (prior_prec * d * d).sum()

    def grad(x):
        z = X @ x
        g = X.T @ (w * (y - sigmoid(z)))
        return -g + prior_prec * (x - prior_mean)

    res = minimize(nll, prior_mean.copy(), jac=grad, method="L-BFGS-B")
    x = res.x
    s = sigmoid(X @ x)
    H = (X * (w * s * (1 - s))[:, None]).T @ X + np.diag(prior_prec)
    cov = np.linalg.inv(H)

    return RatingFit(
        as_of=as_of,
        params=p,
        teams=teams,
        team_region=team_region,
        regions=regions,
        theta=x[:n_t],
        rho=x[n_t : n_t + n_r],
        beta_side=float(x[-1]),
        cov=cov,
        n_games=len(y),
        effective_games=float(w.sum()) if len(w) else 0.0,
        extras={"converged": bool(res.success), "message": str(res.message)},
    )
