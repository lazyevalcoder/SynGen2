"""Phase 4: the convergence loop (Experiment D, automated with guardrails).

M5 additions (iteration 1):
- Proposal allowlist: only accounts/opportunities paths are tunable; edits to
  time_model/seed/output/quota are rejected at patch time (G14).
- Measured deltas: each proposal's history records how margins actually moved,
  so the proposer learns real transfer functions instead of guesses (G3).
- Margin-aware hardening: after convergence with thin margins, bounded
  re-centering rounds try to widen them; any round that fails validation or
  does not improve reverts to the best known-good state (G4).
"""
import copy
import json
from pathlib import Path

from syngen.generator.engine import generate_to_workbook
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt
from syngen.utils import extract_json, get_at_path, set_at_path
from syngen.validator.report import render_table, run_validation, to_report_dict

# Plan-of-record blocks: proposals may not touch these (G14). quota targets
# define the plan itself - tuning them to pass attainment would be circular.
BLOCKED_PATH_ROOTS = {"time_model", "seed", "output", "quota"}


class LoopEscalation(Exception):
    def __init__(self, reason, results, history):
        super().__init__(reason)
        self.reason = reason
        self.results = results
        self.history = history


def _path_root(path):
    return str(path).split(".")[0].split("[")[0]


def _tunable(path):
    """Allowlist decision for a proposed knob path (G14).

    Tunable: accounts.*, opportunities.*, and quota.attainment_by_segment.*
    (steering actuals relative to the plan is legitimate; editing the plan
    itself, the calendar, seed, or output paths is not).
    """
    root = _path_root(path)
    if root in ("accounts", "opportunities"):
        return True
    if root == "quota":
        return str(path).startswith("quota.attainment_by_segment")
    return False


def _apply_changes(cfg, changes):
    applied = []
    for ch in changes:
        path = ch.get("path", "")
        if not _tunable(path):
            applied.append({
                "path": path, "error":
                    "blocked: not a tunable knob (time_model/seed/output/"
                    "quota.by_segment are plan-of-record)"})
            continue
        try:
            try:
                old = get_at_path(cfg, path)
            except (KeyError, IndexError, TypeError):
                # null parents / missing containers: set_at_path creates them
                old = None
            set_at_path(cfg, path, ch.get("to"))
            applied.append({"path": path, "from": old, "to": ch.get("to"),
                            "predicted_effect": ch.get("predicted_effect", "")})
        except (KeyError, IndexError, TypeError) as e:
            applied.append({"path": path, "error": f"could not apply: {e}"})
    return applied


def propose_knobs(client, simulator_cfg, results, history_lines,
                  hardening=False):
    system = load_prompt(
        "knob_proposal",
        validation_results=render_table(results, all_pass=not hardening),
        iteration_history="\n".join(history_lines) or "none yet",
        simulator_json=json.dumps(simulator_cfg, indent=2),
    )
    user_msg = "Propose the next knob changes as JSON."
    if hardening:
        system += (
            "\n\nMODE: MARGIN HARDENING. Every criterion currently PASSES. "
            "The thinnest margins are too close to their thresholds - a seed "
            "change could flip them. Propose MINIMAL knob adjustments that "
            "move ONLY the thinnest criteria toward band-center while keeping "
            "every other criterion safely passing. Fewer than 3 changes; tiny "
            "moves; compensate interactions explicitly."
        )
    response = chat_json(client, "knob_proposal", system, user_msg)
    return response


def _min_margin(results):
    vals = [r["margin"] for r in results if r["margin"] is not None]
    return min(vals) if vals else None


def _thin_ids(results, thin_margin_pp):
    return [r["id"] for r in results
            if r["margin"] is not None and r["margin"] < thin_margin_pp]


def _record_measured_deltas(results, prev_margins, history_lines):
    """Append actual margin movement to the last history entry (G3): the
    proposer sees predicted-vs-realized transfer functions."""
    movements = []
    for r in results:
        prior = prev_margins.get(r["id"])
        if prior is not None and r["margin"] is not None:
            movements.append(f"{r['id']} margin {prior:+.2f}->{r['margin']:+.2f}")
    if movements and history_lines:
        history_lines[-1] += "; measured: " + ", ".join(movements)


