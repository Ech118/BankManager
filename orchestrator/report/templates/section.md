{# Section template. Rendered by orchestrator/report/generator.py.

   Specified by docs/research-state.md and docs/adr/0004.

   Claims in, markdown out. Nothing here paraphrases: the agent's claim text is
   rendered as written, and every number is formatted from its ValueObject with
   its fact/estimate/assumption type preserved so the UI can colour it.

   Unverified claims are rendered WITH a marker rather than omitted. A reader
   must be able to tell a checked report from an unchecked one.

   TODO(roadmap Step 2, P3): wire this up.
#}
## {{ section.title }}

{% for claim in section.claims %}
- {{ claim.text }}
  {%- if claim.value %} ({{ claim.value | format_value }}){% endif %}
  {%- if claim.verification_status == "unverified" %} **[UNVERIFIED]**{% endif %}
  {%- if claim.fact_ids %} _[{{ claim.fact_ids | join(", ") }}]_{% endif %}
{% endfor %}

{% if section.evidence %}
### Evidence
{% for item in section.evidence %}
> {{ item.quote }}
> — `{{ item.source_id }}`
{% endfor %}
{% endif %}
