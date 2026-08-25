"""Prompt library loader (M6 P3).

Prompt fragments are domain vocabulary, so they live in the domain pack
(`packs/revops/prompts/`). Resolution order: pack dir first, then the
kernel dir (kept for future kernel-generic fragments). Template variables
use {{name}} syntax (safe alongside JSON braces in prompts).
"""
from pathlib import Path

_KERNEL_PROMPT_DIR = Path(__file__).parent / "prompts"
_PACK_PROMPT_DIR = Path(__file__).resolve().parents[1] / "packs" / "revops" / "prompts"


def _resolve(name):
    for base in (_PACK_PROMPT_DIR, _KERNEL_PROMPT_DIR):
        path = base / f"{name}.txt"
        if path.exists():
            return path
    return None


def load_prompt(name, **substitutions):
    path = _resolve(name)
    if path is None:
        raise FileNotFoundError(
            f"prompt not found in pack or kernel dirs: {name}")
    text = path.read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", value)
    return text
