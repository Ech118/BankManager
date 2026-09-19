{# Full report template. Rendered by orchestrator/report/generator.py.

   Specified by docs/research-state.md and docs/adr/0004.

   Order is deliberate. The card comes FIRST: the original single-prompt design
   put the verdict last, after fifteen sections, which buried the answer the
   reader came for. The red team block sits immediately after the card, so the
   case against is visible before the supporting detail rather than after it.

   TODO(roadmap Step 2, P3): wire this up.
#}
# {{ card.company }} ({{ card.ticker }})

> {{ disclaimer }}

{% if data_quality.overall != "ok" %}
**Data quality: {{ data_quality.overall }}** — {{ data_quality.gaps | join("; ") }}
{% endif %}
{% if state.redacted %}
_This run was produced from anonymized filing text (backtest mode)._
{% endif %}

## Verdict: {{ card.verdict | upper }}

{{ card.thesis }}

| | 0-12m | 1-3y | 3-5y |
|---|---|---|---|
| Score (1-10) | {{ card.scores.short_term }} | {{ card.scores.medium_term }} | {{ card.scores.long_term }} |
| Expected return vs S&P 500 | {{ card.expected_return_vs_sp500.short_term | format_value }} | {{ card.expected_return_vs_sp500.medium_term | format_value }} | {{ card.expected_return_vs_sp500.long_term | format_value }} |

- **P(beat S&P 500) over 3-5y:** {{ card.p_beat_sp500_5y }}
- **Primary catalyst:** {{ card.primary_catalyst }}
- **Biggest risk:** {{ card.biggest_risk }}
- **Valuation:** {{ card.valuation }} · **Business quality:** {{ card.business_quality }} · **Financial strength:** {{ card.financial_strength }}

**$10,000 today:** {{ card.ten_thousand_dollar_answer.choice }} — {{ card.ten_thousand_dollar_answer.reason }}

{% if scenario_result.weights.any_clamped %}
_One or more scenario weights proposed by the model were outside the permitted
band and were adjusted by code. See the scenarios section._
{% endif %}

## The case against

{{ red_team.summary }}

**Response:** {{ red_team.responses_by_synthesizer }}

{% if red_team.drawdown_path %}
**Drawdown path:** {{ red_team.drawdown_path }}
{% endif %}

---

{% for section in sections %}
{{ section.body_markdown }}
{% endfor %}

---

{% if audit.claims_unverified %}
**{{ audit.claims_unverified }} claim(s) could not be verified** and are marked
inline above.
{% endif %}

> {{ disclaimer }}
