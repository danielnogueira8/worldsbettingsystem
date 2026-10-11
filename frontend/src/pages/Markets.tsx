import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, pct } from "../api";
import { useLoad } from "../hooks";

export default function MarketsPage() {
  const edges = useLoad(api.edges);
  const markets = useMemo(() => (edges.data?.edges ?? []).filter((e) => e.kind !== "unsupported"), [edges.data]);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    if (!sel && markets.length) setSel(markets[0].market_id);
  }, [markets, sel]);
  const m = markets.find((x) => x.market_id === sel);
  const ticks = useLoad(() => (sel ? api.ticks(sel) : Promise.resolve([])), [sel]);
  const data = (ticks.data ?? []).map((t) => ({
    t: new Date(t.ts).getTime(), mid: t.mid, bid: t.bid, ask: t.ask,
  }));

  return (
    <div className="card">
      <h2>Price history</h2>
      <p className="desc">Market midpoint over time against the model's current probability and its 90% interval (shaded).</p>
      <div className="row" style={{ marginBottom: 10 }}>
        <select value={sel ?? ""} onChange={(e) => setSel(e.target.value)} aria-label="Market" style={{ maxWidth: "100%" }}>
          {markets.map((x) => <option key={x.market_id} value={x.market_id}>{x.question}</option>)}
        </select>
        {m?.model && <span className="small muted">model {pct(m.model.p)} · mid {pct(m.mid)}</span>}
      </div>
      {!data.length ? (
        <p className="muted">{ticks.loading ? "Loading…" : "No price ticks stored for this market yet."}</p>
      ) : (
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time"
                     tickFormatter={(t) => new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })}
                     stroke="var(--text-muted)" fontSize={11} tickLine={false} />
              <YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} stroke="var(--text-muted)" fontSize={11}
                     tickLine={false} axisLine={false} width={44}
                     domain={[0, (dataMax: number) => Math.min(1, Math.max(dataMax, m?.model?.hi ?? 0) * 1.15)]} />
              {m?.model && <ReferenceArea y1={m.model.lo} y2={m.model.hi} fill="var(--series-2)" fillOpacity={0.12} />}
              <Tooltip
                contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)" }}
                labelFormatter={(t) => new Date(t as number).toLocaleString()}
                formatter={(v, n) => [pct(v as number), n as string]} />
              <Legend />
              <Line type="monotone" dataKey="mid" name="Market mid" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
              {m?.model && <ReferenceLine y={m.model.p} stroke="var(--series-2)" strokeWidth={2} strokeDasharray="6 4"
                                           label={{ value: `model ${pct(m.model.p)}`, position: "insideTopRight", fill: "var(--text-secondary)", fontSize: 11 }} />}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
