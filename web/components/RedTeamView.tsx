import type { Verdict } from "@/lib/types";

/** The case against, immediately after the card: the objection is read before the supporting detail. */
export function RedTeamView({ redTeam }: { redTeam: Verdict["red_team"] }) {
  return (
    <section className="red-team" aria-labelledby="against-heading">
      <h2 id="against-heading">The case against</h2>
      <p>{redTeam.summary}</p>
      <p>
        <strong>Response:</strong> {redTeam.responses_by_synthesizer}
      </p>
      {redTeam.drawdown_path && (
        <p>
          <strong>Drawdown path:</strong> {redTeam.drawdown_path}
        </p>
      )}
    </section>
  );
}
