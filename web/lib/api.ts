/**
 * Client for the orchestrator API. P3 owns this file.
 *
 * Specified by docs/pipeline.md.
 *
 * MODE=mock loads fixtures/mock/verdict.json directly, so the entire UI can be
 * built and demoed before any backend exists. That is deliberate: web/ is the
 * most reassignable piece of work in the project, and it should never be
 * blocked on P1 or P2.
 *
 * TODO(roadmap Step 2, P3): mock loader.
 * TODO(roadmap Step 3, P3): live fetch + SSE subscription.
 */

import type { Verdict } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface AgentEvent {
  run_id: string;
  agent: string;
  status: "pending" | "running" | "retrying" | "done" | "failed";
  ts: string;
  detail?: string;
}

/** Load the ACME fixture. No network, no backend. */
export async function loadMockVerdict(): Promise<Verdict> {
  throw new Error("TODO(roadmap Step 2, P3): load fixtures/mock/verdict.json");
}

/** Start a run. Returns immediately with a run id. */
export async function startAnalysis(ticker: string): Promise<{ run_id: string }> {
  throw new Error("TODO(roadmap Step 3, P3): POST /api/analyze");
}

/** The verdict once the run finishes. */
export async function fetchVerdict(runId: string): Promise<Verdict> {
  throw new Error("TODO(roadmap Step 3, P3): GET /api/runs/{id}");
}

/**
 * Subscribe to per-agent progress. Drives one lane per agent, which is what
 * makes the parallel pair visible to a viewer.
 */
export function subscribeToEvents(
  runId: string,
  onEvent: (event: AgentEvent) => void,
): () => void {
  throw new Error("TODO(roadmap Step 3, P3): SSE /api/runs/{id}/events");
}
