"""Phase 1: story pre-check and decomposition into acceptance criteria."""
import json
from pathlib import Path

from syngen.config import validate_criteria_doc
from syngen.llm.profiles import chat_task
from syngen.prompts import load_prompt
from syngen.utils import extract_json


def precheck_claims(client, story, log_fn=print):
    system = load_prompt("precheck")
    response = chat_task(client, "precheck", system, story)
    claims = extract_json(response.content)
    log_fn(f"Pre-check found {len(claims.get('claims', []))} claims; "
           f"{len(claims.get('questions_for_user', []))} question(s) for user")
    return claims


def draft_criteria(client, story, decisions_text="", criteria_path=None, log_fn=print):
    """LLM drafts criteria JSON; contract validation rejects malformed output."""
    system = load_prompt("decompose", user_decisions=decisions_text or "none", story=story)
    response = chat_task(client, "decompose", system, "Produce the criteria JSON now.")
    doc = extract_json(response.content)

    if criteria_path:
        Path(criteria_path).write_text(json.dumps(doc, indent=2), encoding="utf-8")

    validated = validate_criteria_doc(_as_criteria_doc(doc))
    log_fn(f"Drafted {len(validated['criteria'])} criteria: "
           + ", ".join(c["id"] for c in validated["criteria"]))
    return validated


def _as_criteria_doc(doc):
    """Accept both full-document and nested {'criteria': [...]} LLM shapes."""
    if "criteria" in doc and isinstance(doc["criteria"], list):
        return {
            "definitions": doc.get("definitions", {}),
            "criteria": doc["criteria"],
        }
    raise ValueError("LLM output missing 'criteria' list")
