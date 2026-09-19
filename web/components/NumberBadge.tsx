import { formatValue } from "@/lib/format";
import type { ValueObject } from "@/lib/types";
import { NumberToken } from "@/lib/markdown";

/** A ValueObject coloured by its type. `unavailable` reads "unavailable", never 0 or blank. */
export function NumberBadge({ value }: { value: ValueObject }) {
  return <NumberToken text={formatValue(value)} type={value.type} />;
}

export function Legend() {
  return (
    <p className="legend" aria-label="Number colour legend">
      <span className="num num-fact">fact</span> reported or computed from reported values ·{" "}
      <span className="num num-estimate">estimate</span> a forecast ·{" "}
      <span className="num num-assumption">assumption</span> a chosen input ·{" "}
      <span className="chip chip-unverified">Unverified</span> failed verification ·{" "}
      <span className="chip chip-unchecked">Unchecked</span> not yet verified
    </p>
  );
}
