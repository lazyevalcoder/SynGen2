"""The M2 vertical slice + M3 sessions: story in -> landed dataset out.

Orchestrator is a deterministic state machine (AGENT_ROLES); judgment lives in
named phases. I/O is injected so tests can run the whole flow offline.
"""
import json
from pathlib import Path

from syngen.config import load_criteria, load_json, validate_simulator_doc
from syngen.generator.engine import generate_to_workbook
from syngen.linter import has_blocking, lint, structure_findings
from syngen.phases.amend import (
    apply_amendments,
    apply_criterion_overrides,
    apply_structured_amendments,
    consistency_report,
    dependency_closure,
)
from syngen.phases.converge import LoopEscalation, run_convergence
from syngen.phases.diff import RoutingError, classify_story_change, validate_route
from syngen.phases.intake import (
    draft_criteria,
    enforce_coverage,
    precheck_claims,
)
from syngen.phases.spec import draft_simulator, persona_critique
from syngen.session import Session
from syngen.utils import set_at_path
from syngen.validator.checks import CHECKS
from syngen.validator.report import render_table, run_validation, to_report_dict


class ConsoleIO:
    """Interactive terminal I/O."""

    @staticmethod
    def _safe_print(text):
        """LLM output can contain any unicode; Windows consoles are cp1252."""
        try:
            print(text)
        except UnicodeEncodeError:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))

    def inform(self, text):
        self._safe_print(text)

    def confirm(self, prompt, default=True):
        suffix = " (Y/n)" if default else " (y/N)"
        answer = input(prompt + suffix + ": ").strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    def ask(self, prompt, default=""):
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer or default

    def free_text(self, prompt):
        print(prompt)
        lines = []
        while True:
            line = input("> ")
            if not line.strip():
                break
            lines.append(line)
        return "\n".join(lines)


def criteria_summary(doc):
    return "\n".join(
        f"{c['id']} {c['name']} params={json.dumps(c['params'])}"
        for c in doc["criteria"]
    )


def simulator_summary(cfg):
    acc = cfg.get("accounts", {})
    opp = cfg.get("opportunities", {})
    return (f"accounts: count={acc.get('count')}, "
            f"regions={json.dumps(acc.get('regions', {}))}, "
            f"segments={json.dumps(acc.get('segments', {}))}, "
            f"industries={acc.get('industries', [])}; "
            f"opportunities: {opp.get('per_quarter')}/quarter over "
            f"{len(cfg.get('time_model', {}).get('quarter_labels', []))} quarters")


TAXONOMY_CONTAINERS = {
    "accounts.segments": "segments",
    "accounts.regions": "regions",
}


def apply_taxonomy_edits(cfg, edits):
    """Apply categorical container edits; renormalize probability dicts to 1.0.

    Container-level replacements must be dicts of weights - live run 1 caught
    the LLM proposing a bare list, which would silently destroy the weights.
    Returns (cfg, applied, warnings).
    """
    applied, warnings = [], []
    for ch in edits or []:
        path = ch.get("path", "")
        value = ch.get("value")
        try:
            if path in TAXONOMY_CONTAINERS:
                dim = TAXONOMY_CONTAINERS[path]
                if not isinstance(value, dict) or not value:
                    warnings.append(
                        f"rejected edit '{path}': replacing the whole "
                        f"{dim} container requires a dict of weights")
                    continue
                # Live-M3 lesson #2: the classifier replaced the container
                # and silently RENAMED values (Enterprise -> ENT). Existing
                # values must survive a replacement; only additions and
                # weight changes are legitimate taxonomy edits.
                dropped = set(cfg["accounts"][dim]) - {str(k) for k in value}
                if dropped:
                    warnings.append(
                        f"rejected edit '{path}': it removes/renames "
                        f"existing values {sorted(dropped)}; propose one "
                        f"leaf-path addition per new value instead")
                    continue
                node = cfg["accounts"][dim]
                node.clear()
                node.update({str(k): float(v) for k, v in value.items()})
                applied.append({"path": path,
                                "from": f"<{len(node)} entries>",
                                "to": dict(node)})
            else:
                old = set_at_path(cfg, path, value)
                applied.append({"path": path, "from": old, "to": value})
        except (KeyError, IndexError, TypeError, ValueError) as e:
            warnings.append(f"could not apply edit {path}: {e}")

    # containers whose values are mixture weights must keep summing to 1
    # (numpy rejects p-sums off by >1e-8, so no rounding here)
    for dim in ("regions", "segments"):
        spec = cfg["accounts"].get(dim)
        if isinstance(spec, dict) and spec:
            total = sum(float(v) for v in spec.values())
            if abs(total - 1.0) > 1e-9:
                keys = list(spec)
                running = 0.0
                for k in keys[:-1]:
                    spec[k] = float(spec[k]) / total
                    running += spec[k]
                spec[keys[-1]] = 1.0 - running
                warnings.append(
                    f"accounts.{dim} weights rescaled to sum to 1.0 "
                    f"(was {total:.4f})")
    return cfg, applied, warnings


