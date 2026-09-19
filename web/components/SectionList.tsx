import type { ReportSection } from "@/lib/types";
import { Markdown } from "@/lib/markdown";

const STATUS_LABEL: Record<ReportSection["verification_status"], string> = {
  verified: "Verified",
  failed: "Failed verification",
  unverified: "Unverified",
  pending: "Unchecked",
};

/** Sections are expandable and collapsed by default. A section with unverified claims says so before it is opened. */
export function SectionList({ sections }: { sections: ReportSection[] }) {
  return (
    <section aria-labelledby="sections-heading">
      <h2 id="sections-heading">Supporting analysis</h2>
      {sections.map((s) => {
        const flagged = s.verification_status === "failed" || s.verification_status === "unverified";
        return (
          <details key={s.id} className="section" data-section-id={s.id}>
            <summary>
              <span className="section-title">{s.title}</span>
              <span className={`chip chip-${flagged ? "unverified" : s.verification_status === "pending" ? "unchecked" : "verified"}`}>
                {STATUS_LABEL[s.verification_status]}
                {s.unverified_claim_ids.length > 0 && ` (${s.unverified_claim_ids.length} claim${s.unverified_claim_ids.length === 1 ? "" : "s"})`}
              </span>
              <span className="owner">{s.agent}</span>
            </summary>
            <Markdown source={s.body_markdown} />
          </details>
        );
      })}
    </section>
  );
}
