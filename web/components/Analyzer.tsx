"use client";

import { useEffect, useRef, useState } from "react";
import { RunFailed, fetchVerdict, startAnalysis, subscribeToEvents } from "@/lib/api";
import type { AgentEvent, Verdict } from "@/lib/types";
import { AgentLanes } from "./AgentLanes";
import { Report } from "./Report";

type Phase = "idle" | "running" | "done" | "failed";

/** Ticker in, live per-agent lanes while the run is going, then the report. */
export function Analyzer() {
  const [ticker, setTicker] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stop = useRef<() => void>(() => {});

  useEffect(() => () => stop.current(), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const symbol = ticker.trim().toUpperCase();
    if (!/^[A-Z]{1,5}([.-][A-Z])?$/.test(symbol)) {
      setError("Enter a ticker of 1-5 letters, for example ACME or BRK.B.");
      setPhase("failed");
      return;
    }
    setPhase("running");
    setError(null);
    setVerdict(null);
    setEvents([]);
    try {
      const { run_id } = await startAnalysis(symbol);
      stop.current = subscribeToEvents(
        run_id,
        (ev) => setEvents((prev) => [...prev, ev]),
        async () => {
          try {
            setVerdict(await fetchVerdict(run_id));
            setPhase("done");
          } catch (err) {
            setError(err instanceof RunFailed ? err.message : "Could not fetch the result.");
            setPhase("failed");
          }
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the analysis.");
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
      {verdict && <Report verdict={verdict} />}
    </div>
  );
}
