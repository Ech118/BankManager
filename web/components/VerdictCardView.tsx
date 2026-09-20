import { HORIZON_LABELS, type VerdictCard } from "@/lib/types";
import { humanize, stripMock } from "@/lib/format";
import { NumberBadge } from "./NumberBadge";

const TONE: Record<string, string> = {
  strong_buy: "good",
  buy: "good",
  speculative_buy: "warn",
  hold: "neutral",
  avoid: "bad",
  sell: "bad",
};

const CIRC = 2 * Math.PI * 36;

/** The answer, first. Every number on it comes from calc or the market snapshot, never from the model. */
export function VerdictCardView({ card }: { card: VerdictCard }) {
  const horizons = ["short_term", "medium_term", "long_term"] as const;
  const answer = card.ten_thousand_dollar_answer;
  return (
    <section className="card" aria-labelledby="verdict-heading">
      <div className="card-top">
        <div>
          <h2 id="verdict-heading" className="company">
            {stripMock(card.company)} <span className="ticker">{card.ticker}</span>
          </h2>
          <p className="quote-line">
            Price <NumberBadge value={card.price} /> · Market cap <NumberBadge value={card.market_cap} />
          </p>
        </div>
        <div className={`verdict verdict-${TONE[card.verdict] ?? "neutral"}`} data-testid="verdict-word">
          {humanize(card.verdict)}
        </div>
      </div>

      <p className="thesis">{card.thesis}</p>

      <table className="horizons">
        <thead>
          <tr>
            <th scope="col" />
            {horizons.map((h) => (
              <th scope="col" key={h}>
                {HORIZON_LABELS[h]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Score (1-10)</th>
            {horizons.map((h) => (
              <td key={h}>
                <span className="score">{card.scores[h]}</span>
                <span className="score-bar" aria-hidden="true">
                  <span style={{ width: `${Math.max(0, Math.min(10, card.scores[h])) * 10}%` }} />
                </span>
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Expected return vs S&amp;P 500</th>
            {horizons.map((h) => (
              <td key={h}>
                <NumberBadge value={card.expected_return_vs_sp500[h]} />
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      <div className="hero-stats">
        <div className="gauge">
          <svg viewBox="0 0 84 84" aria-hidden="true">
            <circle className="gauge-track" cx="42" cy="42" r="36" fill="none" strokeWidth="8" />
            <circle
              className="gauge-fill"
              cx="42"
              cy="42"
              r="36"
              fill="none"
              strokeWidth="8"
              strokeDasharray={CIRC}
              strokeDashoffset={CIRC * (1 - Math.max(0, Math.min(1, card.p_beat_sp500_5y)))}
            />
          </svg>
          <div>
            <div className="gauge-value">{Math.round(card.p_beat_sp500_5y * 100)}%</div>
            <div className="gauge-label">Probability of beating the S&amp;P 500 (3-5y)</div>
          </div>
        </div>
        <dl className="facts">
          <div>
            <dt>Expected 3-5y return</dt>
            <dd>
              <NumberBadge value={card.expected_5y_return} />
            </dd>
          </div>
          <div className="catalyst">
            <dt>Primary catalyst</dt>
            <dd>{card.primary_catalyst}</dd>
          </div>
          <div className="risk">
            <dt>Biggest risk</dt>
            <dd>{card.biggest_risk}</dd>
          </div>
        </dl>
      </div>

      <p className="tags">
        <span className="tag">Valuation: {humanize(card.valuation)}</span>
        <span className="tag">Business quality: {card.business_quality}</span>
        <span className="tag">Financial strength: {card.financial_strength}</span>
      </p>

      <p className="ten-k">
        <strong>$10,000 for five years:</strong> {answer.choice === "this_stock" ? "this stock" : "the S&P 500"}. {answer.reason}
      </p>
    </section>
  );
}
