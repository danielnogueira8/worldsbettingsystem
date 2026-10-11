import { useState } from "react";
import { api, pct, pp } from "../api";
import { useAction, useLoad } from "../hooks";

export default function JournalPage() {
  const bets = useLoad(api.bets);
  const edges = useLoad(api.edges);
  const { busy, msg, run } = useAction();
  const markets = (edges.data?.edges ?? []).filter((e) => e.kind !== "unsupported");
  const [mid, setMid] = useState("");
  const [side, setSide] = useState("YES");
  const [price, setPrice] = useState("");
  const [stake, setStake] = useState("");
  const sel = markets.find((m) => m.market_id === mid);

  const prefill = (id: string) => {
    setMid(id);
    const m = markets.find((x) => x.market_id === id);
    if (m?.edge?.side) {
      setSide(m.edge.side);
      setPrice(m.edge.price?.toFixed(3) ?? "");
      setStake(m.edge.stake ? m.edge.stake.toFixed(0) : "");
    }
  };

  const rows = bets.data ?? [];
  const settled = rows.filter((b) => b.pnl != null);
  const withClv = rows.filter((b) => b.clv != null);
  const pnl = settled.reduce((s, b) => s + (b.pnl ?? 0), 0);
  const staked = settled.reduce((s, b) => s + b.stake, 0);
  const avgClv = withClv.length ? withClv.reduce((s, b) => s + (b.clv ?? 0), 0) / withClv.length : null;

  return (
    <>
      <div className="stats">
        <div className="stat"><div className="k">Bets</div><div className="v">{rows.length}</div></div>
        <div className="stat"><div className="k">Settled P&amp;L</div><div className={`v ${pnl >= 0 ? "pos" : "neg"}`}>${pnl.toFixed(2)}</div></div>
        <div className="stat"><div className="k">ROI</div><div className="v">{staked ? pct(pnl / staked) : "–"}</div></div>
        <div className="stat"><div className="k">Avg closing line value</div><div className={`v ${(avgClv ?? 0) >= 0 ? "pos" : "neg"}`}>{pp(avgClv)}</div></div>
      </div>
      <div className="card">
        <h2>Log a bet</h2>
        <p className="desc">
          Closing line value is the scorecard that matters over one tournament. P&amp;L over ~60 series is mostly noise;
          consistently beating the closing price is not.
        </p>
        <div className="row">
          <select value={mid} onChange={(e) => prefill(e.target.value)} aria-label="Market" style={{ maxWidth: 360 }}>
            <option value="">Choose market…</option>
            {markets.map((m) => <option key={m.market_id} value={m.market_id}>{m.question}</option>)}
          </select>
          <select value={side} onChange={(e) => setSide(e.target.value)} aria-label="Side"><option>YES</option><option>NO</option></select>
          <label className="inline">Price <input type="number" step="0.001" min="0" max="1" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <label className="inline">Stake $ <input type="number" min="0" value={stake} onChange={(e) => setStake(e.target.value)} /></label>
          <button className="btn primary" disabled={!mid || !price || !stake || !!busy}
                  onClick={() => run("Log bet", () => api.addBet({ market_id: mid, side, price: Number(price), stake: Number(stake),
                    model_p: sel?.model ? (side === "YES" ? sel.model.p : 1 - sel.model.p) : null }), bets.reload)}>
            Log bet
          </button>
          {msg && <span className={`toast ${msg.ok ? "ok" : "err"}`}>{msg.text}</span>}
        </div>
      </div>
      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Placed</th><th>Market</th><th>Side</th><th className="num">Price</th><th className="num">Stake</th><th className="num">Model</th><th>Closing (YES)</th><th className="num">CLV</th><th>Outcome</th><th className="num">P&amp;L</th></tr></thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td className="small muted">{new Date(b.placed_at).toLocaleString()}</td>
                  <td className="q">{b.question ?? b.market_id}</td>
                  <td>{b.side}</td>
                  <td className="num">{b.price.toFixed(3)}</td>
                  <td className="num">${b.stake.toFixed(0)}</td>
                  <td className="num">{pct(b.model_p)}</td>
                  <td>
                    <input type="number" step="0.001" defaultValue={b.closing_price ?? ""} aria-label="Closing YES price"
                           onBlur={(e) => e.target.value && run("Update", () => api.patchBet(b.id, { closing_price: Number(e.target.value) }), bets.reload)} />
                  </td>
                  <td className={`num ${(b.clv ?? 0) >= 0 ? "pos" : "neg"}`}>{pp(b.clv)}</td>
                  <td>
                    <select value={b.outcome ?? ""} aria-label="Outcome"
                            onChange={(e) => run("Update", () => api.patchBet(b.id, { outcome: e.target.value || null }), bets.reload)}>
                      <option value="">open</option><option>WON</option><option>LOST</option><option>VOID</option>
                    </select>
                  </td>
                  <td className={`num ${(b.pnl ?? 0) >= 0 ? "pos" : "neg"}`}>{b.pnl == null ? "–" : `$${b.pnl.toFixed(2)}`}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={10} className="muted">No bets logged.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
