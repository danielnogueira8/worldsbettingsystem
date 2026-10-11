import { useState } from "react";
import { api, pct } from "../api";
import { useLoad } from "../hooks";

export default function TeamsPage() {
  const t = useLoad(api.teams);
  const teams = t.data?.teams ?? [];
  const lo = Math.min(...teams.map((x) => (x.strength ?? 0) - 1.645 * (x.sd ?? 0)), -1);
  const hi = Math.max(...teams.map((x) => (x.strength ?? 0) + 1.645 * (x.sd ?? 0)), 1);
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;

  return (
    <div className="grid2">
      <div className="card" style={{ gridColumn: "1 / -1" }}>
        <h2>Team strength</h2>
        <p className="desc">
          Logit units per game, region offset included. A gap of 1.0 is about a 73% single-game favourite. Bars show the
          90% posterior interval. Fit on {t.data?.n_games.toLocaleString() ?? "–"} games; blue-side term{" "}
          {t.data?.side != null ? t.data.side.toFixed(3) : "–"}.
        </p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Team</th><th>Region</th><th>Pool</th><th className="num">Strength</th><th className="num">± sd</th><th style={{ minWidth: 220 }}>Interval</th><th className="num">GPR</th></tr></thead>
            <tbody>
              {teams.map((tm, i) => (
                <tr key={tm.code}>
                  <td className="muted">{i + 1}</td>
                  <td>{tm.name} <span className="muted small">{tm.code}</span></td>
                  <td>{tm.region}</td>
                  <td className="muted">{tm.pool === 0 ? "Play-In" : tm.pool ?? "–"}</td>
                  <td className="num">{tm.strength?.toFixed(2) ?? "–"}</td>
                  <td className="num muted">{tm.sd?.toFixed(2) ?? "–"}</td>
                  <td>
                    {tm.strength != null && tm.sd != null && (
                      <div className="ibar" style={{ width: 220 }} title={`${(tm.strength - 1.645 * tm.sd).toFixed(2)} to ${(tm.strength + 1.645 * tm.sd).toFixed(2)}`}>
                        <div className="range" style={{ left: x(tm.strength - 1.645 * tm.sd), width: `calc(${x(tm.strength + 1.645 * tm.sd)} - ${x(tm.strength - 1.645 * tm.sd)})` }} />
                        <div className="pt" style={{ left: `calc(${x(tm.strength)} - 1px)` }} />
                      </div>
                    )}
                  </td>
                  <td className="num muted">{tm.gpr?.toFixed(0) ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Matchup codes={teams.map((tm) => [tm.code, tm.name])} />
      <div className="card">
        <h2>Region offsets</h2>
        <p className="desc">Fit mostly from international games. The least certain part of the model.</p>
        <table>
          <tbody>
            {Object.entries(t.data?.regions ?? {}).sort((a, b) => b[1] - a[1]).map(([g, v]) => (
              <tr key={g}><td>{g}</td><td className="num">{v.toFixed(2)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Matchup({ codes }: { codes: [string, string][] }) {
  const [a, setA] = useState("GEN");
  const [b, setB] = useState("T1");
  const [bo, setBo] = useState(5);
  const m = useLoad(() => api.matchup(a, b, bo), [a, b, bo]);
  return (
    <div className="card">
      <h2>Head to head</h2>
      <p className="desc">Neutral side. Series odds assume independent games.</p>
      <div className="row">
        <select value={a} onChange={(e) => setA(e.target.value)} aria-label="Team A">
          {codes.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
        <span className="muted">vs</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Team B">
          {codes.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
        <select value={bo} onChange={(e) => setBo(Number(e.target.value))} aria-label="Series length">
          {[1, 3, 5].map((n) => <option key={n} value={n}>Bo{n}</option>)}
        </select>
      </div>
      {m.error && <p className="neg small">{m.error}</p>}
      {m.data && a !== b && (
        <table style={{ marginTop: 10 }}>
          <tbody>
            <tr><td>Single game</td><td className="num">{pct(m.data.game)}</td></tr>
            <tr><td>Bo{bo} series</td><td className="num"><strong>{pct(m.data.p)}</strong></td></tr>
            <tr><td className="muted">90% interval</td><td className="num muted">{pct(m.data.lo)} – {pct(m.data.hi)}</td></tr>
            <tr><td className="muted">Fair price (no edge)</td><td className="num muted">{(m.data.p * 100).toFixed(1)}¢</td></tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
