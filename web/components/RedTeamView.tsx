import type { Verdict } from "@/lib/types";
import { mergeStanceLeads, parseDrawdown, splitObjection, stanceOf, stripMock, toPoints } from "@/lib/format";

const cap1 = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
const STANCE_LABEL = { accepted: "Accepted", rebutted: "Rebutted", partial: "Partly" } as const;

/** The case against, immediately after the card: the objection is read before the supporting detail. Broken into short points, not an essay. */
export function RedTeamView({ redTeam }: { redTeam: Verdict["red_team"] }) {
  const risks = toPoints(stripMock(redTeam.summary));
  const drawdown = redTeam.drawdown_path ? stripMock(redTeam.drawdown_path) : null;
  const path = drawdown ? parseDrawdown(drawdown) : null;
  const responses = mergeStanceLeads(toPoints(stripMock(redTeam.responses_by_synthesizer))).map(stanceOf);
  return (
    <section className="red-team" aria-labelledby="against-heading">
      <h2 id="against-heading">The case against</h2>
      <h3 className="rt-sub">Key objections</h3>
      <ol className="rt-points">
        {risks.map((r, i) => {
          const o = splitObjection(r);
          return (
            <li key={i} data-n={i + 1}>
              {o.lead ? <strong>{o.lead}</strong> : null} {o.rest || (!o.lead ? r : "")}
              {o.items.length > 0 && (
                <ul className="rt-sub-points">
                  {o.items.map((it, j) => (
                    <li key={j}>{it}</li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      {responses.length > 0 && (
        <>
          <h3 className="rt-sub">How the analysis responded</h3>
          <ul className="rt-points responses">
            {responses.map((r, i) => (
              <li key={i}>
                <span className={`stance stance-${r.stance ?? "none"}`}>{r.stance ? STANCE_LABEL[r.stance] : "Noted"}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {drawdown && (
        <div className="drawdown">
          <strong>Drawdown path</strong>
          {path ? (
            <>
              <ol className="dd-steps">
                {path.steps.map((st) => (
                  <li key={st.n}>
                    <span className="dd-n">{st.n}</span>
                    <span>
                      {st.when && <em className="dd-when">{cap1(st.when)}</em>}
                      {st.body}
                    </span>
                  </li>
                ))}
              </ol>
              {path.tail && <p className="dd-tail">{path.tail}</p>}
            </>
          ) : (
            drawdown
          )}
        </div>
      )}
    </section>
  );
}
