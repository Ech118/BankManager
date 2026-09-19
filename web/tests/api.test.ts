import { afterEach, describe, expect, it, vi } from "vitest";
import { RunFailed, fetchVerdict, startAnalysis } from "@/lib/api";
import { acmeVerdict } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

const respond = (status: number, body: unknown) => vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

describe("api client", () => {
  it("surfaces the server's validation message when a ticker is refused", async () => {
    vi.stubGlobal("fetch", respond(422, { detail: "Ticker must be 1-5 letters" }));
    await expect(startAnalysis("nope!")).rejects.toThrow("Ticker must be 1-5 letters");
  });

  it("turns a failed run (422) into RunFailed with the reason, e.g. an out-of-scope bank", async () => {
    vi.stubGlobal("fetch", respond(422, { status: "failed", error: "Banks are out of scope for v1." }));
    await expect(fetchVerdict("abc")).rejects.toBeInstanceOf(RunFailed);
    await expect(fetchVerdict("abc")).rejects.toThrow("Banks are out of scope");
  });

  it("returns the verdict for a finished run", async () => {
    vi.stubGlobal("fetch", respond(200, acmeVerdict()));
    expect((await fetchVerdict("abc")).ticker).toBe("ACME");
  });

  it("posts the ticker as JSON", async () => {
    const f = respond(200, { run_id: "r1" });
    vi.stubGlobal("fetch", f);
    expect(await startAnalysis("ACME")).toEqual({ run_id: "r1" });
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ ticker: "ACME", as_of: null });
  });
});

describe("types match the real fixture", () => {
  it("has every field the UI reads", () => {
    const v = acmeVerdict();
    for (const k of ["disclaimer", "card", "sections", "red_team", "data_quality", "mode", "as_of"]) expect(v).toHaveProperty(k);
    for (const k of ["price", "market_cap", "thesis", "scores", "p_beat_sp500_5y", "expected_5y_return", "expected_return_vs_sp500", "verdict", "ten_thousand_dollar_answer"]) {
      expect(v.card).toHaveProperty(k);
    }
    expect(v.sections.length).toBe(14);
    for (const s of v.sections) for (const k of ["id", "title", "body_markdown", "agent", "verification_status", "unverified_claim_ids"]) expect(s).toHaveProperty(k);
  });
});
