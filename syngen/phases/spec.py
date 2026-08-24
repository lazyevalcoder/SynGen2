"""Phase 2: persona critique (lightweight) and simulator.json drafting."""
import json
from pathlib import Path

from syngen.config import ConfigError, validate_simulator_doc
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
                    log_fn=print, corrective_findings=None):
    spec_brief = (spec_notes or "none")[-1500:]
    if corrective_findings:
        spec_brief = (spec_brief + "\n\nCORRECTIVE FINDINGS - your previous "
                      "draft was invalid/uncalibrated. Fix ALL of these:\n"
                      + corrective_findings)[-2500:]
    system = load_prompt(
        "simulator_draft", story=story[:2000], criteria=criteria_summary,
        spec=spec_brief,
    )
    response = chat_json(client, "simulator_draft", system,
                         "Produce the simulator.json now.")
    doc = response
    try:
        validated = validate_simulator_doc(_validate_shape(doc))
    except ConfigError as e:
        # F19/F17 family: a schema-plausible draft can still be invalid
        # (share sums off, bad types). One deterministic repair attempt,
        # then one corrective re-draft; never crash the session here.
        log_fn(f"Draft invalid ({e}) - attempting deterministic repair.")
        try:
            from syngen.phases.preflight import _renormalize_product_shares_cfg
            _renormalize_product_shares_cfg(doc)
            validated = validate_simulator_doc(doc)
        except (ConfigError, Exception):
            log_fn("Repair failed - re-drafting with corrective findings.")
            return draft_simulator(client, story, criteria_summary,
                                   spec_notes, sim_path=sim_path,
                                   log_fn=log_fn,
                                   corrective_findings=str(e))

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
