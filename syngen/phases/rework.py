"""Flexible stage-rework loop (P7): escalation evidence -> LLM judge ->
bounded re-dispatch back to criteria or config drafting.

The deterministic guards (coverage vs the original story claims, internal
consistency lint) remain the anti-goalpost floor: a criteria revision is only
accepted if it still expresses every original computable claim. The judge
decides WHERE the mistake lives; the guards decide whether a revision is
honest. Everything here fails OPEN to a terminal escalation - a judge or
redraft failure never fabricates a landing, it just ends the flight.
"""
import json

from syngen.phases.criteria_lint import lint_criteria_internal
from syngen.phases.intake import (authoring_guide, draft_criteria,
                                  enforce_coverage)
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt

ALLOWED_ACTIONS = ("rework_criteria", "rework_config", "escalate")


def make_evidence(kind, reason, doc, margins=None, detail=None):
    """Structured escalation evidence the judge can reason over."""
    return {
        "kind": kind,
        "reason": reason,
        "detail": detail,
        "criteria": [
            {"id": c.get("id"), "check": c.get("check"),
             "params": c.get("params"),
             "source_claim": c.get("source_claim")}
            for c in doc.get("criteria", [])
        ],
        "margins": margins or {},
    }


def criteria_lines(doc):
    return "\n".join(
        f"- {c['id']} check={c['check']} params={json.dumps(c['params'])}"
        for c in doc.get("criteria", [])
    )


def _normalize(verdict, doc):
    """Coerce a judge verdict into a safe shape; bad output degrades to
    escalate (the honest terminal). Scope must reference real criterion ids."""
    if not isinstance(verdict, dict):
        return {"action": "escalate", "scope": [],
                "guidance": "", "reason": "judge returned no verdict"}
    action = verdict.get("action")
    if action not in ALLOWED_ACTIONS:
        return {"action": "escalate", "scope": [],
                "guidance": "", "reason": f"judge returned invalid action {action!r}"}
    ids = {c.get("id") for c in doc.get("criteria", [])}
    scope = verdict.get("scope") or []
    if not isinstance(scope, list):
        scope = []
    scope = [s for s in scope if s in ids]
    return {
        "action": action,
        "scope": scope,
        "guidance": str(verdict.get("guidance", "")).strip(),
        "reason": str(verdict.get("reason", "")).strip(),
    }


def judge_revision(client, story, evidence, doc, round_no, log_fn=print):
    """One judge call: read the escalation evidence, route the next attempt.
    Fails OPEN to escalate (an unparseable/crashed judge never loops)."""
    system = load_prompt("rework_judge", authoring_guide=authoring_guide())
    user = (
        f"STORY:\n{story}\n\n"
        f"CURRENT CRITERIA:\n{criteria_lines(doc)}\n\n"
        f"ESCALATION EVIDENCE (round {round_no}):\n"
        f"kind: {evidence.get('kind')}\n"
        f"reason: {evidence.get('reason')}\n"
        + (f"detail: {evidence['detail']}\n" if evidence.get("detail") else "")
        + (f"worst margins: {json.dumps(evidence.get('margins', {}))}\n"
           if evidence.get("margins") else "")
        + "\nDecide the revision now."
    )
    try:
        verdict = chat_json(client, "rework_judge", system, user)
    except Exception as e:  # noqa: BLE001 - judge must fail open
        log_fn(f"Rework judge failed ({e}) - escalating.")
        return {"action": "escalate", "scope": [],
                "guidance": "", "reason": f"judge failure: {e}"}
    return _normalize(verdict, doc)


def redraft_criteria(client, story, doc, claims, decisions_text, guidance,
                     log_fn=print):
    """Claim-preserving criteria re-draft driven by judge guidance.

    Returns (doc, ok). The coverage guard re-runs against the ORIGINAL
    claims; dropping a claim is rejected (anti-goalpost). A re-draft that
    still fails internal consistency is also rejected. Both rejections
    return the unchanged doc with ok=False.
    """
    brief = (
        "REWORK - the previous attempt escalated because criteria misread "
        "the story or are unreachable. Re-draft the criteria so they still "
        "express EVERY computable claim in the story - do not drop or weaken "
        "any claim - but re-express it in a reachable, correct form.\n\n"
        + (guidance or "(no specific guidance - use the story claims).")
    )
    notes = brief if not decisions_text else decisions_text + "\n\n" + brief
    doc2 = draft_criteria(client, story, notes, log_fn=log_fn)
    doc2, cov = enforce_coverage(client, story, doc2, claims,
                                 decisions_text=decisions_text,
                                 log_fn=log_fn)
    if cov == "uncovered":
        log_fn("Rework criteria re-draft lost coverage of the original "
               "claims - rejected (goalpost guard).")
        return doc, False
    hard, _ = lint_criteria_internal(doc2)
    if hard:
        log_fn("Rework criteria re-draft still internally inconsistent - "
               "rejected.")
        return doc, False
    return doc2, True


def computable_claim_lines(claims):
    return [c.get("claim") for c in (claims or {}).get("claims", [])
            if c.get("classification") == "COMPUTABLE"]


def recover_criteria_consistency(client, story, doc, claims, decisions_text,
                                 findings, max_rounds, log_fn=print):
    """Gate-1 consistency recovery (P8 S25.4).

    The consistency lint is terminal after ONE corrective re-draft, so a
    conflicting set the drafter keeps producing dies at Gate 1 - before the
    delivery stage's rework loop can ever see it. Route it through the same
    bounded, claim-preserving judge loop. Returns (doc, ok, directives).
    """
    directives = []
    cur = doc
    cur_findings = list(findings)
    for rnd in range(max_rounds):
        evidence = make_evidence(
            "criteria_consistency",
            "conflicting criteria persisted past a corrective re-draft", cur,
            detail="; ".join(cur_findings)[:800])
        verdict = judge_revision(client, story, evidence, cur, rnd + 1,
                                 log_fn=log_fn)
        directives.append({
            "round": rnd + 1, "kind": "criteria_consistency",
            "action": verdict["action"], "scope": verdict["scope"],
            "reason": verdict["reason"], "guidance": verdict["guidance"]})
        if verdict["action"] != "rework_criteria":
            break
        new_doc, ok = redraft_criteria(client, story, cur, claims,
                                       decisions_text, verdict["guidance"],
                                       log_fn=log_fn)
        if not ok:
            break
        cur = new_doc
        cur_findings, _ = lint_criteria_internal(cur)
        if not cur_findings:
            return cur, True, directives
    return cur, False, directives
