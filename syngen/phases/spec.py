"""Phase 2: persona critique (lightweight) and simulator.json drafting."""
import json
from pathlib import Path

from syngen.config import validate_simulator_doc
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt
from syngen.utils import extract_json


def persona_critique(client, story, criteria_summary, log_fn=print):
    """Lightweight single-call persona pass. Formal A/B is M4 scope (gap G1)."""
    system = load_prompt("persona_critique")
    user = f"Story:\n{story}\n\nAcceptance criteria:\n{criteria_summary}"
    critique = chat_json(client, "personas", system, user)
    n_conflicts = len(critique.get("conflicts", []))
    log_fn(f"Persona critique: {n_conflicts} conflict(s) flagged")
    return critique


def draft_simulator(client, story, criteria_summary, spec_notes="", sim_path=None,
                    log_fn=print):
    spec_brief = (spec_notes or "none")[-1500:]
    system = load_prompt(
        "simulator_draft", story=story[:2000], criteria=criteria_summary,
        spec=spec_brief,
    )
    response = chat_json(client, "simulator_draft", system,
                         "Produce the simulator.json now.")
    doc = response
    validated = validate_simulator_doc(_validate_shape(doc))

    if sim_path:
        Path(sim_path).write_text(json.dumps(validated, indent=2), encoding="utf-8")

    n_quarters = len(validated["time_model"]["quarter_labels"])
    log_fn(f"Drafted simulator.json: {validated['accounts']['count']} accounts, "
           f"{validated['opportunities']['per_quarter']}/qtr x {n_quarters} quarters, "
           f"seed {validated['seed']}")
    return validated


def _validate_shape(doc):
    """load_simulator enforces keys; this normalizes minor LLM deviations."""
    if not isinstance(doc, dict):
        raise ValueError("simulator draft is not a JSON object")
    return doc
