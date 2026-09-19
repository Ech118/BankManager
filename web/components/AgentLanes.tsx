import type { AgentEvent } from "@/lib/types";

interface Lane {
  agent: string;
  status: AgentEvent["status"];
  detail?: string;
  tokens?: number;
}

/** One lane per agent or stage seen so far, so two agents running at once are visible side by side. */
export function AgentLanes({ events }: { events: AgentEvent[] }) {
  const lanes = new Map<string, Lane>();
  for (const e of events) {
    const prev = lanes.get(e.agent);
    lanes.set(e.agent, {
      agent: e.agent,
      status: e.status,
      detail: e.detail ?? prev?.detail,
      tokens: (e.tokens_in ?? 0) + (e.tokens_out ?? 0) || prev?.tokens,
    });
  }
  if (lanes.size === 0) return null;
  return (
    <ol className="lanes" aria-label="Agent progress">
      {[...lanes.values()].map((l) => (
        <li key={l.agent} className={`lane lane-${l.status}`} data-agent={l.agent} data-status={l.status}>
          <span className="lane-name">{l.agent.replaceAll("_", " ")}</span>
          <span className="lane-status">{l.status}</span>
          {l.tokens ? <span className="lane-tokens">{l.tokens.toLocaleString()} tokens</span> : null}
          {l.detail && <span className="lane-detail">{l.detail}</span>}
        </li>
      ))}
    </ol>
  );
}
