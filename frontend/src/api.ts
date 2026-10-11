export type Interval = { p: number; lo: number; hi: number };

export type Status = {
  demo: boolean;
  games: number;
  last_game: string | null;
  markets: number;
  last_price_tick: string | null;
  last_gpr: string | null;
  last_fit: string | null;
  last_simulation: string | null;
  backtest_verdict: { beats_elo: boolean; beats_market: boolean | null; trust: boolean; note: string } | null;
  bankroll: number;
  kelly_fraction: number;
  max_position: number;
  pipeline: {
    last_tick?: string;
    last_bootstrap?: string;
    steps: Record<string, { ok: boolean; at: string; ok_at?: string; result?: string; error?: string | null }>;
  };
};

export type Team = {
  code: string; name: string; region: string; pool: number | null;
  strength: number | null; sd: number | null; gpr: number | null;
};

export type TeamBlock = { p: Record<string, number>; lo: Record<string, number>; hi: Record<string, number> };

export type Simulation = {
  id: number; created_at: string; n_sims: number; n_draws: number;
  teams: Record<string, TeamBlock>;
  region_champion: Record<string, Interval>;
  western_champion: Interval;
};

export type EdgeResult = {
  side: "YES" | "NO" | null; price: number | null; model_p: number; model_lo: number; model_hi: number;
  edge: number; conservative_edge: number; kelly_f: number; stake: number; flagged: boolean; reason: string;
};

export type EdgeRow = {
  market_id: string; question: string; event: string | null; kind: string; subject: string | null;
  reason: string; volume: number | null; liquidity: number | null; slug: string | null;
  best_bid: number | null; best_ask: number | null; mid: number | null; tick_ts: string | null;
  model?: Interval; edge: EdgeResult | null;
};

export type Structural = {
  event_id: string; title: string; n: number; sum_asks: number; sum_bids: number;
  buy_all_yes_profit: number; buy_all_no_profit: number; arb: boolean;
};

export type Bet = {
  id: number; placed_at: string; market_id: string; question: string | null; side: string;
  price: number; stake: number; model_p: number | null; closing_price: number | null;
  outcome: string | null; note: string | null; clv: number | null; pnl: number | null;
};

export type EventResult = { id: number; stage: string; round: string; team_a: string; team_b: string; winner: string };

export type MatchMarket = {
  market_id: string; question: string; bo: number; yes_team: string; slug: string | null;
  best_bid: number | null; best_ask: number | null; mid: number | null;
  model: Interval & { game: number }; edge?: EdgeResult;
};
export type Match = {
  a: string; b: string; bo: number; stage: string | null; round: string | null;
  start_time: string | null; winner: string | null; names: Record<string, string>;
  model: Interval & { game: number }; markets: MatchMarket[];
};
export type SwissGrid = {
  title: string; cols: string[];
  rows: { team: string; cells: { opp: string; allowed: boolean; p: number | null }[] }[];
};
export type Matches = {
  scheduled: Match[]; played: Match[]; names: Record<string, string>; message?: string;
  swiss_r1: { draw_date: string; grids: SwissGrid[] } | null;
};

export type Calib = { bin: string; n: number; pred: number; actual: number };
export type Backtest = {
  n: number; message?: string;
  model?: { log_loss: number; brier: number; calibration: Calib[] };
  elo?: { log_loss: number; brier: number; calibration: Calib[] };
  market?: { n: number; log_loss: number; model_log_loss_same_games: number; brier: number };
  coin_flip_log_loss?: number;
  verdict?: Status["backtest_verdict"];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  status: () => req<Status>("/api/status"),
  teams: () => req<{ teams: Team[]; regions: Record<string, number>; side: number | null; n_games: number }>("/api/teams"),
  matches: () => req<Matches>("/api/matches"),
  simulation: () => req<Simulation | Record<string, never>>("/api/simulation"),
  runSimulation: (draws = 1000) => req<Simulation>("/api/simulation/run", { method: "POST", body: JSON.stringify({ draws }) }),
  fit: () => req<{ n_games: number }>("/api/fit", { method: "POST" }),
  edges: () => req<{ edges: EdgeRow[]; structural: Structural[] }>("/api/edges"),
  ticks: (id: string) => req<{ ts: string; bid: number | null; ask: number | null; mid: number | null }[]>(`/api/markets/${encodeURIComponent(id)}/ticks`),
  discover: () => req<{ upserted: number }>("/api/markets/discover", { method: "POST" }),
  poll: () => req<{ ticks: number }>("/api/markets/poll", { method: "POST" }),
  matchup: (a: string, b: string, bo: number) =>
    req<Interval & { game: number }>(`/api/matchup?a=${a}&b=${b}&bo=${bo}`),
  backtest: () => req<Backtest>("/api/backtest"),
  runBacktest: (international_only: boolean) =>
    req<Backtest>("/api/backtest/run", { method: "POST", body: JSON.stringify({ international_only }) }),
  results: () => req<EventResult[]>("/api/results"),
  addResult: (r: Omit<EventResult, "id">) => req("/api/results", { method: "POST", body: JSON.stringify(r) }),
  delResult: (id: number) => req(`/api/results/${id}`, { method: "DELETE" }),
  bets: () => req<Bet[]>("/api/bets"),
  addBet: (b: { market_id: string; side: string; price: number; stake: number; model_p?: number | null; note?: string }) =>
    req<{ id: number }>("/api/bets", { method: "POST", body: JSON.stringify(b) }),
  patchBet: (id: number, b: Partial<Pick<Bet, "closing_price" | "outcome" | "note">>) =>
    req(`/api/bets/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
};

export const pct = (x: number | null | undefined, d = 1) =>
  x == null || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(d)}%`;
export const pp = (x: number | null | undefined, d = 1) =>
  x == null ? "–" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}pp`;
export const ago = (iso: string | null) => {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};
