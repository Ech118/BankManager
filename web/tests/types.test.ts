import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Drift guard for lib/types.ts. Generating the types from schema/verdict.json was evaluated and
 * rejected: the contract declares enum-like fields (valuation, verdict...) as plain strings, so a
 * generator cannot produce the literal unions the UI relies on. Instead, this test fails if the
 * schema gains a REQUIRED field that lib/types.ts does not declare.
 */
const root = resolve(__dirname, "../..");
const schema = JSON.parse(readFileSync(resolve(root, "schema/verdict.json"), "utf-8"));
const source = readFileSync(resolve(__dirname, "../lib/types.ts"), "utf-8");

function interfaceBody(name: string): string {
  const m = new RegExp(`export interface ${name} \\{([\\s\\S]*?)\\n\\}`).exec(source);
  if (!m) throw new Error(`lib/types.ts does not declare interface ${name}`);
  return m[1];
}

const CHECKS: [string, string[]][] = [
  ["Verdict", schema.required],
  ["VerdictCard", schema.$defs.VerdictCard.required],
  ["ReportSection", schema.$defs.ReportSection.required],
  ["ValueObject", schema.$defs.ValueObject?.required ?? ["value", "unit", "type", "status"]],
  ["DataQuality", schema.$defs.DataQuality.required],
  ["Evidence", schema.$defs.Evidence.required],
];

describe("lib/types.ts covers the schema's required fields", () => {
  it.each(CHECKS)("%s", (name, required) => {
    const body = name === "Verdict" ? interfaceBody("Verdict") : interfaceBody(name);
    const missing = (required as string[]).filter((f) => !new RegExp(`\\b${f}\\??:`).test(body));
    expect(missing, `${name}: schema requires fields that lib/types.ts does not declare`).toEqual([]);
  });

  it("knows every red-team field the schema requires", () => {
    const redTeam = schema.$defs.RedTeamBlock.required as string[];
    const body = interfaceBody("Verdict");
    expect(redTeam.filter((f) => !body.includes(f))).toEqual([]);
  });
});