def run_convergence(session, client, sim_path, criteria_path,
                    max_iterations=10, max_llm_proposals=5, log_fn=print,
                    thin_margin_pp=0.5, max_hardening_rounds=2):
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
    prev_margins = {}
    hardening_rounds = 0
    best = None  # {"cfg", "min_margin", "summary"} of last accepted all-pass

    def finish_with_best():
        """Ensure disk state matches the best known-good configuration."""
        Path(sim_path).write_text(json.dumps(best["cfg"], indent=2),
                                  encoding="utf-8")
        generate_to_workbook(best["cfg"])
        log_fn(f"Delivering hardened-best config "
               f"(min margin {best['min_margin']:.2f}).")
        return best["summary"]

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

        _record_measured_deltas(results, prev_margins, history_lines)
        prev_margins = {r["id"]: r["margin"] for r in results
                        if r["margin"] is not None}

        if all_pass:
            mm = _min_margin(results)
            summary = {
                "status": "converged",
                "iterations": iteration,
                "llm_proposals": llm_proposals,
                "thin_margins": _thin_ids(results, thin_margin_pp),
                "workbook": str(wb),
            }
            if best is None or mm > best["min_margin"]:
                best = {"cfg": copy.deepcopy(cfg), "min_margin": mm,
                        "summary": summary}

            thin = summary["thin_margins"]
            if not thin:
                if best["cfg"] != cfg:
                    return finish_with_best()
                return summary
            if llm_proposals >= max_llm_proposals:
                log_fn(f"Thin margins remain ({', '.join(thin)}) but proposal "
                       "cap reached - delivering as-is.")
                if best["cfg"] != cfg:
                    return finish_with_best()
                return summary
            if hardening_rounds >= max_hardening_rounds:
                log_fn(f"Thin margins remain ({', '.join(thin)}) after "
                       f"{max_hardening_rounds} hardening rounds - delivering.")
                if best["cfg"] != cfg:
                    return finish_with_best()
                return {**best["summary"],
                        "note": f"hardening budget ({max_hardening_rounds}) spent"}

            # --- G4 hardening round ---
            log_fn(f"Attempting margin hardening round {hardening_rounds + 1} "
                   f"(thin: {', '.join(thin)}).")
            proposal = propose_knobs(client, cfg, results, history_lines,
                                     hardening=True)
            llm_proposals += 1
            hardening_rounds += 1
            applied = _apply_changes(cfg, proposal.get("changes", []))
            session.log(f"### Hardening {hardening_rounds}\n"
                        f"```json\n{json.dumps(applied, indent=2)}\n```")
            history_lines.append(
                f"iter {iteration} (hardening): changed="
                f"{[a['path'] for a in applied if 'error' not in a]}")
            Path(sim_path).write_text(json.dumps(cfg, indent=2),
                                      encoding="utf-8")
            continue  # next iteration validates the hardened config; a FAIL
            # there hits the best-known-good branch below

        # --- FAIL path ---
        failing = [r["id"] for r in results if r["verdict"] == "FAIL"]
        if best is not None:
            # a hardening round broke something: revert, deliver best (G4)
            log_fn("Hardening round FAILED validation - reverting to "
                   "best known-good state.")
            session.log(f"HARDENING REVERTED after iteration {iteration}: "
                        f"failing={failing}")
            return finish_with_best()

        # Live M4 lesson: a criterion that references something the data
        # model cannot express (absent segment, missing sheet) is not
        # fixable by knob turns - looping just burns proposals (G14 family).
        structural = [r["id"] for r in results if r.get("structural")
                      and r["verdict"] == "FAIL"]
        if structural:
            raise LoopEscalation(
                f"structural failure(s) {structural} - criteria reference "
                "something outside the data model; re-enter design phases",
                results, history_lines)
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
