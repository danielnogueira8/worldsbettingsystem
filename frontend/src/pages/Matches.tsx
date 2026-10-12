import { api, pct, type Match, type MatchMarket, type SwissGrid } from "../api";
import { useLoad } from "../hooks";
import Heat from "../components/Heat";
import { best, quoteSides, type Side } from "../value";

const signed = (x: number, d = 0) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}`;

/** Both sides of one match market, labelled in plain words. */
function marketSides(m: Match, mk: MatchMarket): Side[] {
  const y = mk.yes_team, n = y === m.a ? m.b : m.a;
  const what = mk.bo > 1 ? `the Bo${mk.bo}` : (mk.question.match(/game\s*\d+/i)?.[0]?.toLowerCase() ?? "the game");
  return quoteSides(`${m.names[y]} wins ${what}`, `${m.names[n]} wins ${what}`, mk.model, mk.best_bid, mk.best_ask);
}

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
  const { scheduled, played, swiss_r1, champion, names } = d.data;

  return (
    <>
      {champion && champion.length > 0 && (
        <div className="card">
          <h2>Predicted Worlds winner</h2>
          <div className="champ">
            <span className="big">{names[champion[0].team]} · {pct(champion[0].p, 0)}</span>
            <span className="muted">
              Then {champion.slice(1).map((c) => `${names[c.team]} ${pct(c.p, 0)}`).join(", ")}.
            </span>
          </div>
          <p className="desc" style={{ marginTop: 6 }}>
            Chance of winning the whole tournament, from simulating it 20,000 times. The model's range for{" "}
            {names[champion[0].team]} is {pct(champion[0].lo, 0)}–{pct(champion[0].hi, 0)}: still very uncertain.
          </p>
        </div>
      )}

      <div className="card">
        <h2>Upcoming matches</h2>
        <p className="desc">
          Only matches whose draw is known. Blue and orange show the model's split between the two teams;
          the black tick is where the betting market puts it. The table compares our chance with the price for every side on offer: value is the expected return per dollar if our chance is right.
        </p>
        <div className="match-list">
          {scheduled.map((m) => <MatchCard key={`${m.a}-${m.b}`} m={m} />)}
          {!scheduled.length && <p className="muted">No draws known yet.</p>}
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
            {swiss_r1.grids.map((g) => <Grid key={g.title} g={g} names={names} />)}
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

function MatchCard({ m }: { m: Match }) {
  const A = m.names[m.a], B = m.names[m.b];
  const pa = m.model.p;
  const fav = pa >= 0.5 ? A : B;
  const favP = pa >= 0.5 ? pa : 1 - pa;
  const top = m.model.scores[0];
  const topWinner = top.a > top.b ? A : B;
  const topScore = top.a > top.b ? `${top.a}-${top.b}` : `${top.b}-${top.a}`;

  const series = m.markets.find((mk) => mk.bo === m.bo) ?? m.markets.find((mk) => mk.bo > 1);
  const mktA = series?.mid == null ? null : series.yes_team === m.a ? series.mid : 1 - series.mid;
  // Series market first, then single games in question order.
  const ordered = [...m.markets].sort((x, y) => (y.bo - x.bo) || x.question.localeCompare(y.question));
  const rows = ordered.flatMap((mk) => marketSides(m, mk));

  let value: { text: string; good: boolean };
  if (!m.markets.length) value = { text: "No betting market for this match yet.", good: false };
  else if (!rows.length) value = { text: "Market has no live prices yet.", good: false };
  else {
    const t = best(rows);
    const vs = `our ${pct(t.ours, 0)} vs the market's ${pct(t.price, 0)}`;
    value = t.verdict === "value"
      ? { text: `Bet: ${t.label} at ${Math.round(t.price * 100)}¢. That's ${vs}, ${signed(t.value)}% value, and still positive in the model's cautious case.`, good: true }
      : t.verdict === "maybe"
        ? { text: `Closest to value: ${t.label}, ${vs} (${signed(t.value)}% value). Within the model's uncertainty, so no bet.`, good: false }
        : { text: "The market prices every side at or above our chances. No bet.", good: false };
  }

  return (
    <div className="match">
      <div className="meta">
        {STAGE[m.stage ?? ""] ?? "Match"} · Bo{m.bo} · {when(m)}
        {m.round?.includes("derived") && " · draw implied by the other play-in opener"}
      </div>
      <div className="title">{A} <span className="muted">vs</span> {B}</div>
      <p className="verdict">{fav} to win <span className="p">{pct(favP, 0)}</span></p>
      <p className="sub">
        {m.bo > 1 ? <>Most likely score: {topWinner} {topScore} ({pct(top.p, 0)}). </> : null}
        Each game: {A} {pct(m.model.game, 0)}. Model range for {A}: {pct(m.model.lo, 0)}–{pct(m.model.hi, 0)}.
      </p>
      <div className="split" role="img" aria-label={`Model: ${A} ${pct(pa, 0)}, ${B} ${pct(1 - pa, 0)}`}>
        <div className="a" style={{ width: `${pa * 100}%` }}>{pa >= 0.3 ? `${A} ${pct(pa, 0)}` : ""}</div>
        <div className="b" style={{ width: `${(1 - pa) * 100}%` }}>{pa <= 0.7 ? `${pct(1 - pa, 0)} ${B}` : ""}</div>
        {mktA != null && <div className="mk" style={{ left: `calc(${mktA * 100}% - 1px)` }} />}
      </div>
      <div className="split-legend">
        <span>Model: {A} {pct(pa, 0)} · {B} {pct(1 - pa, 0)}</span>
        <span>{mktA != null ? `Market: ${A} ${pct(mktA, 0)} · ${B} ${pct(1 - mktA, 0)}` : "No market price"}</span>
      </div>
      <div className={`value ${value.good ? "good" : ""}`}>{value.text}</div>
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="mini">
            <thead>
              <tr>
                <th>Bet</th>
                <th className="num">Our chance</th>
                <th className="num">Market's</th>
                <th className="num wide-only">Difference</th>
                <th className="num">Value</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="num"><strong>{pct(r.ours, 0)}</strong></td>
                  <td className="num">{pct(r.price, 0)}</td>
                  <td className={`num wide-only ${r.diff > 0 ? "pos" : "neg"}`}>{signed(r.diff, 1)} pts</td>
                  <td className={`num ${r.value > 0 ? "pos" : "neg"}`}><strong>{signed(r.value)}%</strong></td>
                  <td>
                    {r.verdict === "value" ? <span className="pill good">✓ Value</span>
                      : r.verdict === "maybe" ? <span className="pill neutral" title="Positive on our central estimate, not in the cautious case">Maybe</span>
                      : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
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