def gate_lint(io, session, sim_cfg, log):
    """Schema linter at Gate 1 (FR4). Blocking findings prevent generation.

    Clean draft  -> confirm to proceed; decline exits to manual editing.
    Blocked draft -> user may fix simulator.json on disk and reload.
    Returns sim_cfg to proceed with, or None for the manual-edit exit.
    """
    while True:
        findings = lint(sim_cfg)
        for rule, sev, msg in findings:
            marker = "BLOCK" if sev != "ADVISE" else "ADVISE"
            log(f"  LINT [{rule}/{sev}] {msg}")
        blocked = has_blocking(findings)
        session.write_artifact("simulator.json", json.dumps(sim_cfg, indent=2))
        if not blocked:
            if io.confirm("Accept simulator.json knobs and start generating?"):
                log("Lint gate passed.")
                return sim_cfg
            log("Edit session simulator.json manually, then re-run convergence.")
            return None
        if io.confirm("Draft is BLOCKED by lint rules. Edit simulator.json on "
                      "disk now and continue when done?", default=False):
            sim_cfg = validate_simulator_doc(load_json(
                session.root / "simulator.json"))
            continue
        log("Edit session simulator.json manually, then re-run convergence.")
        return None


def calibrate_gate(client, io, story, crit_summary, spec_notes, doc,
                   sim_cfg, session, log):
    """Pre-flight calibration (F17): deterministic config-vs-criteria
    cross-check before any iteration burns. HARD findings trigger one
    corrective re-draft; persistent HARD findings abort the session
    early with a precise reason instead of a doomed convergence loop.
    Returns (sim_cfg, status); sim_cfg None means abort."""
    from syngen.phases.preflight import (autocalibrate, calibrate,
                                         hard_findings, render_findings,
                                         repair_criteria)

    repairs = repair_criteria(sim_cfg, doc)
    if repairs:
        log("Repaired criteria deterministically:\n"
            + "\n".join(f"  - {x}" for x in repairs))
        session.log("## Criteria repair\n" + "\n".join(f"- {x}" for x in repairs))
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))

    def run_pass(cfg):
        return calibrate(cfg, doc)

    def evaluate(cfg):
        """Calibrate + deterministically auto-fix (ALWAYS - even a
        findings-free draft may be missing planning synthesis like
        attainment ratios or a required quota block)."""
        f = run_pass(cfg)
        fx = autocalibrate(cfg, doc)
        if fx:
            log("Auto-calibrated " + f"{len(fx)} item(s) deterministically:"
                + "\n" + "\n".join(f"  - {x}" for x in fx))
            session.log("## Auto-calibration\n" +
                        "\n".join(f"- {x}" for x in fx))
            (session.root / "simulator.json").write_text(
                json.dumps(cfg, indent=2), encoding="utf-8")
            f = run_pass(cfg)
        return f, fx

    findings, fixes = evaluate(sim_cfg)
    if not findings:
        return sim_cfg, ("autocalibrated" if fixes else "clean")
    log("Pre-flight calibration findings:\n" + render_findings(findings))
    session.log("## Pre-flight calibration\n```\n"
                + render_findings(findings) + "\n```")

    # Bounded corrective re-drafts (F17): the drafter converges on the
    # share/margin calculus across attempts (live s8c: 14pp -> 8pp miss
    # after one redraft). Keep drafting while HARD findings strictly
    # shrink; escalate the moment a draft fails to improve or the
    # budget is spent.
    max_redrafts = 3
    drafts_done = 0
    prev_hard_count = None
    while True:
        hard = hard_findings(findings)
        if not hard:
            if findings:
                log("Residual soft warnings:\n" + render_findings(findings))
            log("Pre-flight calibration passed.")
            session.log("PREFLIGHT passed "
                        f"({drafts_done} corrective re-drafts).")
            return sim_cfg, ("redrafted" if drafts_done else "soft_warnings")
        if prev_hard_count is not None and len(hard) >= prev_hard_count:
            log(f"HARD findings did not shrink ({len(hard)} >= "
                f"{prev_hard_count}) - escalating early.")
            session.log("PREFLIGHT FAILED: no improvement across "
                        "corrective drafts: " + json.dumps(hard))
            return None, "hard_findings_persist"
        if drafts_done >= max_redrafts:
            log("Corrective re-draft budget exhausted.")
            session.log("PREFLIGHT FAILED after re-draft budget: "
                        + json.dumps(hard))
            return None, "hard_findings_persist"
        log(f"{len(hard)} HARD finding(s) - corrective re-draft...")
        fix_notes = (spec_notes + "\n\nCORRECTIVE FINDINGS from pre-flight "
                     "calibration - fix ALL of these in the new draft:\n"
                     + render_findings(hard))
        sim_cfg = draft_simulator(client, story, crit_summary, fix_notes)
        doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
            zip(sim_cfg["time_model"]["quarter_labels"],
                sim_cfg["time_model"]["quarter_end_dates"]))
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        sim_cfg = gate_lint(io, session, sim_cfg, log)
        if sim_cfg is None:
            return None, "manual_edit"
        prev_hard_count = len(hard)
        drafts_done += 1
        findings, _ = evaluate(sim_cfg)
        log("Re-drafted calibration:\n" + render_findings(findings))


