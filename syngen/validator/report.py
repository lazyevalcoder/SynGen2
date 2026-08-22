"""Validation runner and report rendering. Black-box: reads only the workbook."""
from pathlib import Path

import pandas as pd

from syngen.config import load_criteria
from syngen.validator.checks import CHECKS


def load_workbook(path):
    path = Path(path)
    opp = pd.read_excel(path, sheet_name="opportunities")
    accounts = pd.read_excel(path, sheet_name="accounts")
    opp["close_date"] = pd.to_datetime(opp["close_date"])
    return opp, accounts


def run_validation(workbook_path, criteria_path):
    """Returns (results list, all_pass bool). Results carry numeric margins."""
    opp, accounts = load_workbook(workbook_path)
    doc = load_criteria(criteria_path)

    calendar = doc.get("definitions", {}).get("quarter_end_dates")

    results = []
    for c in doc["criteria"]:
        fn = CHECKS.get(c["check"])
        if fn is None:
            results.append({
                "id": c["id"], "name": c["name"], "verdict": "ERROR",
                "actual": "unknown check", "target": "-", "margin": None,
                "detail": f"no check function registered for '{c['check']}'",
            })
            continue
        params = dict(c["params"])
        if calendar:
            params.setdefault("quarter_ends", calendar)
        try:
            r = fn(opp, accounts, params)
            results.append({
                "id": c["id"], "name": c["name"],
                "verdict": "PASS" if r["ok"] else "FAIL",
                "actual": r["actual"], "target": r["target"],
                "margin": r["margin"], "detail": r["detail"],
            })
        except Exception as e:
            results.append({
                "id": c["id"], "name": c["name"], "verdict": "ERROR",
                "actual": "error", "target": "-", "margin": None,
                "detail": str(e),
            })

    all_pass = all(r["verdict"] == "PASS" for r in results)
    return results, all_pass


def to_report_dict(results, all_pass, workbook, iteration=None):
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    report = {
        "workbook": str(workbook),
        "iteration": iteration,
        "overall": {"passed": passed, "total": len(results),
                    "exit_code": 0 if all_pass else 1},
        "results": [
            {k: r[k] for k in ("id", "verdict", "actual", "target", "margin", "detail")}
            for r in results
        ],
    }
    return report


def render_table(results, all_pass):
    lines = []
    header = f"{'ID':<5} {'Verdict':<8} {'Actual':<24} {'Target':<30} {'Margin':<9} Criterion"
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        margin = "-" if r["margin"] is None else f"{r['margin']:+.2f}"
        lines.append(
            f"{r['id']:<5} {r['verdict']:<8} {r['actual']:<24} {r['target']:<30} {margin:<9} {r['name']}"
        )
        if r["verdict"] != "PASS":
            lines.append(f"{'':5} -> {r['detail']}")
    lines.append("-" * len(header))
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    verdict = "STORY LANDED" if all_pass else "STORY NOT LANDED"
    lines.append(f"{passed}/{len(results)} criteria passed - {verdict}")
    return "\n".join(lines)
