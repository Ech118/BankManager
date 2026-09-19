"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, RunFailed, fetchResult, startAnalysis, subscribeToEvents, type RunResult } from "@/lib/api";
import type { AgentEvent } from "@/lib/types";
import { AgentLanes } from "./AgentLanes";
import { PreliminaryReport } from "./PreliminaryReport";
import { Report } from "./Report";

type Phase = "idle" | "running" | "done" | "failed";

/** A browser network failure says only "Failed to fetch"; say what is actually wrong and how to fix it. */
function describe(err: unknown): string {
  if (err instanceof TypeError) {
    return `Could not reach the analysis server at ${API_BASE}. Is it running (uvicorn orchestrator.server:app --port 8000)?`;
  }
  return err instanceof Error ? err.message : "Could not start the analysis.";
}

/** Ticker in, live per-agent lanes while the run is going, then the report. */
export function Analyzer() {
  const [ticker, setTicker] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef<() => void>(() => {});

  useEffect(() => () => stop.current(), []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("ticker"); // shareable link: /?ticker=ACME
    if (q) {
      setTicker(q.toUpperCase());
      void run(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void run(ticker);
  }

  async function run(raw: string) {
    const symbol = raw.trim().toUpperCase();
    if (!/^[A-Z]{1,5}([.-][A-Z])?$/.test(symbol)) {
      setError("Enter a ticker of 1-5 letters, for example ACME or BRK.B.");
      setPhase("failed");
      return;
    }
    setPhase("running");
    setError(null);
    setResult(null);
    setEvents([]);
    try {
      const { run_id } = await startAnalysis(symbol);
      stop.current = subscribeToEvents(
        run_id,
        (ev) => setEvents((prev) => [...prev, ev]),
        async () => {
          try {
            setResult(await fetchResult(run_id));
            setPhase("done");
          } catch (err) {
            setError(err instanceof RunFailed ? err.message : "Could not fetch the result.");
            setPhase("failed");
          }
        },
      );
    } catch (err) {
      setError(describe(err));
      setPhase("failed");
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="ticker-form">
        <label htmlFor="ticker">Ticker</label>
        <input
          id="ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="ACME"
          autoComplete="off"
          spellCheck={false}
          maxLength={7}
        />
        <button type="submit" disabled={phase === "running"}>
          {phase === "running" ? "Analyzing…" : "Analyze"}
        </button>
      </form>
      {phase === "failed" && error && (
        <div className="banner banner-degraded" role="alert">
          {error}
        </div>
      )}
      <AgentLanes events={events} />
      {result?.kind === "verdict" && <Report verdict={result.verdict} />}
      {result?.kind === "preliminary" && <PreliminaryReport markdown={result.markdown} />}
    </div>
  );
}
