# Worlds 2026 Betting System: Plan

Goal: find mispriced odds on Polymarket for the League of Legends 2026 World Championship, using a model we can actually trust, and a frontend that shows where the edge is.

Blunt framing first. Polymarket's LoL Worlds markets had $7.8M on the T1 winner market alone in 2025 and $28M on the final. That's a reasonably efficient market. We don't win by being clever. We win by:

1. Having a calibrated model that beats the market on log loss in backtests. If it doesn't, we don't bet. The app will tell us that honestly.
2. Being fast on structural edges the crowd is slow on: format math (Swiss, Bo1 vs Bo3, double elim), stale prices after a result, and Yes/No pairs or multi-outcome books that don't sum to 1.
3. Sizing correctly (fractional Kelly), so being right 55% of the time compounds instead of blowing up.

Everything below serves those three.

---

## 1. Tournament facts the model has to encode

Worlds 2026, Oct 15 to Nov 14, 19 teams, USA.

| Stage | Dates | Format |
|---|---|---|
| Play-In | Oct 15-18, Los Angeles | 4 teams, double elimination, all Bo5, 1 team advances |
| Swiss | Oct 23-31, Allen TX | 16 teams, 5 rounds. Bo1 unless the match decides advancement/elimination (3rd win or 3rd loss), then Bo3. No rematches. Same-region allowed from round 2 |
| Knockout | Nov 3-14 | 8 teams, single elimination, Bo5. Final at Barclays Center Nov 14 |

Verify these against the official primer before coding the simulator (lolesports.com/news/worlds-2026-primer). The Swiss pairing rules matter a lot for "reach knockout" and "go 3-0" markets.

---

## 2. Data sources

### 2.1 gol.gg (match and game data)

Server-rendered HTML tables. No API. Scrape with `requests` + `BeautifulSoup`, polite rate limit (1 req/2s), cache every page to disk so we never refetch.

