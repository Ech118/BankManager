/**
 * Client for the orchestrator API. P3 owns this file.
 *
 * Specified by docs/pipeline.md.
 *
 * The mock loader reads fixtures/mock/verdict.json (copied to public/mock/ by
 * scripts/sync-mock.mjs), so the entire UI can be built and demoed before any backend
 * exists. web/ is the most reassignable piece of the project and is never blocked on P1/P2.
 */

import type { AgentEvent, Verdict } from "./types";

export type { AgentEvent };

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class RunFailed extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunFailed";
  }
}

/** Load the ACME fixture. No network to the API, no backend. */
export async function loadMockVerdict(): Promise<Verdict> {
  const res = await fetch("/mock/verdict.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`could not load the mock verdict (${res.status}); run \`npm run sync-mock\``);
  return (await res.json()) as Verdict;
}

/** Start a run. Returns immediately with a run id. */
export async function startAnalysis(ticker: string, asOf?: string): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, as_of: asOf ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new RunFailed(typeof body.detail === "string" ? body.detail : `the server refused the request (${res.status})`);
  }
  return res.json();
}

/** The verdict once the run finishes. A failed run throws RunFailed with the server's reason. */
export async function fetchVerdict(runId: string): Promise<Verdict> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}));
    throw new RunFailed(body.error ?? "the analysis failed");
  }
  if (!res.ok) throw new Error(`could not fetch the run (${res.status})`);
  return res.json();
}

/** What a finished run produced: a full verdict, or (until the synthesizer exists) a preliminary report. */
export type RunResult =
  | { kind: "verdict"; verdict: Verdict }
  | { kind: "preliminary"; markdown: string };

/**
 * The outcome of a finished run. 200 is a Verdict; 409 means the run gathered evidence but has no
 * verdict yet, so the preliminary report is fetched instead; 422 is a failed run with its reason.
 */
export async function fetchResult(runId: string): Promise<RunResult> {
  const base = `${API_BASE}/api/runs/${encodeURIComponent(runId)}`;
  const res = await fetch(base, { cache: "no-store" });
  if (res.status === 409) {
    const rep = await fetch(`${base}/report`, { cache: "no-store" });
    if (!rep.ok) throw new Error(`could not fetch the preliminary report (${rep.status})`);
    return { kind: "preliminary", markdown: (await rep.json()).markdown as string };
  }
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}));
    throw new RunFailed(body.error ?? "the analysis failed");
  }
  if (!res.ok) throw new Error(`could not fetch the run (${res.status})`);
  return { kind: "verdict", verdict: (await res.json()) as Verdict };
}

/**
 * Subscribe to per-agent progress. Drives one lane per agent, which is what makes the
 * parallel pair visible to a viewer. Returns an unsubscribe function.
 */
export function subscribeToEvents(runId: string, onEvent: (event: AgentEvent) => void, onEnd?: () => void): () => void {
  const source = new EventSource(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/events`);
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data) as AgentEvent;
    onEvent(event);
    if (event.agent === "run" && (event.status === "done" || event.status === "failed")) {
      source.close();
      onEnd?.();
    }
  };
  source.onerror = () => {
    source.close(); // the server closes the stream when the run ends; the caller decides what to fetch next
    onEnd?.();
  };
  return () => source.close();
}
