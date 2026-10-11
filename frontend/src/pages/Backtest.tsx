import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, pct } from "../api";
import { useAction, useLoad } from "../hooks";

export default function BacktestPage({ onChange }: { onChange: () => void }) {
  const bt = useLoad(api.backtest);
  const { busy, msg, run } = useAction();
  const [intl, setIntl] = useState(true);
  const d = bt.data;

  // Join both calibration tables on bin midpoints so they share one x axis.
  const bins = new Map<string, { x: number; model?: number; elo?: number; nModel?: number }>();
  for (const c of d?.model?.calibration ?? []) bins.set(c.bin, { x: c.pred, model: c.actual, nModel: c.n });
  for (const c of d?.elo?.calibration ?? []) {
    const e = bins.get(c.bin) ?? { x: c.pred };
    e.elo = c.actual;
    bins.set(c.bin, e);
  }
  const calib = [...bins.values()].sort((a, b) => a.x - b.x);
  const diag = [{ x: 0, ideal: 0 }, { x: 1, ideal: 1 }];

  return (
    <>
      <div className="card">
        <h2>Walk-forward backtest</h2>
        <p className="desc">
          Each game is predicted by a model fit only on earlier games. Lower log loss is better; a coin flip scores
          {" "}{d?.coin_flip_log_loss?.toFixed(3) ?? "0.693"}. The model is trusted only if it beats both Elo and market
          prices on the same games.
        </p>
        <div className="row">
          <label className="inline"><input type="checkbox" checked={intl} onChange={(e) => setIntl(e.target.checked)} /> International games only</label>
          <button className="btn primary" disabled={!!busy} onClick={() => run("Backtest", () => api.runBacktest(intl), () => { bt.reload(); onChange(); })}>
            {busy ? "Running…" : "Run backtest"}
          </button>
          {msg && <span className={`toast ${msg.ok ? "ok" : "err"}`}>{msg.text}</span>}
        </div>
      </div>
      {d?.model && d.elo ? (
        <div className="grid2">
          <div className="card">
            <h2>Scores on {d.n.toLocaleString()} held-out games</h2>
            <table>
              <thead><tr><th>Predictor</th><th className="num">Log loss</th><th className="num">Brier</th></tr></thead>
              <tbody>
                <tr><td>Rating model</td><td className="num">{d.model.log_loss.toFixed(4)}</td><td className="num">{d.model.brier.toFixed(4)}</td></tr>
                <tr><td>Elo baseline</td><td className="num">{d.elo.log_loss.toFixed(4)}</td><td className="num">{d.elo.brier.toFixed(4)}</td></tr>
                {d.market && (
                  <>
                    <tr><td>Market ({d.market.n} games)</td><td className="num">{d.market.log_loss.toFixed(4)}</td><td className="num">{d.market.brier.toFixed(4)}</td></tr>
                    <tr><td>Model, same games</td><td className="num">{d.market.model_log_loss_same_games.toFixed(4)}</td><td className="num">–</td></tr>
                  </>
                )}
              </tbody>
            </table>
            {d.verdict?.note && <p className="small muted">{d.verdict.note}</p>}
          </div>
          <div className="card">
            <h2>Calibration</h2>
            <p className="desc">Predicted vs actual win rate per bin. On the dashed line means calibrated.</p>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke="var(--border)" />
                  <XAxis dataKey="x" type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} stroke="var(--text-muted)" fontSize={11} />
                  <YAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} stroke="var(--text-muted)" fontSize={11} width={44} />
                  <Tooltip contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)" }}
                           labelFormatter={(v) => `predicted ${pct(v as number)}`} formatter={(v, n) => [pct(v as number), n as string]} />
                  <Legend />
                  <Line data={diag} dataKey="ideal" name="Perfect" stroke="var(--ref)" strokeDasharray="4 4" dot={false} isAnimationActive={false} legendType="plainline" />
                  <Line data={calib} dataKey="model" name="Rating model" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} connectNulls />
                  <Line data={calib} dataKey="elo" name="Elo" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      ) : (
        <div className="card muted">{bt.loading ? "Loading…" : d?.message ?? "No backtest yet."}</div>
      )}
    </>
  );
}
