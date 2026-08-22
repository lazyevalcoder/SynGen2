"""Phase 4: the convergence loop (Experiment D, automated with guardrails)."""
import json
from pathlib import Path

from syngen.generator.engine import generate_to_workbook
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt
from syngen.utils import extract_json, get_at_path, set_at_path
from syngen.validator.report import render_table, run_validation, to_report_dict


class LoopEscalation(Exception):
    def __init__(self, reason, results, history):
        super().__init__(reason)
        self.reason = reason
        self.results = results
        self.history = history


def _apply_changes(cfg, changes):
    applied = []
    for ch in changes:
        path = ch.get("path", "")
        try:
            old = get_at_path(cfg, path)
            set_at_path(cfg, path, ch.get("to"))
            applied.append({"path": path, "from": old, "to": ch.get("to"),
                            "predicted_effect": ch.get("predicted_effect", "")})
        except (KeyError, IndexError, TypeError) as e:
            applied.append({"path": path, "error": f"could not apply: {e}"})
    return applied


def propose_knobs(client, simulator_cfg, results, history_lines):
    system = load_prompt(
        "knob_proposal",
        validation_results=render_table(results, all_pass=False),
        iteration_history="\n".join(history_lines) or "none yet",
        simulator_json=json.dumps(simulator_cfg, indent=2),
    )
    response = chat_json(client, "knob_proposal", system,
                         "Propose the next knob changes as JSON.")
    return response


def run_convergence(session, client, sim_path, criteria_path,
                    max_iterations=10, max_llm_proposals=5, log_fn=print):
    """Generate -> validate -> propose -> patch until story lands.

    Guardrails: hard iteration cap; LLM proposal cap; escalates via
    LoopEscalation when stuck. Returns summary dict on success.
    """
    cfg = json.loads(Path(sim_path).read_text(encoding="utf-8"))
    workbook_path = Path(cfg["output"]["workbook"])
    if not workbook_path.is_absolute():
        workbook_path = Path(sim_path).parent / workbook_path
    # Live-M3 bug: generate_to_workbook writes to cfg's relative path from
    # CWD, silently bypassing the session folder. Pin the resolved absolute
    # path so the workbook always lands in <session>/output/ (contracts §8).
    cfg = {**cfg, "output": {**cfg["output"], "workbook": str(workbook_path)}}

    history_lines = []
    llm_proposals = 0

    for iteration in range(1, max_iterations + 1):
        _, wb = generate_to_workbook(cfg)
        results, all_pass = run_validation(wb, criteria_path)
        table = render_table(results, all_pass)
        log_fn(f"--- Iteration {iteration} ---\n{table}")
        session.log(f"## Iteration {iteration}\n```\n{table}\n```")
        # history/ is append-only: the exact config + report that produced
        # this iteration's workbook (contracts section 8)
        session.archive_iteration(
            iteration, json.dumps(cfg, indent=2),
            json.dumps(to_report_dict(results, all_pass, str(wb)), indent=2))

        if all_pass:
            margins = {r["id"]: r["margin"] for r in results}
            thin = [i for i, m in margins.items() if m is not None and m < 0.5]
            summary = {
                "status": "converged",
                "iterations": iteration,
                "llm_proposals": llm_proposals,
                "thin_margins": thin,
                "workbook": str(wb),
            }
            if thin:
                log_fn(f"Converged with THIN margins on: {', '.join(thin)}")
            return summary

        failing = [r["id"] for r in results if r["verdict"] == "FAIL"]
        if llm_proposals >= max_llm_proposals:
            raise LoopEscalation(
                f"LLM proposal cap ({max_llm_proposals}) reached; still failing: {failing}",
                results, history_lines)

        proposal = propose_knobs(client, cfg, results, history_lines)
        changes = proposal.get("changes", [])
        applied = _apply_changes(cfg, changes)
        llm_proposals += 1

        diagnosis = proposal.get("diagnosis", [])
        diag_str = "; ".join(
            f"{d.get('criterion')}: {d.get('type')} - {d.get('reason', '')[:80]}"
            for d in diagnosis)
        change_str = "\n".join(
            f"  {a['path']}: {a.get('from')} -> {a.get('to')} ({a.get('predicted_effect', '')})"
            for a in applied if "error" not in a)
        errors = [a for a in applied if "error" in a]
        for err in errors:
            log_fn(f"WARN bad proposal path skipped: {err['path']} ({err['error']})")

        log_fn(f"Adjusting ({len(changes)} changes):\n{change_str}")
        session.log(f"### Proposal {iteration}\nDiagnosis: {diag_str}\n"
                    f"```json\n{json.dumps(applied, indent=2)}\n```")
        history_lines.append(f"iter {iteration}: failed={failing}, "
                             f"changed={[a['path'] for a in applied]}")

        Path(sim_path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    raise LoopEscalation(f"Iteration cap ({max_iterations}) reached",
                         results, history_lines)
