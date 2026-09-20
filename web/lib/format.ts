import type { ValueObject } from "./types";

/**
 * Format one ValueObject for display. Mirrors orchestrator/report/generator.py::format_value
 * so the card and the rendered report agree to the character.
 *
 * `unavailable` renders as "unavailable", never as 0 or a blank: a reader must be able to
 * tell a missing number from a zero one.
 */
export function formatValue(v: ValueObject | null | undefined): string {
  if (!v || v.status !== "ok" || v.value === null || v.value === undefined) return "unavailable";
  const x = v.value;
  switch (v.unit) {
    case "fraction":
      return `${(x * 100).toFixed(1)}%`;
    case "usd": {
      const a = Math.abs(x);
      if (a >= 1e9) return `$${(x / 1e9).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}B`;
      if (a >= 1e6) return `$${(x / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
      return `$${x.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    }
    case "usd_per_share":
      return `$${x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "multiple":
      return `${x.toFixed(1)}x`;
    case "shares":
      return `${(x / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M shares`;
    case "days":
      return `${x.toFixed(0)} days`;
    case "count":
      return x.toLocaleString("en-US", { maximumFractionDigits: 0 });
    default:
      return x.toFixed(2);
  }
}

export const VALUE_TYPES = ["fact", "estimate", "assumption"] as const;
export type ValueType = (typeof VALUE_TYPES)[number];

export const TYPE_LABEL: Record<ValueType, string> = {
  fact: "Fact: reported in a filing, or computed in code from reported values",
  estimate: "Estimate: a forecast (consensus or a scenario output)",
  assumption: "Assumption: a chosen input (discount rate, exit multiple...)",
};

export function humanize(word: string): string {
  return word.replaceAll("_", " ");
}

/** Display-only: drops "(fictional mock)" / "(mock)" tags, "_Mock content for **X**..._" lead-ins and "Mock warning:" prefixes. */
export function stripMock(text: string): string {
  return text
    .replace(/\s*\((?:fictional )?mock\)/gi, "")
    .replace(/_Mock content for [^_]*_\s*/g, "")
    .replace(/^Mock warning:\s*/i, "");
}

const SENTENCE_BREAK = /(?<=[.!?])\s+(?=[A-Z"'(])/;

/** Splits prose into sentences, and each sentence further at semicolons, so a wall of text becomes short points. */
export function toPoints(text: string): string[] {
  return text
    .split(SENTENCE_BREAK)
    .flatMap((s) => s.split(/;\s+/))
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .map((s) => (/[.!?]$/.test(s) ? s : `${s}.`));
}

export type Stance = "accepted" | "rebutted" | "partial";

/** Reads how the synthesizer answered one red-team point ("R1: Accepted...", "On the claim that...: accepted, ..."). */
export function stanceOf(sentence: string): { stance: Stance | null; text: string } {
  const stripped = sentence.replace(/^R\d+:\s*/, "");
  const lead = /^(?:not accepted|partially accepted|accepted|rebutted|rejected)\b[:.,]?\s*/i.exec(stripped);
  const text = lead && stripped.length > lead[0].length ? stripped.slice(lead[0].length).replace(/^./, (c) => c.toUpperCase()) : stripped;
  const m = /\b(not accepted|partially accepted|accepted|rebutted|rejected|mixed)\b/i.exec(lead ? lead[0] : text);
  if (!m) return { stance: null, text };
  const w = m[1].toLowerCase();
  const stance: Stance = w === "accepted" ? "accepted" : w === "rebutted" || w === "rejected" || w === "not accepted" ? "rebutted" : "partial";
  return { stance, text };
}

/** "R1: Accepted." followed by its reasoning is one response, not two: join a bare stance word to the sentence after it. */
export function mergeStanceLeads(points: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < points.length; i++) {
    const bare = /^(?:R\d+:\s*)?(?:not accepted|partially accepted|accepted|rebutted|rejected)[.:]?$/i.test(points[i]);
    if (bare && i + 1 < points.length) {
      out.push(`${points[i].replace(/[.:]$/, "")}: ${points[i + 1]}`);
      i++;
    } else out.push(points[i]);
  }
  return out;
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** One long objection -> a headline (text before the first colon) plus its comma-separated evidence, when that reads as a list. */
export function splitObjection(text: string): { lead: string | null; items: string[]; rest: string } {
  const colon = text.indexOf(": ");
  if (colon < 0 || colon > 140) return { lead: null, items: [], rest: text };
  const lead = text.slice(0, colon + 1);
  const rest = text.slice(colon + 2).replace(/[.]$/, "");
  const parts = rest
    .split(/,\s+(?:and\s+)?/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length >= 3 && parts.every((p) => p.length >= 20)) return { lead, items: parts.map(cap), rest: "" };
  return { lead, items: [], rest: text.slice(colon + 2) };
}

export interface DrawdownStep {
  n: number;
  when: string | null;
  body: string;
}

/** "Step 1 (next quarter): ... Step 2: ... Early warning signs ..." -> numbered steps and a closing note. Null when it is not step-shaped. */
export function parseDrawdown(text: string): { steps: DrawdownStep[]; tail: string | null } | null {
  const chunks = text.split(/\s*(?=\bStep \d+\b)/).filter((c) => c.trim());
  const steps: DrawdownStep[] = [];
  let tail: string | null = null;
  for (const c of chunks) {
    const m = /^Step (\d+)\s*(?:\(([^)]*)\))?\s*:\s*([\s\S]*)$/.exec(c.trim());
    if (!m) continue;
    let body = m[3].trim();
    const t = /\s(Early warning[\s\S]*)$/.exec(body);
    if (t) {
      tail = t[1].trim();
      body = body.slice(0, t.index).trim();
    }
    steps.push({ n: Number(m[1]), when: m[2] ?? null, body: cap(body) });
  }
  return steps.length >= 2 ? { steps, tail } : null;
}
