import { useMemo, useState } from "react";
import { api, pct, type Simulation } from "../api";
import { useLoad } from "../hooks";
import Heat from "../components/Heat";

const COLS: [string, string][] = [
  ["swiss", "Swiss"], ["3-0", "3-0"], ["knockout", "Knockout"], ["semis", "Semis"],
  ["final", "Final"], ["champion", "Champion"], ["0-3", "0-3"],
];

export default function SimulationPage() {
  const sim = useLoad(api.simulation);
  const teams = useLoad(api.teams);
  const [sortKey, setSortKey] = useState("champion");
  const s = sim.data && "teams" in sim.data ? (sim.data as Simulation) : null;
  const names = Object.fromEntries((teams.data?.teams ?? []).map((t) => [t.code, t]));

  const order = useMemo(() => {
    if (!s) return [];
    return Object.keys(s.teams.champion.p).sort((a, b) => s.teams[sortKey].p[b] - s.teams[sortKey].p[a]);
  }, [s, sortKey]);

  if (!s) return <div className="card muted">{sim.loading ? "Loading…" : "No simulation yet. Re-run it from the Edges tab."}</div>;

  return (
    <>
      <div className="card">
        <h2>Tournament outcome probabilities</h2>
        <p className="desc">
          {s.n_sims.toLocaleString()} simulated tournaments over {s.n_draws} draws from the rating posterior. Conditioned
          on every result entered in the Results tab. Hover a cell for its 90% interval across posterior draws. Click a
          column to sort.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Team</th><th>Region</th>
                {COLS.map(([k, l]) => (
                  <th key={k} className="num" style={{ cursor: "pointer" }} onClick={() => setSortKey(k)}
                      aria-sort={sortKey === k ? "descending" : undefined}>
                    {l}{sortKey === k ? " ↓" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {order.map((c) => (
                <tr key={c}>
                  <td>{names[c]?.name ?? c}</td>
                  <td className="muted small">{names[c]?.region}</td>
                  {COLS.map(([k]) => (
                    <Heat key={k} v={s.teams[k].p[c]} lo={s.teams[k].lo[c]} hi={s.teams[k].hi[c]} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Winning region</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Region</th><th className="num">P(win)</th><th className="num">90% interval</th></tr></thead>
            <tbody>
              {Object.entries(s.region_champion).sort((a, b) => b[1].p - a[1].p).map(([g, v]) => (
                <tr key={g}><td>{g}</td><td className="num">{pct(v.p)}</td><td className="num muted">{pct(v.lo)} – {pct(v.hi)}</td></tr>
              ))}
              <tr><td>Any Western team</td><td className="num">{pct(s.western_champion.p)}</td>
                <td className="num muted">{pct(s.western_champion.lo)} – {pct(s.western_champion.hi)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
