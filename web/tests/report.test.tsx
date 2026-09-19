import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AgentLanes } from "@/components/AgentLanes";
import { DISCLAIMER } from "@/components/Disclaimer";
import { Report } from "@/components/Report";
import { SiteShell } from "@/components/SiteShell";
import { Analyzer } from "@/components/Analyzer";
import { formatValue } from "@/lib/format";
import { Markdown } from "@/lib/markdown";
import type { AgentEvent, ValueObject, Verdict } from "@/lib/types";
import { acmeVerdict, goldenBodies } from "./fixtures";

afterEach(cleanup);

const vo = (over: Partial<ValueObject>): ValueObject => ({
  value: 1, unit: "fraction", type: "fact", status: "ok", source_id: "src:x:1", ...over,
});

describe("the disclaimer (error M)", () => {
  it("is in the site shell, so every page has it", () => {
    render(<SiteShell><p>any page</p></SiteShell>);
    expect(screen.getByRole("note", { name: "Disclaimer" })).toHaveTextContent(DISCLAIMER);
  });

  it("is on the home page, before any analysis exists", () => {
    render(<SiteShell><Analyzer /></SiteShell>);
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
  });

  it("is on the report itself as well as the footer", () => {
    render(<SiteShell><Report verdict={acmeVerdict()} /></SiteShell>);
    expect(screen.getAllByText(DISCLAIMER).length).toBe(2);
  });

  it("uses the same words as the Python generator", () => {
    expect(acmeVerdict().disclaimer).toBe(DISCLAIMER);
  });
});

