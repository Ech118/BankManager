import type { DataQuality } from "@/lib/types";

/** Shown whenever data quality is not "ok". A degraded report must say so. */
export function DataQualityBanner({ quality }: { quality: DataQuality }) {
  if (quality.overall === "ok") return null;
  return (
    <div className={`banner banner-${quality.overall}`} role="alert">
      <strong>Data quality: {quality.overall}.</strong>
      {quality.gaps.length > 0 && (
        <ul>
          {quality.gaps.map((g, i) => (
            <li key={i}>{g}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
