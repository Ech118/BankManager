"""Test helpers: build a Ctx from the ACME mock and script LLM behaviour."""
import copy

from agents.llm import MockLLM, Usage
from agents.refs import build_index
from agents.runner import Ctx
from calc import api as calc
from data import api as data
from orchestrator.pipeline import build_docs


def make_ctx() -> Ctx:
    fs = data.build_factsheet("ACME")
    metrics = calc.compute_metrics(fs)
    docs, _, _ = build_docs(fs, data.get_section_text, None, 60_000)
    return Ctx("ACME", fs["as_of"], fs, metrics, build_index(fs, metrics), docs)


class ScriptedLLM:
    """Calls fn(kwargs) -> dict (or (dict, Usage)); records every call."""

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def complete_json(self, **kw):
        self.calls.append(kw)
        out = self.fn(kw)
        return out if isinstance(out, tuple) else (out, Usage(model="mock", calls=1))


class SpyMock(MockLLM):
    """MockLLM that records prompts and can post-edit each agent's output."""

    def __init__(self, edit=None):
        self.calls, self.edit = [], edit

    def complete_json(self, **kw):
        self.calls.append(kw)
        data_, usage = super().complete_json(**kw)
        if self.edit:
            data_ = self.edit(kw["agent"], copy.deepcopy(data_)) or data_
        return data_, usage


MDNA_QUOTE = "Gross margin improved to 40.0% from 38.9%"


def good_finding(section="financial_quality", refs=None, ctx=None, quote=MDNA_QUOTE):
    sid = ctx.docs["mdna"].source_id if ctx else "src:edgar:0001234567-26-000010:mdna"
    return {"claim": "Gross margin expanded on price and mix.", "trend": "temporarily_positive",
            "section": section, "evidence": [{"quote": quote, "source_id": sid}],
            "number_refs": refs or [], "confidence": "medium"}
