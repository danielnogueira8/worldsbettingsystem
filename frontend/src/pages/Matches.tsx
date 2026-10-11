import { api, pct, pp, type Match, type SwissGrid } from "../api";
import { useLoad } from "../hooks";
import IntervalBar from "../components/IntervalBar";
import Heat from "../components/Heat";

const STAGE: Record<string, string> = { play_in: "Play-In", swiss: "Swiss", knockout: "Knockout" };

function when(m: Match) {
  if (m.start_time) {
    return new Date(m.start_time).toLocaleString(undefined, {
      weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }
  return "Time TBC";
}

export default function MatchesPage() {
  const d = useLoad(api.matches, [], 60000);
  if (d.error) return <div className="banner critical">{d.error}</div>;
  if (!d.data) return <div className="card muted">Loading…</div>;
  const { scheduled, played, swiss_r1 } = d.data;

  return (
    <>
      <div className="card">
        <h2>Upcoming matches</h2>
        <p className="desc">
          Known draws only: Polymarket's series markets, pairings you enter in Results, and the play-in's
          second opener once the first is known. Model odds are for the team listed first, with the 90%
          interval. Market prices are that team's YES price.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th><th>Stage</th><th>Match</th><th className="num">Bo</th>
                <th>Model · interval · <span style={{ color: "var(--series-2)" }}>▮</span> market</th>
                <th className="num">Series</th><th className="num">Per game</th>
                <th className="num">Market</th><th>Edge</th>
              </tr>
            </thead>
            <tbody>
              {scheduled.map((m) => <MatchRow key={`${m.a}-${m.b}`} m={m} />)}
              {!scheduled.length && (
                <tr><td colSpan={9} className="muted">No draws known yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {swiss_r1 && (
        <div className="card">
          <h2>Swiss round 1: possible matchups</h2>
          <p className="desc">
            The draw is on {new Date(swiss_r1.draw_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}.
            Pool 1 meets pool 4 and pool 2 meets pool 3, never two teams from the same region. Each cell is the
            row team's chance to win a Bo1. Dashes are pairings the rules forbid; the play-in winner is still unknown.
          </p>
          <div className="grid2">
            {swiss_r1.grids.map((g) => <Grid key={g.title} g={g} names={d.data!.names} />)}
          </div>
        </div>
      )}

      <div className="card">
        <h2>Played</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Stage</th><th>Match</th><th>Winner</th><th className="num">Model gave the winner</th></tr></thead>
            <tbody>
              {played.map((m) => {
                const pw = m.winner === m.a ? m.model.p : 1 - m.model.p;
                return (
                  <tr key={`${m.a}-${m.b}`}>
                    <td>{STAGE[m.stage ?? ""] ?? "–"} {m.round ? <span className="muted small">{m.round}</span> : null}</td>
                    <td>{m.names[m.a]} vs {m.names[m.b]}</td>
                    <td><strong>{m.names[m.winner!] ?? m.winner}</strong></td>
                    <td className="num">{pct(pw)}</td>
                  </tr>
                );
              })}
              {!played.length && <tr><td colSpan={4} className="muted">No results entered yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function MatchRow({ m }: { m: Match }) {
  const series = m.markets.find((mk) => mk.bo === m.bo) ?? m.markets.find((mk) => mk.bo > 1);
  const mid = series ? (series.yes_team === m.a ? series.mid : series.mid == null ? null : 1 - series.mid) : null;
  const e = series?.edge;
  const games = m.markets.filter((mk) => mk.bo === 1);
  return (
    <tr>
      <td className="small">{when(m)}</td>
      <td className="small">{STAGE[m.stage ?? ""] ?? "–"}{m.round ? <div className="muted">{m.round}</div> : null}</td>
      <td>
        <strong>{m.names[m.a]}</strong> <span className="muted">vs</span> {m.names[m.b]}
        {games.length > 0 && <div className="muted small">+{games.length} single-game market{games.length > 1 ? "s" : ""} on Edges</div>}
      </td>
      <td className="num">{m.bo}</td>
      <td><IntervalBar {...m.model} market={mid} /></td>
      <td className="num"><strong>{pct(m.model.p)}</strong></td>
      <td className="num muted">{pct(m.model.game)}</td>
      <td className="num">{pct(mid)}</td>
      <td>
        {e && e.side ? (() => {
          const other = series!.yes_team === m.a ? m.b : m.a;
          const backed = m.names[e.side === "YES" ? series!.yes_team : other];
          return e.flagged
            ? <span className="pill good">✓ Back {backed} {pp(e.edge)}</span>
            : <span className="pill neutral" title={e.reason}>{backed} {pp(e.edge)}</span>;
        })() : <span className="muted small">{series ? "no quote" : "no market"}</span>}
      </td>
    </tr>
  );
}

function Grid({ g, names }: { g: SwissGrid; names: Record<string, string> }) {
  return (
    <div>
      <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>{g.title}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              {g.cols.map((c) => <th key={c} className="num">{c === "PLAYIN_WINNER" ? "Play-in" : c}</th>)}
            </tr>
          </thead>
          <tbody>
            {g.rows.map((r) => (
              <tr key={r.team}>
                <td title={names[r.team]}>{r.team}</td>
                {r.cells.map((c) => c.allowed && c.p != null
                  ? <Heat key={c.opp} v={c.p} linear />
                  : <td key={c.opp} className="num muted">–</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