def post_generate_structure_gate(workbook_path, log, cfg=None):
    """Post-generation structural check (FR4): workbook must match the
    engine contract exactly (columns depend on optional config blocks)."""
    findings = structure_findings(workbook_path, cfg=cfg)
    for rule, sev, msg in findings:
        log(f"  STRUCTURE [{rule}/{sev}] {msg}")
    return not has_blocking(findings)


def run_new_story(client, story, io, sessions_dir="sessions", slug=None,
                  max_iterations=10, max_llm_proposals=8, use_personas=False):
    """use_personas defaults OFF: the M4 A/B (experiments/M4_persona_ab)
    found no measurable quality benefit and a consistent ~35s latency cost.
    Opt in when drafting unfamiliar domains where extra critique may help."""
    session = Session.create(sessions_dir, slug=slug or story[:40])
    log = io.inform
    session.save_story(story)
    log(f"Session: {session.root}")
    return _run_pipeline(session, client, io, story, log,
                         fresh_criteria=True,
                         max_iterations=max_iterations,
                         max_llm_proposals=max_llm_proposals,
                         use_personas=use_personas)


def run_resume(session_root, client, io, new_story=None,
               max_iterations=10, max_llm_proposals=8):
    """Return to an existing session: regenerate as-is, or classify a tweak."""
    session = Session.open(session_root)
    log = io.inform
    log(f"Resumed session: {session.root}")

    root = session.root
    criteria_path = root / "criteria.json"
    sim_path = root / "simulator.json"
    missing = [p.name for p in (criteria_path, sim_path) if not p.exists()]
    if missing:
        log(f"Session is incomplete; missing {missing}. Cannot resume - "
            "start a new session instead.")
        return {"status": "invalid_session"}

    if new_story is None:
        log("No new story given: regenerating from the existing config.")
        doc = load_criteria(criteria_path)
        return _converge_and_deliver(session, client, io, doc, sim_path, log,
                                     max_iterations, max_llm_proposals)

    # --- classify the tweak ---
    old_story = session.latest_story()
    if new_story.strip() == old_story.strip():
        # Live-M3 lesson: resubmitting identical text burned an LLM call and
        # created a redundant version just to hear "no diff".
        log("New story is identical to the latest version - "
            "treating as regenerate-as-is.")
        return _converge_and_deliver(session, client, io,
                                     load_criteria(criteria_path), sim_path,
                                     log, max_iterations, max_llm_proposals)
    n = session.save_story(new_story)
    log(f"Story saved as story.v{n}.md")
    doc = load_criteria(criteria_path)
    cfg = json.loads(sim_path.read_text(encoding="utf-8"))

    try:
        routed = classify_story_change(
            client, old_story, new_story,
            criteria_summary(doc), simulator_summary(cfg), log_fn=log)
    except (RoutingError, ValueError) as e:
        log(f"Classifier failed ({e}); escalating to structural.")
        routed = {"route": "structural", "notes": str(e)}
    try:
        routed = validate_route(routed, {c["id"] for c in doc["criteria"]})
    except RoutingError as e:
        log(f"Routing guardrails rejected the proposal ({e}); "
            "treating as structural.")
        routed = {"route": "structural", "notes": str(e)}

    route = routed["route"]
    session.write_artifact("story_diff.json", json.dumps(routed, indent=2))
    session.log(f"## Story diff v{n}: route={route}\n"
                f"```json\n{json.dumps(routed, indent=2)}\n```")

    if route == "structural":
        reason = routed.get("notes") or "new entities/behaviors required"
        session.log(f"RESUME escalated: structural ({reason})")
        log("\nSTRUCTURAL CHANGE: the current data model cannot express this. "
            "Start a fresh session ('syngen new'); carry over what you need.")
        return {"status": "escalated", "reason": "structural",
                "detail": reason, "session": str(root)}

    if route == "taxonomy":
        cfg, applied, warns = apply_taxonomy_edits(
            cfg, routed.get("proposed_config_edits", []))
        for w in warns:
            log(f"  NOTE {w}")
        change_str = "\n".join(
            f"  {a['path']}: {a['from']} -> {a['to']}" for a in applied)
        log(f"Taxonomy edits:\n{change_str}")
        if not applied or not io.confirm("Apply these taxonomy edits?"):
            log("Aborted at taxonomy review.")
            return {"status": "aborted", "where": "taxonomy_review"}
        sim_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    else:  # parametric
        amendments = routed.get("proposed_criteria_amendments", []) or []
        doc, applied, errors = apply_structured_amendments(doc, amendments)
        for e in errors:
            log(f"WARN unusable amendment skipped: {json.dumps(e)}")
        changed_ids = sorted({a["id"] for a in applied})
        affected = dependency_closure(doc["criteria"], changed_ids) \
            if changed_ids else []
        _print_criteria(io, doc)
        if applied:
            log("Amended: " + ", ".join(changed_ids))
            if affected:
                log(f"Dependency propagation: {', '.join(affected)} also "
                    "affected - re-review above before signing off.")
            log("Dependency edges:\n" + consistency_report(doc))
        if not io.confirm("Sign off amended criteria?", default=True):
            log("Aborted at Gate 1 re-approval.")
            return {"status": "aborted", "where": "gate1_reapproval"}
        session.log("GATE 1 re-approval passed after amendment.")
        criteria_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    return _converge_and_deliver(session, client, io, doc, sim_path, log,
                                 max_iterations, max_llm_proposals)