describe("layout order", () => {
  it("shows the verdict card first, the case against second, then the sections", () => {
    const { container } = render(<Report verdict={acmeVerdict()} />);
    const order = ["verdict-heading", "against-heading", "sections-heading"].map((id) => container.querySelector(`#${id}`)!);
    expect(order.every(Boolean)).toBe(true);
    expect(order[0].compareDocumentPosition(order[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(order[1].compareDocumentPosition(order[2]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("collapses every section by default", () => {
    const { container } = render(<Report verdict={acmeVerdict()} />);
    const sections = container.querySelectorAll("details.section");
    expect(sections.length).toBe(acmeVerdict().sections.length);
    sections.forEach((d) => expect(d).not.toHaveAttribute("open"));
  });

  it("states the verdict word and the plain-language $10,000 answer", () => {
    render(<Report verdict={acmeVerdict()} />);
    expect(screen.getByTestId("verdict-word")).toHaveTextContent("avoid");
    expect(screen.getByText(/\$10,000 for five years/)).toBeInTheDocument();
  });
});

describe("numbers", () => {
  it("colours each number by its type", () => {
    const { container } = render(<Report verdict={acmeVerdict()} />);
    expect(container.querySelector('[data-value-type="fact"]')).toBeTruthy();
    expect(container.querySelector('[data-value-type="estimate"]')).toBeTruthy();
    expect(container.querySelector(".num-fact")).not.toEqual(container.querySelector(".num-estimate"));
  });

  it("renders unavailable as the word, never 0 or a blank", () => {
    const v = acmeVerdict();
    v.card.price = vo({ value: null, status: "unavailable", unit: "usd_per_share" });
    render(<Report verdict={v} />);
    expect(screen.getAllByText("unavailable")[0]).toBeInTheDocument();
    expect(formatValue(v.card.price)).toBe("unavailable");
    expect(formatValue(null)).toBe("unavailable");
  });

  it("keeps a real zero as zero", () => {
    expect(formatValue(vo({ value: 0 }))).toBe("0.0%");
  });

  it.each([
    [{ value: 0.4, unit: "fraction" }, "40.0%"],
    [{ value: 5e9, unit: "usd" }, "$5.00B"],
    [{ value: 600e6, unit: "usd" }, "$600.0M"],
    [{ value: 1.48, unit: "usd_per_share" }, "$1.48"],
    [{ value: 33.78, unit: "multiple" }, "33.8x"],
    [{ value: 395e6, unit: "shares" }, "395.0M shares"],
    [{ value: 51.1, unit: "days" }, "51 days"],
  ] as [Partial<ValueObject>, string][])("formats %j like the Python generator", (over, expected) => {
    expect(formatValue(vo(over))).toBe(expected);
  });
});

describe("verification markers", () => {
  it("renders the generator's real markdown: unverified, unchecked and typed numbers", () => {
    const { container } = render(<Markdown source={goldenBodies()} />);
    expect(container.querySelector(".chip-unverified")).toHaveTextContent("Unverified");
    expect(container.querySelector(".chip-unchecked")).toHaveTextContent("Unchecked");
    expect(container.querySelector('[data-value-type="assumption"]')).toHaveTextContent("40.0%");
    expect(container.querySelector('[data-value-type="fact"]')).toHaveTextContent("-2.4%");
    expect(screen.getByText(/Buybacks shrank the diluted share count/)).toBeInTheDocument(); // shown, never hidden
    expect(container.querySelector("blockquote")).toBeTruthy();
  });

  it("flags a section with unverified claims before it is opened", () => {
    const v = acmeVerdict();
    v.sections[1] = { ...v.sections[1], verification_status: "failed", unverified_claim_ids: ["claim:x:1", "claim:x:2"] };
    const { container } = render(<Report verdict={v} />);
    const summary = container.querySelector('[data-section-id="financials"] summary')!;
    expect(within(summary as HTMLElement).getByText(/Failed verification \(2 claims\)/)).toBeInTheDocument();
  });

  it("states how many claims could not be verified", () => {
    const v = acmeVerdict();
    v.audit = { passed: false, claims_checked: 16, claims_verified: 14, claims_unverified: 2 };
    render(<Report verdict={v} />);
    expect(screen.getByTestId("audit-summary")).toHaveTextContent("2 claim(s) could not be verified");
  });
});

describe("banners", () => {
  it("shows the data-quality banner only when quality is not ok", () => {
    const ok = render(<Report verdict={acmeVerdict()} />);
    expect(ok.container.querySelector(".banner-partial")).toBeNull();
    cleanup();
    const v: Verdict = { ...acmeVerdict(), data_quality: { overall: "partial", gaps: ["No news available"] } };
    render(<Report verdict={v} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Data quality: partial");
    expect(screen.getByText("No news available")).toBeInTheDocument();
  });

  it("labels mock data as fictional", () => {
    render(<Report verdict={acmeVerdict()} />);
    expect(screen.getByText(/fictional company/)).toBeInTheDocument();
  });
});

describe("untrusted text (error F)", () => {
  it("displays markup in report text as text and never injects it", () => {
    const evil = "- <script>window.hacked=1</script> <img src=x onerror=alert(1)> **bold**\n> <b onmouseover=1>quote</b>";
    const { container } = render(<Markdown source={evil} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>window.hacked=1</script>");
    expect((window as unknown as { hacked?: number }).hacked).toBeUndefined();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
  });
});

describe("agent lanes", () => {
  const ev = (agent: string, status: AgentEvent["status"], extra: Partial<AgentEvent> = {}): AgentEvent => ({
    run_id: "r", agent, status, ts: "2026-09-19T12:00:00Z", ...extra,
  });

  it("shows one lane per agent, so parallel agents are visible together", () => {
    const { container } = render(
      <AgentLanes events={[ev("ingest", "done"), ev("financial", "running"), ev("business", "running")]} />,
    );
    const running = container.querySelectorAll('[data-status="running"]');
    expect(running.length).toBe(2);
    expect(container.querySelectorAll("li.lane").length).toBe(3);
  });

  it("keeps the latest status and the token count for an agent", () => {
    render(<AgentLanes events={[ev("financial", "running"), ev("financial", "done", { tokens_in: 900, tokens_out: 100 })]} />);
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("1,000 tokens")).toBeInTheDocument();
  });

  it("renders nothing before the first event", () => {
    const { container } = render(<AgentLanes events={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("preliminary report", () => {
  it("says there is no verdict, and shows no score, probability or recommendation", async () => {
    const { PreliminaryReport } = await import("@/components/PreliminaryReport");
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const md = readFileSync(resolve(__dirname, "fixtures/preliminary_report.md"), "utf-8");
    const { container } = render(<PreliminaryReport markdown={md} />);
    expect(screen.getAllByText(/No verdict yet/).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("verdict-word")).toBeNull();
    expect(container.textContent).not.toMatch(/Probability of beating/);
    expect(container.querySelector("[data-kind='preliminary']")).toBeTruthy();
    expect(container.querySelector('[data-value-type="fact"]')).toBeTruthy(); // numbers still typed
    expect(container.textContent).toContain(DISCLAIMER);
  });
});

describe("analyzer errors", () => {
  it("explains an unreachable server instead of showing 'Failed to fetch'", async () => {
    const { vi } = await import("vitest");
    const { fireEvent } = await import("@testing-library/react");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<Analyzer />);
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "ACME" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not reach the analysis server/);
    vi.unstubAllGlobals();
  });

  it("rejects a malformed ticker before any network call", async () => {
    const { fireEvent } = await import("@testing-library/react");
    render(<Analyzer />);
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AA;DROP" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/1-5 letters/);
  });
});
