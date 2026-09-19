import { Markdown } from "@/lib/markdown";
import { Legend } from "./NumberBadge";

/**
 * A run that gathered evidence but has no verdict yet. It says so plainly and shows NO score,
 * probability or recommendation: a verdict is never invented to fill the gap.
 */
export function PreliminaryReport({ markdown }: { markdown: string }) {
  return (
    <article className="report preliminary" data-kind="preliminary">
      <div className="banner banner-partial" role="note">
        <strong>Preliminary report.</strong> No verdict yet: the scenario, red team and synthesizer steps have not run.
      </div>
      <Legend />
      <Markdown source={markdown} />
    </article>
  );
}