def _converge_and_deliver(session, client, io, doc, sim_path, log,
                          max_iterations, max_llm_proposals):
    """Shared tail of both flows: converge, structure-gate, deliver."""
    criteria_path = session.root / "criteria.json"
    try:
        summary = run_convergence(session, client, sim_path, criteria_path,
                                  max_iterations=max_iterations,
                                  max_llm_proposals=max_llm_proposals,
                                  log_fn=log)
    except LoopEscalation as esc:
        session.log(f"ESCALATED: {esc.reason}")
        log(f"\nNEEDS YOUR ATTENTION: {esc.reason}")
        return {"status": "escalated", "reason": esc.reason,
                "session": str(session.root)}

    sim_cfg = load_json(sim_path) if not isinstance(sim_path, dict) else sim_path
    if not post_generate_structure_gate(summary["workbook"], log, cfg=sim_cfg):
        session.log("STRUCTURE GATE FAILED")
        return {"status": "structure_check_failed",
                "workbook": summary["workbook"]}

    results, all_pass = run_validation_final(summary, criteria_path)
    report_md = render_table(results, all_pass) if all_pass else "(see log)"
    session.write_artifact("validation_report.md", f"```\n{report_md}\n```\n")
    session.log("GATE 2 passed: delivered.")
    log(f"\nDeliverables in {session.root}")
    log(f"  dataset:   {summary['workbook']}")
    log(f"  proof:     validation_report.md")
    log(f"  config:    simulator.json (tweak knobs anytime, regenerate)")
    if summary.get("thin_margins"):
        log(f"  note: thin margins on {', '.join(summary['thin_margins'])}")
    if not io.confirm("Inspect and accept delivery?", default=True):
        return {"status": "delivered_unaccepted", "session": str(session.root)}
    return {"status": "converged", "session": str(session.root),
            "iterations": summary["iterations"],
            "llm_proposals": summary["llm_proposals"],
            "thin_margins": summary["thin_margins"]}


