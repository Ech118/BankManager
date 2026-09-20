type Kind = "code" | "agent" | "check" | "output";

interface Node {
  kind: Kind;
  title: string;
  does: string;
  never?: string;
}

const KIND_LABEL: Record<Kind, string> = { code: "Code", agent: "AI agent", check: "Verification", output: "Result" };

/** Each row runs top to bottom; nodes in the same row run at the same time. Mirrors docs/pipeline.md. */
const FLOW: { step: string; nodes: Node[]; note?: string }[] = [
  {
    step: "Ticker in",
    nodes: [{ kind: "code", title: "Scope check", does: "Refuses banks, insurers, REITs and pre-revenue companies before any AI runs.", never: "Guess at a company it does not understand." }],
  },
  {
    step: "Ingest",
    nodes: [{ kind: "code", title: "Facts store", does: "SEC filings, XBRL facts, filing sections, market snapshot and news, each number with its source and filing date.", never: "Use data filed after the analysis date." }],
  },
  {
    step: "Read in parallel",
    nodes: [
      { kind: "agent", title: "Financial Agent", does: "Reads the numbers: growth, margins, cash flow, balance sheet, earnings quality.", never: "Do arithmetic. It cites fact IDs." },
      { kind: "agent", title: "Business Agent", does: "Reads the filings: model, competition, risks, management, wording changes.", never: "See the Financial Agent's work." },
    ],
    note: "Two independent readings, so a later check can catch them contradicting each other.",
  },
  {
    step: "Value",
    nodes: [
      { kind: "agent", title: "Valuation Agent", does: "Chooses peers and methods, then asks: what growth does today's price assume, and do the filings support it?", never: "Compute a multiple or DCF itself." },
      { kind: "code", title: "calc: valuation", does: "Multiples, peer comparison, DCF and reverse DCF with a sensitivity grid.", never: "Call a model." },
    ],
    note: "The agent calls the code for every number.",
  },
  {
    step: "Scenarios",
    nodes: [{ kind: "agent", title: "Scenario Agent", does: "Proposes bear, base and bull cases, a requested weight for each, and one tilt to the prior, with reasons.", never: "State P(beat S&P), a score or a price target." }],
  },
  {
    step: "Challenge",
    nodes: [{ kind: "agent", title: "Red Team", does: "Argues the strongest case against, from the raw facts. Finds the likeliest drawdown path. May push the prior down.", never: "Just restate the others in a sceptical tone." }],
  },
  {
    step: "Bound the numbers",
    nodes: [{ kind: "code", title: "calc: scenarios", does: "Clamps scenario weights into a fixed band, caps the combined prior shift, then derives probabilities, expected returns and scores.", never: "Let an agent exceed the caps." }],
  },
  {
    step: "Conclude",
    nodes: [{ kind: "agent", title: "Synthesizer", does: "Writes the thesis, answers every red-team point, picks catalyst and risk, gives the $10,000 answer.", never: "Write a number. Its verdict word must pass the consistency check." }],
  },
  {
    step: "Check",
    nodes: [{ kind: "check", title: "Verifier", does: "Seven deterministic checks, then one AI check for qualitative claims. A failure goes back to the agent that owns it, at most twice; after that the claim ships marked unverified.", never: "Hide a failed claim." }],
    note: "retry",
  },
  {
    step: "Deliver",
    nodes: [{ kind: "output", title: "Report generator", does: "Renders the verdict card and the full report from the structured research state.", never: "Use free-form agent text." }],
  },
];

const HIERARCHY_TOOLS = [
  { title: "Data tools", sub: "SEC filings, facts, market data, news, served over MCP" },
  { title: "calc", sub: "All metrics, valuation and scenario math" },
  { title: "audit", sub: "Deterministic verification of every claim" },
];

const AGENTS = ["Financial", "Business", "Valuation", "Scenario", "Red Team", "Synthesizer"];

function NodeCard({ n }: { n: Node }) {
  return (
    <div className={`fc-node fc-${n.kind}`}>
      <span className="fc-kind">{KIND_LABEL[n.kind]}</span>
      <strong>{n.title}</strong>
      <p>{n.does}</p>
      {n.never && (
        <p className="fc-never">
          <span>Never:</span> {n.never}
        </p>
      )}
    </div>
  );
}

/** Who reports to whom, then the run from ticker to report. Pure markup: it needs no data and no client code. */
export function FlowChart() {
  return (
    <div className="fc">
      <ul className="fc-legend" aria-label="Legend">
        {(["agent", "code", "check", "output"] as Kind[]).map((k) => (
          <li key={k}>
            <span className={`fc-swatch fc-${k}`} />
            {KIND_LABEL[k]}
          </li>
        ))}
      </ul>

      <section aria-labelledby="hier-heading">
        <h2 id="hier-heading">Who does what</h2>
        <div className="fc-tree">
          <div className="fc-node fc-coordinator">
            <span className="fc-kind">Orchestrator</span>
            <strong>Coordinator</strong>
            <p>Runs the stages in order, passes each agent only what it needs, retries failures, and assembles the result.</p>
          </div>
          <div className="fc-branch" aria-hidden="true" />
          <div className="fc-agents">
            {AGENTS.map((a) => (
              <span key={a} className="fc-node fc-agent fc-chip">
                {a}
              </span>
            ))}
          </div>
          <p className="fc-tree-note">Six agents. They interpret; they never calculate.</p>
          <div className="fc-branch" aria-hidden="true" />
          <div className="fc-tools">
            {HIERARCHY_TOOLS.map((t) => (
              <div key={t.title} className="fc-node fc-code">
                <strong>{t.title}</strong>
                <p>{t.sub}</p>
              </div>
            ))}
          </div>
          <p className="fc-tree-note">Plain code. No model runs here, so the numbers are reproducible.</p>
        </div>
      </section>

      <section aria-labelledby="flow-heading">
        <h2 id="flow-heading">What happens in a run</h2>
        <ol className="fc-flow">
          {FLOW.map((row, i) => (
            <li key={row.step} className="fc-row">
              <span className="fc-step">
                <span className="fc-n">{i + 1}</span>
                {row.step}
              </span>
              <div className={`fc-nodes fc-cols-${row.nodes.length}`}>
                {row.nodes.map((n) => (
                  <NodeCard key={n.title} n={n} />
                ))}
              </div>
              {row.note === "retry" ? (
                <p className="fc-retry">
                  <span aria-hidden="true">↺</span> On failure: back to the owning agent (max 2 retries), then re-check.
                </p>
              ) : (
                row.note && <p className="fc-note">{row.note}</p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
