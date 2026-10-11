const STEPS = 8;

/** Sequential single-hue cell. Text stays in text tokens; color only fills. */
/** `linear` suits even-money quantities like match odds; the default square-root scale
 *  spreads out the small probabilities typical of tournament outcomes. */
export default function Heat({ v, lo, hi, linear = false }: { v: number; lo?: number; hi?: number; linear?: boolean }) {
  const t = linear ? v : Math.sqrt(v);
  const step = v <= 0 ? 0 : Math.min(STEPS - 1, 1 + Math.floor(t * (STEPS - 1)));
  const title = lo != null && hi != null
    ? `${(v * 100).toFixed(1)}% (90%: ${(lo * 100).toFixed(1)}–${(hi * 100).toFixed(1)}%)`
    : `${(v * 100).toFixed(1)}%`;
  return (
    <td className="heat" title={title}
        style={{ background: `var(--seq-${step})`, color: `var(--seq-ink-${step})` }}>
      {v < 0.0005 ? "–" : v >= 0.9995 ? "100%" : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`}
    </td>
  );
}
