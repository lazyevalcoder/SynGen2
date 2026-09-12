"""Stage 2, split: pick the claim form, then fill params, then assemble (P11).

The classic stage 2 asks one prompt (story + generated catalog + capability
sheet) for the whole criteria JSON. Here:
  2a `select_claim_forms`  - map each computable claim to ONE menu check;
  2b `fill_criteria_params` - fill target/tolerance for the chosen checks;
  2c `assemble`             - merge + validate in code (the caller then runs
                             the existing coverage/consistency guards).

The menu is the enforcement layer: a blocked check is dropped before it can
become a criterion.
"""
import json

from syngen.config import validate_criteria_doc
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt


def _tax():
    from syngen.phases.intake import _pack_taxonomy
    return _pack_taxonomy()


def computable_claims(claims):
    return [c.get("claim") for c in (claims or {}).get("claims", [])
            if c.get("classification") == "COMPUTABLE"]


def select_claim_forms(client, story, claims, decisions_text="", log_fn=print):
    """2a: one small call mapping claims -> buildable checks."""
    from syngen.menu import menu_text
    computable = computable_claims(claims)
    if not computable:
        return {"forms": []}
    system = load_prompt("claim_forms", menu=menu_text(),
                         user_decisions=decisions_text or "none", story=story)
    user = ("COMPUTABLE CLAIMS:\n"
            + "\n".join(f"- {c}" for c in computable)
            + "\n\nReturn the claim->check mapping now.")
    try:
        result = chat_json(client, "claim_forms", system, user)
    except Exception as e:  # noqa: BLE001 - caller falls back to classic
        log_fn(f"Stage 2a form selection failed ({e}).")
        return {"forms": []}
    forms = result.get("forms") if isinstance(result, dict) else None
    return {"forms": forms if isinstance(forms, list) else []}


def fill_criteria_params(client, story, forms, decisions_text="", log_fn=print,
                         corrective=""):
    """2b: one call filling params for the selected checks."""
    from syngen.menu import engine_limits_for
    checks = sorted({f.get("check") for f in forms
                     if isinstance(f, dict) and f.get("check")})
    facts = _tax().check_facts(checks) or "(none registered)"
    limits = engine_limits_for(checks) or "(none)"
    system = load_prompt("criterion_params", check_facts=facts,
                         engine_limits=limits,
                         forms=json.dumps(forms, indent=2),
                         user_decisions=decisions_text or "none", story=story)
    if corrective:
        system += "\n\nCORRECTIVE FINDINGS - fix ALL of these:\n" + corrective
    return chat_json(client, "criterion_params", system,
                     "Produce the criteria JSON now.")


def _to_doc(result):
    from syngen.config import validate_criteria_doc
    from syngen.phases.intake import _as_criteria_doc
    return validate_criteria_doc(_as_criteria_doc(result))


def _dedupe(doc, log_fn):
    """Drop EXACT duplicate criteria (same check, params and source claim)."""
    seen, out = set(), []
    for c in doc.get("criteria", []):
        key = (c.get("check"),
               json.dumps(c.get("params"), sort_keys=True),
               c.get("source_claim"))
        if key in seen:
            log_fn(f"Stage 2 split: dropped exact duplicate {c.get('id')}.")
            continue
        seen.add(key)
        out.append(c)
    return {**doc, "criteria": out}


def draft_criteria_split(client, story, claims, decisions_text="", log_fn=print):
    """2a + 2b + 2c. Returns a validated criteria doc, or None to fall back
    to the classic single-prompt path."""
    from syngen.menu import is_blocked
    selected = select_claim_forms(client, story, claims, decisions_text,
                                  log_fn=log_fn)
    forms, dropped = [], []
    for f in selected.get("forms", []):
        check = f.get("check") if isinstance(f, dict) else None
        if not check or is_blocked(check):
            dropped.append(check or f)
            continue
        forms.append(f)
    if dropped:
        log_fn(f"Menu: dropped non-buildable form(s): {dropped}")
    if not forms:
        log_fn("Stage 2 split: no buildable forms selected.")
        return None

    try:
        doc = _to_doc(fill_criteria_params(client, story, forms, decisions_text,
                                           log_fn=log_fn))
    except (ValueError, KeyError) as e:
        log_fn(f"Stage 2 split: param fill unparseable ({e}).")
        return None

    # 2c guard: the number-filling step may only use the mapped forms.
    allowed = {f["check"] for f in forms}
    bad = [c for c in doc["criteria"] if c.get("check") not in allowed]
    if bad:
        log_fn(f"Stage 2 split: {len(bad)} criterion(s) used a check outside "
               "the mapped forms - one re-draft.")
        corrective = ("These checks are NOT allowed (use ONLY the mapped "
                      "forms): " + ", ".join(sorted({c.get('check') for c in bad}))
                      + ". Allowed checks: " + ", ".join(sorted(allowed)) + ".")
        try:
            doc = _to_doc(fill_criteria_params(client, story, forms,
                                              decisions_text, log_fn=log_fn,
                                              corrective=corrective))
        except (ValueError, KeyError) as e:
            log_fn(f"Stage 2 split: corrective param fill unparseable ({e}).")
            return None

    doc = _dedupe(doc, log_fn)
    log_fn(f"Stage 2 split drafted {len(doc['criteria'])} criteria from "
           f"{len(forms)} form(s): " + ", ".join(c["id"] for c in doc["criteria"]))
    return doc
