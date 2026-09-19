{# Section template. Rendered by orchestrator/report/generator.py.

   Specified by docs/research-state.md and docs/adr/0004.

   Claims in, markdown out. Nothing here paraphrases: the agent's claim text is
   rendered as written, and every number is formatted from its ValueObject with
   its fact/estimate/assumption type preserved so the UI can colour it.

   Unverified claims are rendered WITH a marker rather than omitted. Claims the
   verifier has not seen say so. A reader must be able to tell a checked report
   from an unchecked one.
#}
## {{ section.title }}

{% for claim in section.claims %}
- {{ claim.text }}{% if claim.value %} ({{ claim.value | format_value }} · {{ claim.value | value_type }}){% endif %}{% if marker(claim.verification_status) %} {{ marker(claim.verification_status) }}{% endif %}{% if claim.fact_ids %} _[{{ claim.fact_ids | join(", ") }}]_{% endif %}

{% else %}
_No claims recorded for this section._

{% endfor %}
{% if evidence %}
### Evidence

{% for item in evidence %}
> {{ item.quote }}
> — `{{ item.source_id }}`

{% endfor %}
{% endif %}
