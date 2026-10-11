import { useMemo, useState } from "react";
import { api, pct, pp, ago, type EdgeRow, type Status } from "../api";
import { useAction, useLoad } from "../hooks";
import IntervalBar from "../components/IntervalBar";

const KIND_LABEL: Record<string, string> = {
  champion: "Win Worlds", final: "Reach final", semis: "Reach semis", knockout: "Reach knockout",
  swiss_3_0: "Swiss 3-0", swiss_0_3: "Swiss 0-3", region_champion: "Winning region",
  western_champion: "Western winner", match: "Match",
};

export default function Dashboard({ status, onChange }: { status: Status | null; onChange: () => void }) {
  const edges = useLoad(api.edges, [], 60000);
  const { busy, msg, run } = useAction();
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [showUnsupported, setShowUnsupported] = useState(false);
  const after = () => { edges.reload(); onChange(); };

  const rows = useMemo(() => {
    let r = edges.data?.edges ?? [];
    if (!showUnsupported) r = r.filter((e) => e.kind !== "unsupported");
    if (onlyFlagged) r = r.filter((e) => e.edge?.flagged);
    return r;
  }, [edges.data, onlyFlagged, showUnsupported]);

  const trusted = status?.backtest_verdict?.trust ?? false;
  const nUnsupported = (edges.data?.edges ?? []).filter((e) => e.kind === "unsupported").length;

  return (
    <>
      <div className="card">
        <div className="row">
          <button className="btn" disabled={!!busy} onClick={() => run("Discover markets", api.discover, after)}>Discover markets</button>
          <button className="btn" disabled={!!busy} onClick={() => run("Poll prices", api.poll, after)}>Poll prices</button>
          <button className="btn" disabled={!!busy} onClick={() => run("Refit ratings", api.fit, after)}>Refit ratings</button>
          <button className="btn primary" disabled={!!busy} onClick={() => run("Simulate", () => api.runSimulation(), after)}>
            {busy === "Simulate" ? "Simulating…" : "Re-run simulation"}
          </button>
          {busy && <span className="muted small">{busy}…</span>}
          {msg && <span className={`toast ${msg.ok ? "ok" : "err"}`}>{msg.text}</span>}
        </div>
      </div>

      {(edges.data?.structural ?? []).map((s) => (
        <div key={s.event_id} className={`banner ${s.arb ? "good" : "warning"}`}>
          <strong>{s.title}</strong>
          <span>
            {s.n} outcomes · YES asks sum to {pct(s.sum_asks)} · YES bids sum to {pct(s.sum_bids)}.{" "}
            {s.arb
              ? s.buy_all_yes_profit > 0
                ? `Buying every YES locks in ${pct(s.buy_all_yes_profit)} per $1 before fees. Check that the set is exhaustive.`
                : `Buying every NO locks in ${pct(s.buy_all_no_profit)} per $1 before fees. Check that the set is exhaustive.`
              : `No structural arb. Overround ${pp(s.sum_asks - 1)}.`}
          </span>
        </div>
      ))}

      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <div>
            <h2>Edges</h2>
            <p className="desc">
              Executable prices only: buy YES at the ask, buy NO at one minus the bid. A row is flagged only if the
              pessimistic end of the model's 90% interval still beats the price.
              {!trusted && " Stakes shown are what Kelly would say. Don't bet them until the backtest passes."}
            </p>
          </div>
          <span className="spacer" />
          <label className="inline"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} /> Flagged only</label>
          <label className="inline"><input type="checkbox" checked={showUnsupported} onChange={(e) => setShowUnsupported(e.target.checked)} /> Show unpriced ({nUnsupported})</label>
        </div>
        {edges.error && <div className="banner critical">{edges.error}</div>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Market</th><th>Type</th>
                <th>Model · interval · <span style={{ color: "var(--series-2)" }}>▮</span> market</th>
                <th className="num">Model</th><th className="num">Bid</th><th className="num">Ask</th>
                <th>Side</th><th className="num">Edge</th><th className="num">Worst case</th>
                <th className="num">Stake</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => <EdgeRowView key={r.market_id} r={r} />)}
              {!rows.length && (
                <tr><td colSpan={11} className="muted">
                  {edges.loading ? "Loading…" : "No markets yet. Discover markets, then poll prices."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function EdgeRowView({ r }: { r: EdgeRow }) {
  const e = r.edge;
  const max = r.model ? Math.min(1, Math.max(0.1, r.model.hi * 1.15, (r.best_ask ?? 0) * 1.15)) : 1;
  return (
    <tr>
      <td className="q">
        {r.slug && r.slug !== "demo"
          ? <a href={`https://polymarket.com/event/${r.slug}`} target="_blank" rel="noreferrer">{r.question}</a>
          : r.question}
        <div className="muted small">
          {r.volume != null && `$${Math.round(r.volume).toLocaleString()} vol · `}price {ago(r.tick_ts)}
        </div>
      </td>
      <td className="small">{KIND_LABEL[r.kind] ?? <span className="muted" title={r.reason}>unpriced</span>}</td>
      <td>{r.model ? <IntervalBar {...r.model} market={r.mid} max={max} /> : <span className="muted small">{r.reason}</span>}</td>
      <td className="num">{r.model ? pct(r.model.p) : "–"}</td>
      <td className="num">{pct(r.best_bid)}</td>
      <td className="num">{pct(r.best_ask)}</td>
      <td>{e?.side ?? "–"}</td>
      <td className={`num ${e && e.edge > 0 ? "pos" : ""}`}>{e ? pp(e.edge) : "–"}</td>
      <td className={`num ${e ? (e.conservative_edge > 0 ? "pos" : "neg") : ""}`}>{e ? pp(e.conservative_edge) : "–"}</td>
      <td className="num">{e && e.stake > 0 ? `$${e.stake.toFixed(0)}` : "–"}</td>
      <td>
        {e?.flagged
          ? <span className="pill good">✓ Bet</span>
          : <span className="pill neutral" title={e?.reason}>{e ? "Pass" : "No quote"}</span>}
      </td>
    </tr>
  );
}
