import { useMemo, useState } from "react";
import { api, pct, pp, ago, type EdgeRow, type Status } from "../api";
import { useAction, useLoad } from "../hooks";
import { best, sides, stake, type Side } from "../value";

const KIND_LABEL: Record<string, string> = {
  champion: "Winner", final: "Grand final", semis: "Semifinal", knockout: "Knockout",
  swiss_3_0: "Swiss 3-0", swiss_0_3: "Swiss 0-3", region_champion: "Region",
  western_champion: "Region", match: "Match",
};

export default function Dashboard({ status, onChange }: { status: Status | null; onChange: () => void }) {
  const edges = useLoad(api.edges, [], 60000);
  const { busy, msg, run } = useAction();
  const teams = useLoad(api.teams);
  const names = useMemo(
    () => Object.fromEntries((teams.data?.teams ?? []).map((t) => [t.code, t.name])),
    [teams.data],
  );
  const [onlyValue, setOnlyValue] = useState(false);
  const [kind, setKind] = useState("all");
  const after = () => { edges.reload(); onChange(); };

  const rows = useMemo(() => {
    const out: { r: EdgeRow; s: Side }[] = [];
    for (const r of edges.data?.edges ?? []) {
      if (r.kind === "unsupported") continue;
      if (kind !== "all" && KIND_LABEL[r.kind] !== kind) continue;
      const ss = sides(r, names);
      if (!ss || !ss.length) continue;
      const s = best(ss);
      if (onlyValue && s.verdict === "none") continue;
      out.push({ r, s });
    }
    return out.sort((a, b) => b.s.value - a.s.value);
  }, [edges.data, names, onlyValue, kind]);

  const trusted = status?.backtest_verdict?.trust ?? false;
  const kinds = ["all", ...Array.from(new Set(Object.values(KIND_LABEL)))];
  const nValue = rows.filter((x) => x.s.verdict === "value").length;
  const bank = status?.bankroll ?? 1000, kf = status?.kelly_fraction ?? 0.25, cap = status?.max_position ?? 0.05;

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
        <h2>Value: our chance vs the market's</h2>
        <p className="desc">
          The market's chance is the price you'd pay per $1 payout: 33¢ means the market says 33%. Value is what
          $1 returns on average if our chance is right: +20% means $1.20 back. "Cautious" redoes that at the
          pessimistic end of the model's range. Each row shows the better of the two sides of a market.
          {!trusted && " The model isn't validated against market prices yet, so treat value as a lead to check, not a bet."}
        </p>
        <div className="row" style={{ marginBottom: 10 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Market type">
            {kinds.map((k) => <option key={k} value={k}>{k === "all" ? "All markets" : k}</option>)}
          </select>
          <label className="inline"><input type="checkbox" checked={onlyValue} onChange={(e) => setOnlyValue(e.target.checked)} /> Positive value only</label>
          <span className="spacer" />
          <span className="small muted">{rows.length} markets · {nValue} with value</span>
        </div>
        {edges.error && <div className="banner critical">{edges.error}</div>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bet</th>
                <th className="num">Our chance</th>
                <th className="num">Market's chance</th>
                <th className="num">Difference</th>
                <th className="num wide-only">Fair odds</th>
                <th className="num wide-only">Market odds</th>
                <th className="num">Value</th>
                <th className="num">Cautious</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ r, s }) => (
                <tr key={r.market_id}>
                  <td className="q">
                    {s.label}
                    <div className="muted small">
                      {KIND_LABEL[r.kind]} · {s.side === "YES" ? "buy YES" : "buy NO"}
                      {r.volume != null && ` · $${Math.round(r.volume).toLocaleString()} traded`} · price {ago(r.tick_ts)}
                    </div>
                  </td>
                  <td className="num"><strong>{pct(s.ours)}</strong></td>
                  <td className="num">{pct(s.price)}</td>
                  <td className={`num ${s.diff > 0 ? "pos" : "neg"}`}>{s.diff >= 0 ? "+" : "−"}{Math.abs(s.diff * 100).toFixed(1)} pts</td>
                  <td className="num muted wide-only">{s.fairOdds < 100 ? s.fairOdds.toFixed(2) : "99+"}</td>
                  <td className="num wide-only">{s.marketOdds < 100 ? s.marketOdds.toFixed(2) : "99+"}</td>
                  <td className={`num ${s.value > 0 ? "pos" : "neg"}`}><strong>{s.value >= 0 ? "+" : "−"}{Math.abs(s.value * 100).toFixed(0)}%</strong></td>
                  <td className={`num ${s.valueLow > 0 ? "pos" : "muted"}`}>{s.valueLow >= 0 ? "+" : "−"}{Math.abs(s.valueLow * 100).toFixed(0)}%</td>
                  <td>
                    {s.verdict === "value"
                      ? <span className="pill good" title={`Quarter-Kelly stake on $${bank}`}>✓ Value · ${stake(s, bank, kf, cap).toFixed(0)}</span>
                      : s.verdict === "maybe"
                        ? <span className="pill neutral" title="Positive on our central estimate, but not at the cautious end">Maybe</span>
                        : <span className="pill neutral">No value</span>}
                  </td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={9} className="muted">
                  {edges.loading ? "Loading…" : "No priced markets with live quotes."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
