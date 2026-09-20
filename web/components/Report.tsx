import type { Verdict } from "@/lib/types";
import { DataQualityBanner } from "./DataQualityBanner";
import { Disclaimer } from "./Disclaimer";
import { Legend } from "./NumberBadge";
import { RedTeamView } from "./RedTeamView";
import { SectionList } from "./SectionList";
import { VerdictCardView } from "./VerdictCardView";

/** The whole report in its mandated order: banner, verdict card, the case against, then the detail. */
export function Report({ verdict }: { verdict: Verdict }) {
  const audit = verdict.audit;
  return (
    <article className="report" data-mode={verdict.mode}>
      <DataQualityBanner quality={verdict.data_quality} />
      <VerdictCardView card={verdict.card} />
      <RedTeamView redTeam={verdict.red_team} />
      <Legend />
      <SectionList sections={verdict.sections} />
      {audit && (
        <p className="audit" data-testid="audit-summary">
          {audit.claims_unverified > 0
            ? `${audit.claims_unverified} claim(s) could not be verified and are marked above.`
            : `Verification: ${audit.claims_verified} of ${audit.claims_checked} claims checked and verified.`}{" "}
          As of {verdict.as_of}.
        </p>
      )}
      <Disclaimer text={verdict.disclaimer} />
    </article>
  );
}
