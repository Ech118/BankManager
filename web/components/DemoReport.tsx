"use client";

import { useEffect, useState } from "react";
import { loadMockVerdict } from "@/lib/api";
import type { Verdict } from "@/lib/types";
import { Report } from "./Report";

/** The fixture ACME report. No backend needed. */
export function DemoReport() {
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadMockVerdict().then(setVerdict, (e: Error) => setError(e.message));
  }, []);
  if (error) return <div className="banner banner-degraded" role="alert">{error}</div>;
  if (!verdict) return <p className="muted">Loading the demo report…</p>;
  return <Report verdict={verdict} />;
}
