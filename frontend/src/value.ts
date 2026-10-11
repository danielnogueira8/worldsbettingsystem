import type { EdgeRow } from "./api";

/** One side of a market, priced at what you'd actually pay to take it. */
export type Side = {
  side: "YES" | "NO";
  label: string;        // plain words: "Gen.G wins Worlds" / "Gen.G does not win Worlds"
  ours: number;         // model probability this side happens
  oursLow: number;      // pessimistic end of the model's 90% range
  price: number;        // cost per $1 payout = market's implied probability
  diff: number;         // ours - price, in probability points
  value: number;        // expected return per $1 staked: ours / price - 1
  valueLow: number;     // same, at the pessimistic end
  fairOdds: number;     // decimal odds the model thinks are fair: 1 / ours
  marketOdds: number;   // decimal odds on offer: 1 / price
  verdict: "value" | "maybe" | "none";
};

const REGION: Record<string, string> = {
  LCK: "an LCK (Korea)", LPL: "an LPL (China)", LEC: "an LEC (Europe)", LCS: "an LCS (North America)",
  CBLOL: "a CBLOL (Brazil)", LCP: "an LCP (Pacific)",
};

export function describe(r: EdgeRow, names: Record<string, string>): [string, string] {
  const n = (c: string | null) => (c ? names[c] ?? c : "?");
  switch (r.kind) {
    case "champion": return [`${n(r.subject)} wins Worlds`, `${n(r.subject)} does not win Worlds`];
    case "final": return [`${n(r.subject)} reaches the grand final`, `${n(r.subject)} misses the final`];
    case "semis": return [`${n(r.subject)} reaches the semifinals`, `${n(r.subject)} misses the semifinals`];
    case "knockout": return [`${n(r.subject)} reaches the knockout stage`, `${n(r.subject)} goes out in Swiss`];
    case "swiss_3_0": return [`${n(r.subject)} goes 3-0 in Swiss`, `${n(r.subject)} drops a Swiss game`];
    case "swiss_0_3": return [`${n(r.subject)} goes 0-3 in Swiss`, `${n(r.subject)} wins a Swiss game`];
    case "region_champion":
      return [`${REGION[r.subject ?? ""] ?? r.subject} team wins Worlds`, `${REGION[r.subject ?? ""] ?? r.subject} team does not win`];
    case "western_champion": return ["A Western team wins Worlds", "No Western team wins Worlds"];
    case "match": {
      const [a, b, bo] = (r.subject ?? "").split("|");
      const what = bo === "1" ? (r.question.match(/game\s*\d+/i)?.[0]?.toLowerCase() ?? "the game") : `the Bo${bo}`;
      return [`${n(a)} beats ${n(b)} in ${what}`, `${n(b)} beats ${n(a)} in ${what}`];
    }
    default: return [r.question, `Not: ${r.question}`];
  }
}

/** Minimum expected return before we call something value, to cover noise and slippage. */
export const MIN_VALUE = 0.05;

function side(s: "YES" | "NO", label: string, ours: number, oursLow: number, price: number): Side {
  const value = ours / price - 1;
  const valueLow = oursLow / price - 1;
  const verdict = value >= MIN_VALUE && valueLow > 0 ? "value" : value > 0 ? "maybe" : "none";
  return { side: s, label, ours, oursLow, price, diff: ours - price, value, valueLow,
           fairOdds: 1 / ours, marketOdds: 1 / price, verdict };
}

/** Both sides of a market with a model price and a live quote; null if either is missing. */
export function sides(r: EdgeRow, names: Record<string, string>): Side[] | null {
  if (!r.model) return null;
  const [yesLabel, noLabel] = describe(r, names);
  const out: Side[] = [];
  const { p, lo, hi } = r.model;
  if (r.best_ask != null && r.best_ask > 0 && r.best_ask < 1) out.push(side("YES", yesLabel, p, lo, r.best_ask));
  if (r.best_bid != null && r.best_bid > 0 && r.best_bid < 1) out.push(side("NO", noLabel, 1 - p, 1 - hi, 1 - r.best_bid));
  return out.length ? out.filter((s) => s.ours > 0) : null;
}

export const best = (ss: Side[]) => ss.reduce((a, b) => (b.value > a.value ? b : a));

/** Quarter-Kelly stake on a binary contract, capped. */
export function stake(s: Side, bankroll: number, kelly: number, cap: number) {
  if (s.verdict !== "value") return 0;
  const f = (s.ours - s.price) / (1 - s.price);
  return Math.max(0, Math.min(kelly * f * bankroll, cap * bankroll));
}
