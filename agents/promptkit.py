"""Prompt loading and rendering. Prompt text lives in prompts/*.md (one file per agent)."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_system(agent_prompt: str) -> str:
    """Shared rules + the agent's role. Stable across runs so it can be cached."""
    shared = (PROMPT_DIR / "_shared.md").read_text().strip()
    role = (PROMPT_DIR / agent_prompt).read_text().strip()
    return f"{shared}\n\n---\n\n{role}\n"


def block(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"
