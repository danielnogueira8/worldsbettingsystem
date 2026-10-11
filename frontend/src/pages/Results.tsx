import { useState } from "react";
import { api } from "../api";
import { useAction, useLoad } from "../hooks";

const STAGES: Record<string, string[]> = {
  play_in: ["r1a", "r1b", "uf", "lr1", "lf", "gf"],
  swiss: ["1", "2", "3", "4", "5"],
  knockout: ["qf1", "qf2", "qf3", "qf4", "sf1", "sf2", "final"],
};

export default function ResultsPage() {
  const res = useLoad(api.results);
  const teams = useLoad(api.teams);
  const { busy, msg, run } = useAction();
  const codes = (teams.data?.teams ?? []).map((t) => t.code).sort();
  const [stage, setStage] = useState("swiss");
  const [round, setRound] = useState("1");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [w, setW] = useState("");

  const submit = () => run("Save result", () => api.addResult({ stage, round, team_a: a, team_b: b, winner: w }), () => {
    res.reload();
    setA(""); setB(""); setW("");
  });

  return (
    <>
      <div className="card">
        <h2>Event results</h2>
        <p className="desc">
          Enter draws and results as they happen. The simulator replays them exactly and only simulates what's left.
          Leave the winner blank to record a drawn pairing that hasn't been played. A Swiss round is only used once every
          one of its eight pairings is entered. Knockout quarterfinals go in bracket order: qf1 and qf2 meet in sf1.
          Play-in rounds: r1a, r1b opening matches; uf upper final; lr1 lower round 1; lf lower final; gf grand final.
        </p>
        <div className="row">
          <select value={stage} onChange={(e) => { setStage(e.target.value); setRound(STAGES[e.target.value][0]); }} aria-label="Stage">
            {Object.keys(STAGES).map((s) => <option key={s} value={s}>{s.replace("_", "-")}</option>)}
          </select>
          <select value={round} onChange={(e) => setRound(e.target.value)} aria-label="Round">
            {STAGES[stage].map((r) => <option key={r}>{r}</option>)}
          </select>
          <select value={a} onChange={(e) => setA(e.target.value)} aria-label="Team A">
            <option value="">Team A</option>{codes.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Team B">
            <option value="">Team B</option>{codes.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select value={w} onChange={(e) => setW(e.target.value)} aria-label="Winner">
            <option value="">Winner: not played</option>
            {[a, b].filter(Boolean).map((c) => <option key={c}>{c}</option>)}
          </select>
          <button className="btn primary" disabled={!a || !b || a === b || !!busy} onClick={submit}>Save</button>
          <button className="btn" disabled={!!busy} onClick={() => run("Simulate", () => api.runSimulation())}>
            {busy === "Simulate" ? "Simulating…" : "Re-run simulation"}
          </button>
          {msg && <span className={`toast ${msg.ok ? "ok" : "err"}`}>{msg.text}</span>}
        </div>
      </div>
      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Stage</th><th>Round</th><th>Match</th><th>Winner</th><th></th></tr></thead>
            <tbody>
              {(res.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.stage}</td><td>{r.round}</td><td>{r.team_a} vs {r.team_b}</td>
                  <td>{r.winner || <span className="muted">not played</span>}</td>
                  <td><button className="btn" onClick={() => run("Delete", () => api.delResult(r.id), res.reload)}>Delete</button></td>
                </tr>
              ))}
              {!res.data?.length && <tr><td colSpan={5} className="muted">No results entered.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