URL patterns to verify locally (sandbox can't reach gol.gg):

- Tournament list: `gol.gg/tournament/list/season-S16/split-ALL/`
- Tournament stats: `gol.gg/tournament/tournament-stats/{Tournament Name}/`
- Match list: `gol.gg/tournament/tournament-matchlist/{Tournament Name}/`
- Game page: `gol.gg/game/stats/{game_id}/page-game/`
- Team page: `gol.gg/teams/team-stats/{team_id}/split-ALL/tournament-ALL/`

Per game we want: date, tournament, patch, team A, team B, winner, side, duration, gold diff at 15, kills, dragons, towers. Per series: Bo format, final score.

Scope: all Tier 1 regional leagues (LCK, LPL, LEC, LTA North and South, LCP) plus MSI and Worlds, going back to 2023. That's roughly 3 full seasons. Enough to fit and to backtest Worlds 2023, 2024, 2025.

### 2.2 Riot Global Power Rankings (GPR)

`lolesports.com/en-US/gpr/2026/current`. Riot's own Elo-like rating with regional strength weighting, 2-year team window, 3-year league window, higher weights for international and knockout matches.

The page is a JS app. Open devtools, find the JSON the page fetches, hit that directly. If it's locked down, Playwright headless and parse the rendered table. Store a daily snapshot: team, rank, score.

Use: GPR becomes one feature and a sanity check, not the model. Riot built it for content, not for betting. But it already encodes cross-region strength, which is the hardest thing to estimate from match data alone (regions rarely play each other). Treat it as a strong prior.

### 2.3 Polymarket

Two public APIs, no auth for reads:

- Gamma API (`gamma-api.polymarket.com`): market discovery. `/public-search?q=worlds`, `/events?tag_slug=...`. Each market returns `outcomePrices`, `clobTokenIds`, `question`, `endDate`, volume, liquidity.
- CLOB API (`clob.polymarket.com`): live prices. `/midpoint?token_id=`, `/price?token_id=&side=`, `/book?token_id=`. Index 0 of `clobTokenIds` is Yes, index 1 is No.

Markets to expect (based on 2025): outright winner (one Yes/No market per team under one event), per-series winner, probably "reach final" and "reach knockout", maybe map handicaps. We poll Gamma hourly for new markets and CLOB every 1-2 minutes for prices on markets we track. Store every price tick. That tick history is also how we measure closing line value later.

Verify field names against docs.polymarket.com. Community mirrors drift.

Note on fees: Polymarket has charged taker fees on some sports markets. Pull the fee schedule per market and bake it into the edge calculation. An edge smaller than fee plus half-spread isn't an edge.

---

## 3. The math

### 3.1 Team strength: Bayesian Bradley-Terry with time decay

Each team gets a latent strength `θ_i`. Probability team i beats team j in a single game:

```
P(i beats j) = σ(θ_i - θ_j + β_side * side)
```

Fit on game-level results (not series), because games are the atomic unit and Bo5s give us 3 to 5 observations each. Weight each game by `exp(-λ * days_ago)` with λ tuned so a game 180 days old counts about half. Add a small side term (blue side has historically won around 52 to 53%).

Why not Elo? Elo is sequential and sensitive to ordering and K. BT fit by MAP over the whole window is more stable, gives us a posterior (uncertainty) per team, and lets us weight international games higher. We'll keep an Elo as a baseline to beat.

Cross-region problem: LCK teams almost only play LCK teams. BT can rank within a region but not across. Fixes, in order:

1. International results (MSI, Worlds, First Stand) are the only direct cross-region data. Weight them 2 to 3x.
2. A region offset `ρ_r` added to every team in region r, fit from international results with a prior centered on Riot's GPR league strength. This is the single most important modeling decision and the one most likely to be wrong, so it gets its own tuning in backtest.
3. GPR score as a prior mean for `θ_i` with a prior variance we tune.

Optional (phase 2): margin of victory. Gold diff at 15 and game duration carry real signal about how lopsided a game was. A 25-minute stomp and a 45-minute coinflip both count as one win in plain BT. Add a second likelihood term on standardized gold diff. Backtest decides whether it helps.

### 3.2 Game probability to series probability

Given single-game win prob `p`:

```
Bo1: p
Bo3: p^2 * (3 - 2p)
Bo5: p^3 * (10 - 15p + 6p^2)
```

This assumes games are independent with fixed `p`. Known to be slightly wrong (momentum, draft adaptation), but the error is small and symmetric. We can test for it on historical Bo5s.

Important consequence: Bo5 amplifies favorites. A 60% game-win favorite is 68% in a Bo5. The market sometimes prices series like games. That's a recurring edge to look for.

### 3.3 Tournament simulation (Monte Carlo)

Simulate the whole bracket 100,000 times with the exact format rules in section 1:

- Play-in double elim Bo5
- Swiss with correct pairing logic (group by record, no rematches, random draw within constraints, Bo3 for deciding matches)
- Single elim Bo5 knockout with the actual draw once known

Each simulation samples `θ` from the posterior, not the point estimate. That propagates model uncertainty into the outputs.

Outputs per team: P(win), P(final), P(top 8), P(3-0 Swiss), P(0-3 Swiss), expected placement. These map directly onto Polymarket's markets.

Re-run after every result. A Swiss result changes pairings and conditional probabilities a lot. This is where the crowd is slowest.

### 3.4 Edge detection

For each tracked market:

```
p_model      = model probability (with 90% credible interval from posterior)
p_market     = midpoint of CLOB book, adjusted for fee
edge         = p_model - p_market
```

Flag a bet only when edge exceeds the credible interval half-width plus fee plus half-spread. That's the "is this real or is it noise" filter.

Also check structural stuff that needs no model:

- Sum of Yes prices across all "Team X wins Worlds" markets. Under 1 is free money (buy all). Over 1.05 means the book is wide and we should be fussy about entries.
- Yes price + No price within a single market vs 1.
- Series market vs implied series prob from the same market's game-level pricing, if both exist.
- "Reach final" price vs sum of "win" prices for the two teams on that side of the bracket.

### 3.5 Sizing

Fractional Kelly at 0.25:

```
f* = (p * b - q) / b      where b = (1 - price) / price, q = 1 - p
stake = 0.25 * f* * bankroll
```

Cap any single position at 5% of bankroll. Polymarket books are thin on some markets. Stake also capped at what the book can absorb within 2 cents of midpoint.

### 3.6 Calibration and backtest (the part that keeps us honest)

Walk-forward backtest on Worlds 2023, 2024, 2025 and MSI 2024, 2025. For each match, fit the model only on data before that date, predict, record.

Metrics:

- Log loss and Brier score, model vs market closing price vs GPR-only vs Elo baseline.
- Calibration curve (predicted 70% should win about 70%).
- Simulated P&L with the sizing rule against historical Polymarket prices where we can get them (Polymarket data API has resolved markets with price history).

Decision rule: if the model's log loss on held-out international matches isn't better than the market's, the frontend shows that in red and the recommended stake is zero across the board. We don't bet a model that loses to the crowd.

---

## 4. Architecture

Monorepo. Python backend, React frontend, SQLite to start (Postgres later if needed, the schema is the same via SQLAlchemy).

```
worldsbettingsystem/
├── backend/
│   ├── app/
│   │   ├── ingest/
│   │   │   ├── golgg.py          # scraper + HTML cache
│   │   │   ├── gpr.py            # Riot power rankings snapshot
│   │   │   └── polymarket.py     # Gamma discovery + CLOB price polling
│   │   ├── model/
│   │   │   ├── ratings.py        # Bradley-Terry fit (scipy / numpyro)
│   │   │   ├── series.py         # Bo1/Bo3/Bo5 math
│   │   │   ├── tournament.py     # Worlds 2026 format simulator
│   │   │   ├── edge.py           # mispricing + Kelly
│   │   │   └── backtest.py       # walk-forward evaluation
│   │   ├── db/                   # SQLAlchemy models + Alembic migrations
│   │   ├── api/                  # FastAPI routes
│   │   └── scheduler.py          # APScheduler jobs
│   ├── tests/
│   └── pyproject.toml
├── frontend/                     # Vite + React + TypeScript + Tailwind + Recharts
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx     # edges ranked by expected value
│       │   ├── Teams.tsx         # ratings, GPR, posterior intervals
│       │   ├── Simulation.tsx    # bracket outcome probabilities
│       │   ├── Markets.tsx       # all Polymarket markets, model vs market
│       │   ├── Backtest.tsx      # calibration, log loss, P&L
│       │   └── Journal.tsx       # bets placed, CLV, running P&L
│       └── api/
├── data/                         # raw HTML cache + sqlite (gitignored)
├── docs/
└── docker-compose.yml
```

Core tables: `teams`, `games`, `series`, `tournaments`, `gpr_snapshots`, `ratings` (one row per team per fit date), `pm_markets`, `pm_price_ticks`, `simulations`, `edges`, `bets`.

Scheduler jobs:

| Job | Cadence |
|---|---|
| gol.gg incremental scrape | every 6h, plus manual trigger after a match day |
| GPR snapshot | daily |
| Polymarket market discovery | hourly |
| Polymarket price poll | every 2 min on tracked markets |
| Refit ratings + rerun simulation | on new game data |
| Recompute edges | on every price poll or new sim |

### 4.1 Frontend pages

- Dashboard: table of live edges sorted by EV. Columns: market, model p with interval, market p, edge, recommended stake, liquidity, link to Polymarket. Red banner if backtest says the model doesn't beat the market.
- Teams: each team's rating, interval, GPR score, recent form. Sparkline of rating over time.
- Simulation: heatmap of P(win), P(final), P(top 8) per team. Updates after every result. Swiss bracket view with live conditional probabilities.
- Markets: every discovered market, price history chart, model overlay.
- Backtest: calibration plot, log loss comparison table, hypothetical P&L curve.
- Journal: log each bet (manual entry, we don't auto-trade in v1), track closing line value. CLV is the real scorecard. If we consistently beat the close, we have an edge even on a losing week.

No auto-trading in v1. Placing orders on Polymarket needs a wallet and signed CLOB requests. Get the model right first. Add execution in v2 if the journal shows real CLV.

---

## 5. Phases

Timeline is tight. Play-in starts Oct 15. Swiss starts Oct 23. Prioritize accordingly.

### Phase 0: Scaffold (day 1)
- Repo structure above, FastAPI hello, Vite app, SQLite, docker-compose, CI running tests and lint.

### Phase 1: Data in (days 1-3)
- gol.gg scraper with disk cache. Pull 2023 to 2026 Tier 1 + international.
- GPR snapshot.
- Polymarket discovery and price polling. Start storing ticks immediately, even before the model exists. That history is valuable.

### Phase 2: Ratings (days 3-5)
- Elo baseline.
- Bradley-Terry with time decay, side term, region offsets, GPR prior.
- Unit tests on the series math (closed-form checks).

### Phase 3: Simulator (days 5-7)
- Worlds 2026 format encoded exactly. Swiss pairing logic tested against the 2024 and 2025 actual pairings.
- Monte Carlo with posterior sampling. Target under 30 seconds for 100k sims (vectorize with numpy).

### Phase 4: Backtest (days 7-9)
- Walk-forward on Worlds 2023-2025, MSI 2024-2025.
- Tune λ, international weight, region prior variance. Report log loss vs market.
- This phase decides whether we bet at all.

### Phase 5: Edge engine (days 9-10)
- Model vs market comparison, credible interval filter, structural checks, Kelly sizing.

### Phase 6: Frontend (days 7-12, parallel with 4 and 5)
- Dashboard and Simulation first. Those are what you look at during the tournament. Backtest and Journal after.

### Phase 7: Live ops (from Oct 15)
- Run it. Log bets in the Journal. Refit after each day. Watch CLV.

---

## 6. Risks and honest caveats

- Cross-region strength is mostly guesswork before international games happen. Early Swiss rounds have the widest intervals and the model will say so. Edges will tighten as results come in.
- Patch changes between the last regional split and Worlds can shift team strength. Patch is a feature we can carry but we'll have little data on the Worlds patch.
- Roster changes. gol.gg tracks teams, not rosters. If a team subs a player, the rating is stale. Manual override flag per team.
- Polymarket liquidity on non-headline markets is thin. The edge table must show depth, not just price.
- Sample size. Worlds is roughly 60 to 70 series. Even a real 3% edge can lose money over one tournament. The journal's CLV metric is the thing to judge the system on, not one tournament's P&L.
- This sandbox can't reach gol.gg, lolesports.com or Polymarket (egress policy). Scrapers must run on your machine or the environment network policy needs those hosts allowed.

---

## 7. Build status (Oct 11)

| Phase | State |
|---|---|
| 0 Scaffold | Done. Monorepo, CI, SQLite, FastAPI, Vite |
| 1 Data in | Code done. Oracle's Elixir loader, gol.gg scraper, GPR capture, Polymarket client. Not run live: the build sandbox had no access to those hosts |
| 2 Ratings | Done. Bayesian Bradley-Terry with Laplace posterior; Elo baseline |
| 3 Simulator | Done. Play-in, Swiss with 2026 draw rules, knockout seeding, conditioning on real results |
| 4 Backtest | Done. Walk-forward, log loss, Brier, calibration, trust verdict |
| 5 Edge engine | Done. Executable prices, interval filter, Kelly, overround check |
| 6 Frontend | Done. Seven pages |
| 7 Live ops | Needs real data loaded on a machine that can reach the sources |

Changes from the original plan, decided while building:

- Swiss pools and draw rules came from Riot's primer: pool 1 vs 4 and 2 vs 3 in round 1, no same-region round 1, 3-0 teams drawn against 3-2 teams in quarterfinals. Same-region avoidance in the knockout draw isn't modeled; the primer coverage didn't mention it.
- Model uncertainty for futures comes from running the tournament many times per posterior draw (40 draws by 500 sims by default). The spread of per-draw results is the interval. It includes some Monte Carlo noise, which makes the filter slightly more conservative, not less.
- Margin-of-victory term (gold diff at 15) is not built yet. It needs real data to tell whether it helps.

## 8. Open questions for you

1. Bankroll size and max per-position cap. Default in the plan is 5%.
2. Do you want auto-execution eventually, or is a journal plus manual placement fine for this tournament? Affects whether we need wallet integration.
3. Hosting. Local only, or deploy somewhere so the price poller runs 24/7 during the tournament? A cheap VPS is enough.
4. Any other data you'd trust? Oracle's Elixir publishes game-level CSVs that are cleaner than scraping gol.gg. Worth checking if they're still public for 2026.
