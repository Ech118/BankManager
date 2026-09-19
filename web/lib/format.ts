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