def _run_pipeline(session, client, io, story, log, fresh_criteria=True,
                  max_iterations=10, max_llm_proposals=8, use_personas=True):
    """Fresh-story flow: pre-check, Gate 1, personas+draft, converge, deliver."""

    # --- Pre-check ---
    claims = precheck_claims(client, story, log_fn=log)
    for c in claims.get("claims", []):
        marker = "+" if c.get("classification") == "COMPUTABLE" else "-"
        log(f"  [{marker}] {c.get('claim')} - {c.get('note', '')[:90]}")
    for q in claims.get("questions_for_user", []):
        log(f"  ? {q}")
    if not io.confirm("Proceed with the computable claims above?"):
        log("Aborted at pre-check.")
        return {"status": "aborted", "where": "precheck"}

    # --- Gate 1: decompose + negotiate ---
    decisions_text = io.free_text(
        "Answer any pre-check questions now (blank line to finish), "
        "or leave empty:"
    )
    doc = draft_criteria(client, story, decisions_text)

    # --- Coverage guard (M5 iter 5, R6): vacuous criteria never converge ---
    doc, cov_status = enforce_coverage(client, story, doc, claims,
                                       decisions_text=decisions_text,
                                       log_fn=log)
    if cov_status == "uncovered":
        session.log("ESCALATED: criteria_coverage - drafted criteria do not "
                    "express the story's computable claims.")
        log("\nNEEDS YOUR ATTENTION: the drafted criteria express none of "
            "the story's computable claims (even after a corrective "
            "re-draft). Review/extend criteria.json manually or re-run.")
        return {"status": "escalated", "reason": "criteria_coverage",
                "session": str(session.root)}
    if cov_status == "redrafted":
        session.log("COVERAGE GUARD: criteria re-drafted to cover the "
                    "story's claims.")

    deps_note = consistency_report(doc).strip()
    if deps_note != "(no dependencies declared)":
        log("Declared dependencies:\n" + deps_note)
    _print_criteria(io, doc)

    overrides = ""
    while not io.confirm("Sign off these criteria?", default=True):
        overrides = io.ask("Overrides (e.g. AC3.target_pct=21, AC6.min_gap_pp=4)")
        try:
            doc, changed, affected = apply_amendments(doc, overrides)
            _print_criteria(io, doc)
            if affected:
                log(f"Dependency propagation: {', '.join(affected)} depend(s) "
                    f"on {', '.join(changed)} - re-review above before "
                    "signing off.")
        except ValueError as e:
            log(f"Could not apply override: {e}")

    criteria_path = session.write_artifact(
        "criteria.json", json.dumps(doc, indent=2))
    session.log("GATE 1 passed: criteria signed off.")
    log("Gate 1 passed.")

    # --- Phase 2: personas (lightweight) + simulator draft ---
    crit_summary = criteria_summary(doc)
    if use_personas:
        critique = persona_critique(client, story, crit_summary, log_fn=log)
        spec_lines = []
        for persona in ("domain_expert", "bi_engineer", "outsider"):
            for bullet in critique.get(persona, [])[:5]:
                spec_lines.append(f"- [{persona}] {bullet}")
    else:
        # A/B arm (G1): measure what the persona pass actually contributes
        log("Personas SKIPPED (A/B control arm)")
        spec_lines = []
    conflict_notes = io.free_text(
        "Resolve flagged conflicts (one per line, blank to finish):"
    )
    spec_notes = ("\n".join(spec_lines)
                  + f"\n\nUser resolutions:\n{conflict_notes}").strip()
    session.write_artifact("spec.md", f"# Data Spec\n\n{spec_notes or 'none'}\n")

    sim_cfg = draft_simulator(client, story, crit_summary, spec_notes)

    # Calendar flows from the generator's config into criteria so validation
    # stays consistent with what the engine actually generated (live-smoke bug).
    doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
        zip(sim_cfg["time_model"]["quarter_labels"],
            sim_cfg["time_model"]["quarter_end_dates"])
    )
    session.write_artifact("criteria.json", json.dumps(doc, indent=2))

    # --- Schema lint gate (FR4) ---
    sim_cfg = gate_lint(io, session, sim_cfg, log)
    if sim_cfg is None:
        return {"status": "manual_edit", "session": str(session.root)}

    # --- Pre-flight calibration gate (F17) ---
    sim_cfg, status = calibrate_gate(client, io, story, crit_summary,
                                     spec_notes, doc, sim_cfg, session, log)
    if sim_cfg is None:
        return {"status": "escalated", "reason": "preflight_calibration",
                "session": str(session.root)}

    return _converge_and_deliver(session, client, io, doc,
                                 session.root / "simulator.json", log,
                                 max_iterations, max_llm_proposals)


def run_validation_final(summary, criteria_path):
    wb = Path(summary["workbook"])
    return run_validation(wb, criteria_path)


def _print_criteria(io, doc):
    rows = []
    for c in doc["criteria"]:
        check_ok = c["check"] in CHECKS
        known = "" if check_ok else " [UNKNOWN CHECK]"
        depends = c.get("depends_on") or []
        dep_note = f" (depends_on: {', '.join(depends)})" if depends else ""
        rows.append(f"  {c['id']}  {c['name']}{known}{dep_note}\n"
                    f"       check={c['check']} params={json.dumps(c['params'])}")
    io.inform("\n".join(rows))
