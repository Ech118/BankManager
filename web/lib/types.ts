/**
 * Types mirroring schema/*.json. P3 owns this file.
 *
 * Specified by docs/research-state.md.
 *
 * The JSON Schema files are GENERATED from schema/contracts/ (pydantic). This
 * file is the TypeScript view of the same contracts, which is the reason the
 * generated JSON is committed at all: a non-Python consumer needs something to
 * read.
 *
 * TODO(roadmap Step 2, P3): generate these from schema/*.json instead of
 * maintaining them by hand, so they cannot drift.
 */

/** Every reported or computed number. Fractions, not percents. */
export interface ValueObject {
  value: number | null;
  unit:
    | "usd"
    | "usd_per_share"
    | "shares"
    | "fraction"
    | "multiple"
    | "count"
    | "days"
    | "ratio";
  /** Drives the colour coding: fact, estimate and assumption look different. */
  type: "fact" | "estimate" | "assumption";
  /** `unavailable` renders as "unavailable", never as 0 or a blank. */
  status: "ok" | "unavailable";
  source_id: string | null;
  derived_from?: string[];
}

export interface Evidence {
  quote: string;
  source_id: string;
}

export interface Scores {
  short_term: number;
  medium_term: number;
  long_term: number;
}

/** Keys match Scores; labels are 0-12m, 1-3y, 3-5y. */
export interface HorizonValues {
  short_term: ValueObject;
  medium_term: ValueObject;
  long_term: ValueObject;
}

export const HORIZON_LABELS: Record<keyof HorizonValues, string> = {
  short_term: "0-12m",
  medium_term: "1-3y",
  long_term: "3-5y",
};

export interface VerdictCard {
  company: string;
  ticker: string;
  price: ValueObject;
  market_cap: ValueObject;
  thesis: string;
  scores: Scores;
  p_beat_sp500_5y: number;
  expected_5y_return: ValueObject;
  expected_return_vs_sp500: HorizonValues;
  primary_catalyst: string;
  biggest_risk: string;
  valuation: "cheap" | "reasonable" | "expensive" | "extremely_expensive";
  business_quality: "poor" | "average" | "good" | "excellent";
  financial_strength: "weak" | "average" | "strong" | "fortress";
  verdict: "strong_buy" | "buy" | "speculative_buy" | "hold" | "avoid" | "sell";
  ten_thousand_dollar_answer: { choice: "this_stock" | "sp500"; reason: string };
}

export interface ReportSection {
  id: string;
  title: string;
  body_markdown: string;
  agent: string;
  evidence: Evidence[];
  verification_status: "pending" | "verified" | "failed" | "unverified";
  /** Rendered with a visible marker. Never hidden. */
  unverified_claim_ids: string[];
}

export interface DataQuality {
  overall: "ok" | "partial" | "degraded";
  gaps: string[];
}

export interface Verdict {
  schema_version: string;
  ticker: string;
  as_of: string;
  generated_at: string;
  mode: "live" | "mock" | "backtest";
  /** Required, non-empty, on every page. */
  disclaimer: string;
  card: VerdictCard;
  sections: ReportSection[];
  red_team: {
    summary: string;
    responses_by_synthesizer: string;
    drawdown_path?: string | null;
  };
  data_quality: DataQuality;
  [key: string]: unknown;
}
