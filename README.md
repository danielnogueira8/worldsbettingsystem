# worldsbettingsystem

Finds mispriced Polymarket odds for the League of Legends 2026 World Championship.

It fits team strengths from pro match data, simulates the exact Worlds 2026 format tens of
thousands of times, compares the result with live Polymarket order books, and sizes bets
with fractional Kelly. It refuses to call anything a bet until a walk-forward backtest
shows the model beats both Elo and the market. The design and the math are in
[PLAN.md](PLAN.md).

## What's verified and what isn't

The code was built in a sandbox that couldn't reach gol.gg, lolesports.com or Polymarket.

| Part | State |
|---|---|
| Series math, rating model, simulator, edge/Kelly, backtest | Tested (42 tests) |
| Frontend | Built and screenshot-checked on demo data |
| Oracle's Elixir CSV loader | Written against the documented CSV format, not run on a real file |
| Polymarket client | Written against docs.polymarket.com, not run against the live API |
| gol.gg scraper | Written from memory of the site's HTML. Expect to fix selectors on first run |
| Riot GPR capture | Best effort. If it fails, enter the numbers into a CSV by hand |

Each scraper fails loudly with the URL and cached HTML path when a selector misses.

## Setup

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cd backend
uv venv && uv pip install -e '.[dev,browser]'
.venv/bin/playwright install chromium        # only for the GPR capture

cd ../frontend
npm install && npm run build                  # the API serves the built UI
```

## Try it offline first

```bash
cd backend
.venv/bin/wbs demo                            # SYNTHETIC games + markets, fit, simulate
.venv/bin/wbs backtest
.venv/bin/wbs serve                           # http://127.0.0.1:8000
.venv/bin/wbs demo --clear                    # remove all synthetic data
```

The UI shows a yellow banner whenever synthetic data is loaded.

## Real run, in order

```bash
cd backend

# 1. Match data. Oracle's Elixir is cleaner than scraping; use both if you can.
#    Download yearly CSVs from https://oracleselixir.com/tools/downloads
.venv/bin/wbs load-oracles ~/Downloads/2024_LoL_esports_match_data_from_OraclesElixir.csv \
                           ~/Downloads/2025_LoL_esports_match_data_from_OraclesElixir.csv \
                           ~/Downloads/2026_LoL_esports_match_data_from_OraclesElixir.csv
#    or scrape gol.gg (check the tournament list first)
.venv/bin/wbs scrape-golgg --season S16 --dry-run
.venv/bin/wbs scrape-golgg --season S16

# 2. Riot GPR, used as a prior on team and region strength
.venv/bin/wbs gpr-snapshot                    # or: wbs gpr-import my_gpr.csv

# 3. Fill in the two CBLOL seeds in backend/app/data/worlds2026.yaml (names and aliases)

# 4. Fit, check it, simulate
.venv/bin/wbs fit
.venv/bin/wbs backtest                        # international games only, by default
.venv/bin/wbs simulate

# 5. Markets
.venv/bin/wbs pm-discover
.venv/bin/wbs pm-poll
.venv/bin/wbs edges

# 6. Run it all on a schedule during the event
.venv/bin/wbs serve --schedule
```

`serve --schedule` polls Polymarket order books every 2 minutes, discovers new markets
hourly, pulls Worlds games from gol.gg hourly, and refits and re-simulates every 2 hours.

During the event, enter draws and results in the **Results** tab. The simulator replays
them exactly and only simulates what's left. A Swiss result changes the next round's
pairings, and that's when prices tend to lag.

## Using the output

- **Edges** lists every priced market. A row is flagged only if the pessimistic end of
  the model's 90% interval still beats the executable price after fees.
- **Structural** banners check whether a full set of YES prices sums to less than 1.
  That's an arbitrage, if the set really is exhaustive.
- **Journal** tracks closing line value. Over one tournament, P&L is mostly noise.
  Consistently beating the closing price is the signal.
- Nothing here places orders. You place bets on Polymarket yourself.

## Deploying to Vercel

`vercel.json` deploys the repo as one Vercel project with two services:

| Service | Root | Public path |
|---|---|---|
| `backend` (FastAPI) | `backend/` | `/api/*` |
| `frontend` (Vite) | `frontend/` | everything else |

Rewrites keep the request path, so `/api/teams` reaches FastAPI as `/api/teams`.
The FastAPI entrypoint is set in `backend/pyproject.toml` under `[tool.vercel]`.
Run `vercel dev` from the repo root to run both services together.

Things that behave differently on Vercel:

- **Storage.** The filesystem is read-only except `/tmp`, which is wiped between
  invocations. Without `DATABASE_URL` the backend falls back to SQLite in `/tmp`, so
  data won't persist. Attach a Postgres database and set `DATABASE_URL`.
- **Background jobs.** `serve --schedule` doesn't run on Vercel. Price polling and
  refits need an external trigger, such as Vercel Cron hitting the API, or keep the
  scheduler running on your own machine against the same database.
- **Data loading.** Load match data from your machine with the CLI, pointing
  `DATABASE_URL` at the same Postgres database the deployment uses.

## Configuration

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `WBS_BANKROLL` | 1000 | Bankroll for stake sizing |
| `WBS_KELLY_FRACTION` | 0.25 | Fraction of full Kelly |
| `WBS_MAX_POSITION` | 0.05 | Max stake as a fraction of bankroll |
| `WBS_DEFAULT_FEE` | 0 | Fee per $1, used when the market doesn't report one |
| `WBS_HALF_LIFE_DAYS` | 180 | Game weight halves every N days |
| `WBS_INTL_WEIGHT` | 1.0 | Weight multiplier for international games. 2.5 backtested worse on 2026 data |
| `WBS_N_SIMS` | 20000 | Tournaments per simulation run |
| `WBS_DB_URL` or `DATABASE_URL` | `sqlite:///data/wbs.sqlite` | Any SQLAlchemy URL. Postgres URLs are used with psycopg 3 |

## Layout

```
backend/app/
  ingest/   oracles.py golgg.py gpr.py polymarket.py
  model/    ratings.py series.py tournament.py markets.py edge.py backtest.py elo.py
  api/      FastAPI routes; also serves frontend/dist
  pipeline.py  cli.py  scheduler.py  demo.py
frontend/src/pages/  Dashboard Simulation Teams Markets Results Backtest Journal
backend/app/data/worlds2026.yaml  teams, regions, pools, aliases
```
