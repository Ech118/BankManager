"""Validate P3-produced artifacts against the FROZEN schemas in schema/ (read-only)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for p in SCHEMA_DIR.glob("*.json"):
        s = json.loads(p.read_text())
        resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIR / name).read_text()), registry=_registry())


def errors(obj: dict, schema_name: str) -> list[str]:
    errs = sorted(_validator(schema_name).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message[:200]}" for e in errs]


def check(obj: dict, schema_name: str) -> None:
    errs = errors(obj, schema_name)
    if errs:
        raise ValueError(f"{schema_name} invalid:\n  " + "\n  ".join(errs[:12]))
