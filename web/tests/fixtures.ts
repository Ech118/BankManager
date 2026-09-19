import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Verdict } from "@/lib/types";

const root = resolve(__dirname, ".."); // web/

/** The frozen ACME verdict: the same file the UI demo and the Python contract tests use. */
export function acmeVerdict(): Verdict {
  return JSON.parse(readFileSync(resolve(root, "../fixtures/mock/verdict.json"), "utf-8")) as Verdict;
}

/** Real output of orchestrator/report/generator.py (kept in sync by a Python test). */
export function goldenBodies(): string {
  return readFileSync(resolve(root, "tests/fixtures/section_bodies.md"), "utf-8");
}
