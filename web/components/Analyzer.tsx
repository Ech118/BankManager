"use client";

import { useEffect, useRef, useState } from "react";
import {
  API_BASE,
  DEMO_MODE,
  RunFailed,
  fetchResult,
  loadDemoTickers,
  loadDemoVerdict,
  startAnalysis,
  subscribeToEvents,
  type RunResult,
} from "@/lib/api";
import type { AgentEvent } from "@/lib/types";
import { AgentLanes } from "./AgentLanes";
import { PreliminaryReport } from "./PreliminaryReport";
import { Report } from "./Report";

type Phase = "idle" | "running" | "done" | "failed";

const STEPS = [
  { t: "Agents read", d: "Filings and market data, parsed by structure." },
  { t: "Code computes", d: "Every metric and valuation is deterministic math." },
  { t: "Red team objects", d: "A dedicated agent argues the other side." },
  { t: "Claims checked", d: "Each claim is verified against its source." },
];

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
  const [saved, setSaved] = useState<string[]>([]);
  const [offline, setOffline] = useState(DEMO_MODE);
  const stop = useRef<() => void>(() => {});

  useEffect(() => {
    void loadDemoTickers().then(setSaved);
  }, []);

  useEffect(() => () => stop.current(), []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("ticker"); // shareable link: /?ticker=ACME
    if (q) {
      setTicker(q.toUpperCase());
      void run(q);
    }
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

    // No backend: serve the run that was saved at build time. Also the fallback
    // when the API is unreachable, so a demo never dies on a dead socket.
    if (DEMO_MODE || offline) {
      try {
        setResult({ kind: "verdict", verdict: await loadDemoVerdict(symbol) });
        setPhase("done");
      } catch (err) {
        setError(err instanceof RunFailed ? err.message : "Could not load the saved run.");
        setPhase("failed");
      }
      return;
    }

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
      if (err instanceof TypeError) {
        // The API is not there. Fall back to the saved runs for the rest of the session.
        setOffline(true);
        try {
          setResult({ kind: "verdict", verdict: await loadDemoVerdict(symbol) });
          setPhase("done");
          return;
        } catch (fallback) {
          setError(
            fallback instanceof RunFailed ? fallback.message : describe(err),
          );
          setPhase("failed");
          return;
        }
      }
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
          {phase === "running" ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Analyzing…
            </>
          ) : (
            "Analyze"
          )}
        </button>
      </form>
      {saved.length > 0 && (
        <p className="saved-runs">
          {offline ? "Saved runs (no backend needed): " : "Saved runs: "}
          {saved.map((symbol) => (
            <button
              key={symbol}
              type="button"
              className="ticker-chip"
              onClick={() => {
                setTicker(symbol);
                void run(symbol);
              }}
            >
              {symbol}
            </button>
          ))}
        </p>
      )}
      {phase === "failed" && error && (
        <div className="banner banner-degraded" role="alert">
          {error}
        </div>
      )}
      <AgentLanes events={events} />
      {result?.kind === "verdict" && <Report verdict={result.verdict} />}
      {result?.kind === "preliminary" && <PreliminaryReport markdown={result.markdown} />}
      {phase === "idle" && !result && (
        <ol className="steps" aria-label="How it works">
          {STEPS.map((s, i) => (
            <li key={s.t}>
              <span className="step-n">{i + 1}</span>
              <strong>{s.t}</strong>
              <span className="d">{s.d}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
