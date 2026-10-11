/** Model probability with its 90% interval; optional market price marker. */
export default function IntervalBar({ p, lo, hi, market, max = 1 }: {
  p: number; lo: number; hi: number; market?: number | null; max?: number;
}) {
  const x = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`;
  const title = `model ${(p * 100).toFixed(1)}% (90%: ${(lo * 100).toFixed(1)}–${(hi * 100).toFixed(1)}%)` +
    (market != null ? ` · market ${(market * 100).toFixed(1)}%` : "");
  return (
    <div className="ibar" title={title} aria-label={title} role="img">
      <div className="range" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
      <div className="pt" style={{ left: `calc(${x(p)} - 1px)` }} />
      {market != null && <div className="mk" style={{ left: `calc(${x(market)} - 1px)` }} />}
    </div>
  );
}
