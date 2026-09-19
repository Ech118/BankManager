/** The disclaimer. Rendered by the site shell on EVERY page, and by the report itself (error M). */
export const DISCLAIMER =
  "This is AI-generated research for educational purposes only. It is not investment advice or a recommendation to buy or sell any security.";

export function Disclaimer({ text = DISCLAIMER }: { text?: string }) {
  return (
    <aside className="disclaimer" role="note" aria-label="Disclaimer">
      {text}
    </aside>
  );
}
