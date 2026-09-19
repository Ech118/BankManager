{# Full report template. Rendered by orchestrator/report/generator.py.

   Specified by docs/research-state.md and docs/adr/0004.

   Order is deliberate. The card comes FIRST: the original single-prompt design
   put the verdict last, after fifteen sections, which buried the answer the
   reader came for. The red team block sits immediately after the card, so the
   case against is visible before the supporting detail rather than after it.

   With no verdict (the run has not reached the synthesizer) this renders a
   PRELIMINARY report and no card. It never invents a verdict.
#}
# {% if card %}{{ card.company }} ({{ card.ticker }}){% else %}{{ ticker }} — preliminary research{% endif %}

> {{ disclaimer }}

{% if data_quality.overall != "ok" %}
**Data quality: {{ data_quality.overall }}**{% if data_quality.gaps %} — {{ data_quality.gaps | join("; ") }}{% endif %}

{% endif %}
{% if state.redacted %}
_This run was produced from anonymized filing text (backtest mode)._

{% endif %}
{% if card %}
## Verdict: {{ card.verdict | upper | replace("_", " ") }}

{{ card.thesis }}

| | 0-12m | 1-3y | 3-5y |
|---|---|---|---|
| Score (1-10) | {{ card.scores.short_term }} | {{ card.scores.medium_term }} | {{ card.scores.long_term }} |
| Expected return vs S&P 500 | {{ card.expected_return_vs_sp500.short_term | format_value }} | {{ card.expected_return_vs_sp500.medium_term | format_value }} | {{ card.expected_return_vs_sp500.long_term | format_value }} |

- **Price:** {{ card.price | format_value }} · **Market cap:** {{ card.market_cap | format_value }}
- **Probability of beating the S&P 500 over 3-5y:** {{ "%.0f" | format(card.p_beat_sp500_5y * 100) }}%
- **Expected 3-5y return:** {{ card.expected_5y_return | format_value }} · estimate
- **Primary catalyst:** {{ card.primary_catalyst }}
- **Biggest risk:** {{ card.biggest_risk }}
- **Valuation:** {{ card.valuation | replace("_", " ") }} · **Business quality:** {{ card.business_quality }} · **Financial strength:** {{ card.financial_strength }}

**$10,000 for five years:** {{ card.ten_thousand_dollar_answer.choice | replace("_", " ") }} — {{ card.ten_thousand_dollar_answer.reason }}

{% if scenario_result.weights.any_clamped %}
_One or more scenario weights proposed by the model were outside the permitted band and were adjusted by code. See the scenarios section._

{% endif %}
## The case against

{{ red_team.summary }}

**Response:** {{ red_team.responses_by_synthesizer }}

{% if red_team.drawdown_path %}
**Drawdown path:** {{ red_team.drawdown_path }}

{% endif %}
{% else %}
**Preliminary report.** The committee has not reached a verdict: the scenario, red team and synthesizer steps have not run for this analysis, so there is no score, probability or recommendation. What follows is the evidence gathered so far, as of {{ as_of }}.

{% endif %}
---

{% for section in sections %}
{{ section.body_markdown }}

{% endfor %}
---

{% if audit %}
{% if audit.claims_unverified %}
**{{ audit.claims_unverified }} claim(s) could not be verified** and are marked inline above.
{% else %}
Verification: {{ audit.claims_verified }} of {{ audit.claims_checked }} claims checked and verified.
{% endif %}
{% else %}
_Verification has not run for this report: claims are marked unchecked._
{% endif %}

> {{ disclaimer }}
