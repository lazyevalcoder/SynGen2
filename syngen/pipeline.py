"""The M2 vertical slice: story in -> landed dataset out, two human gates.

Orchestrator is a deterministic state machine (AGENT_ROLES); judgment lives in
named phases. I/O is injected so tests can run the whole flow offline.
"""
import json
from pathlib import Path

from syngen.config import load_criteria
from syngen.generator.engine import generate_to_workbook
from syngen.phases.converge import LoopEscalation, run_convergence
from syngen.phases.intake import draft_criteria, precheck_claims
from syngen.phases.spec import draft_simulator, persona_critique
from syngen.session import Session
from syngen.validator.checks import CHECKS
from syngen.validator.report import render_table


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


def apply_criterion_overrides(doc, override_text):
    """Parse 'AC3.target_pct=21; AC6.min_gap_pp=4' style overrides into the doc."""
    for chunk in override_text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        assignment, _, value = chunk.partition("=")
        crit_id, _, param = assignment.strip().partition(".")
        value = float(value) if "." in value else int(value)
        for c in doc["criteria"]:
            if c["id"] == crit_id.strip():
                c["params"][param.strip()] = value
                break
        else:
            raise ValueError(f"unknown criterion id in override: {crit_id}")
    return doc


def run_new_story(client, story, io, sessions_dir="sessions", slug=None,
                  max_iterations=10, max_llm_proposals=5):
    session = Session.create(sessions_dir, slug=slug or story[:40])
    log = io.inform
    session.log(f"# Story\n{story}\n")
    log(f"Session: {session.root}")

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
    _print_criteria(io, doc)

    overrides = ""
    while not io.confirm("Sign off these criteria?", default=True):
        overrides = io.ask("Overrides (e.g. AC3.target_pct=21, AC6.min_gap_pp=4)")
        try:
            doc = apply_criterion_overrides(doc, overrides)
            _print_criteria(io, doc)
        except ValueError as e:
            log(f"Could not apply override: {e}")

    criteria_path = session.write_artifact(
        "criteria.json", json.dumps(doc, indent=2))
    session.log("GATE 1 passed: criteria signed off.")
    log("Gate 1 passed.")

    # --- Phase 2: personas (lightweight) + simulator draft ---
    crit_summary = "\n".join(
        f"{c['id']} {c['name']} params={json.dumps(c['params'])}"
        for c in doc["criteria"]
    )
    critique = persona_critique(client, story, crit_summary, log_fn=log)
    spec_lines = []
    for persona in ("domain_expert", "bi_engineer", "outsider"):
        for bullet in critique.get(persona, [])[:5]:
            spec_lines.append(f"- [{persona}] {bullet}")
    conflict_notes = io.free_text(
        "Resolve flagged conflicts (one per line, blank to finish):"
    )
    spec_notes = "\n".join(spec_lines) + f"\n\nUser resolutions:\n{conflict_notes}"
    session.write_artifact("spec.md", f"# Data Spec\n\n{spec_notes}\n")

    sim_cfg = draft_simulator(client, story, crit_summary, spec_notes)
    if not io.confirm("Accept simulator.json knobs and start generating?"):
        log("Edit session simulator.json manually, then re-run convergence.")
    sim_path = session.write_artifact("simulator.json",
                                      json.dumps(sim_cfg, indent=2))

    # Calendar flows from the generator's config into criteria so validation
    # stays consistent with what the engine actually generated (live-smoke bug).
    doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
        zip(sim_cfg["time_model"]["quarter_labels"],
            sim_cfg["time_model"]["quarter_end_dates"])
    )
    criteria_path = session.write_artifact(
        "criteria.json", json.dumps(doc, indent=2))

    # --- Phase 4: converge ---
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

    # --- Gate 2 ---
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


def run_validation_final(summary, criteria_path):
    from syngen.validator.report import run_validation as rv
    wb = Path(summary["workbook"])
    return rv(wb, criteria_path)


def _print_criteria(io, doc):
    rows = []
    for c in doc["criteria"]:
        check_ok = c["check"] in CHECKS
        known = "" if check_ok else " [UNKNOWN CHECK]"
        rows.append(f"  {c['id']}  {c['name']}{known}\n"
                    f"       check={c['check']} params={json.dumps(c['params'])}")
    io.inform("\n".join(rows))
