import { useEffect, useState } from "react";
import { api, ago, type Status } from "./api";
import { useLoad } from "./hooks";
import Dashboard from "./pages/Dashboard";
import SimulationPage from "./pages/Simulation";
import MatchesPage from "./pages/Matches";
import TeamsPage from "./pages/Teams";
import MarketsPage from "./pages/Markets";
import ResultsPage from "./pages/Results";
import BacktestPage from "./pages/Backtest";
import JournalPage from "./pages/Journal";

const TABS = [
  ["edges", "Value"],
  ["matches", "Matches"],
  ["sim", "Simulation"],
  ["teams", "Teams"],
  ["markets", "Markets"],
  ["results", "Results"],
  ["backtest", "Backtest"],
  ["journal", "Journal"],
] as const;
type Tab = (typeof TABS)[number][0];

function initialTab(): Tab {
  const h = window.location.hash.slice(1);
  return (TABS.find(([k]) => k === h)?.[0] ?? "edges") as Tab;
}

export default function App() {
  const [tab, setTab] = useState<Tab>(initialTab);
  const status = useLoad(api.status, [], 30000);
  useEffect(() => {
    window.location.hash = tab;
  }, [tab]);

  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1>Worlds Edge</h1>
          <div className="sub">LoL Worlds 2026 · model vs Polymarket</div>
        </div>
        <nav className="tabs" aria-label="Sections">
          {TABS.map(([k, label]) => (
            <button key={k} aria-current={tab === k ? "page" : undefined} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </nav>
      </header>
      <Banners s={status.data} error={status.error} />
      {tab === "edges" && <Dashboard status={status.data} onChange={status.reload} />}
      {tab === "matches" && <MatchesPage />}
      {tab === "sim" && <SimulationPage />}
      {tab === "teams" && <TeamsPage />}
      {tab === "markets" && <MarketsPage />}
      {tab === "results" && <ResultsPage />}
      {tab === "backtest" && <BacktestPage onChange={status.reload} />}
      {tab === "journal" && <JournalPage />}
    </div>
  );
}

function Banners({ s, error }: { s: Status | null; error: string | null }) {
  if (error) return <div className="banner critical" role="alert"><strong>API unreachable.</strong> {error}</div>;
  if (!s) return null;
  const v = s.backtest_verdict;
  return (
    <>
      {s.demo && (
        <div className="banner warning" role="alert">
          <strong>Demo data.</strong> Synthetic games and markets are loaded. Nothing on screen is real. Run
          <code> wbs demo --clear</code> before using real data.
        </div>
      )}
      {!v ? (
        <div className="banner critical">
          <strong>Model not validated.</strong> No backtest has been run. Treat every edge as unproven and stake nothing.
        </div>
      ) : !v.trust ? (
        <div className="banner critical">
          <strong>Model not trusted.</strong>{" "}
          {v.beats_elo ? "Beats Elo" : "Does not beat Elo"}
          {v.beats_market == null ? ", untested against market prices." : v.beats_market ? ", beats the market." : ", loses to the market."}{" "}
          Edges are informational only.
        </div>
      ) : (
        <div className="banner good"><strong>Model validated.</strong> Beats Elo and the market on held-out games.</div>
      )}
      {Object.entries(s.pipeline?.steps ?? {}).filter(([, v]) => !v.ok).map(([k, v]) => (
        <div key={k} className="banner warning">
          <strong>Pipeline step failing: {k.replace(/_/g, " ")}.</strong>
          {v.error} <span className="small">Last success {ago(v.ok_at ?? null)}.</span>
        </div>
      ))}
      <div className="stats">
        <Stat k="Games" v={s.games.toLocaleString()} />
        <Stat k="Latest game" v={ago(s.last_game)} />
        <Stat k="Markets" v={String(s.markets)} />
        <Stat k="Last price" v={ago(s.last_price_tick)} />
        <Stat k="Last fit" v={ago(s.last_fit)} />
        <Stat k="Last sim" v={ago(s.last_simulation)} />
        <Stat k="Pipeline run" v={ago(s.pipeline?.last_tick ?? s.pipeline?.last_bootstrap ?? null)} />
        <Stat k="Bankroll" v={`$${s.bankroll.toLocaleString()} · ${s.kelly_fraction}× Kelly`} />
      </div>
    </>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}
