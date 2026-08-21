"""Prompt library loader. Prompts are versioned .txt files in syngen/prompts/.
Template variables use {{name}} syntax (safe alongside JSON braces in prompts).
"""
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name, **substitutions):
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    text = path.read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", value)
    return text
