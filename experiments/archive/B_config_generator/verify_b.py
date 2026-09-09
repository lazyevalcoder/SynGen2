import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def read_workbook(path):
    return {
        s: pd.read_excel(path, sheet_name=s)
        for s in ["accounts", "opportunities", "quarterly_summary"]
    }


def frames_equal(a, b):
    for sheet in a:
        if not a[sheet].equals(b[sheet]):
            return False
    return True


def main():
    base = Path(".")
    wb1_path = base / "output" / "syngen_demo.xlsx"
    wb1 = read_workbook(wb1_path)

    print("Check 1: determinism (same seed -> identical data)")
    subprocess.run([sys.executable, "generate.py"], check=True, capture_output=True)
    wb2 = read_workbook(wb1_path)
    det = frames_equal(wb1, wb2)
    print(f"  deterministic: {det}")

    print("Check 2: knob change (noise_sd_pp 3 -> 8) changes output without code edits")
    cfg = json.loads((base / "simulator.json").read_text(encoding="utf-8"))
    cfg["opportunities"]["discount"]["noise_sd_pp"] = 8
    cfg["output"]["workbook"] = "output/_knob_test.xlsx"
    alt_cfg = base / "simulator_knobtest.json"
    alt_cfg.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, "generate.py", str(alt_cfg)], check=True, capture_output=True)

    d1 = wb1["opportunities"]["discount_pct"]
    d2 = pd.read_excel(base / "output" / "_knob_test.xlsx", sheet_name="opportunities")["discount_pct"]
    print(f"  discount sd baseline: {d1.std():.2f} pp")
    print(f"  discount sd knob=8:   {d2.std():.2f} pp")
    spread_changed = abs(d2.std() - d1.std()) > 1.0
    print(f"  responds to knob: {spread_changed}")

    alt_cfg.unlink()
    (base / "output" / "_knob_test.xlsx").unlink()

    print("Check 3: data sanity (AC8)")
    opp = wb1["opportunities"]
    acc_ids = set(wb1["accounts"]["account_id"])
    checks = {
        "discount within [0,40]": bool(((opp["discount_pct"] >= 0) & (opp["discount_pct"] <= 40)).all()),
        "amounts positive": bool((opp["list_price"] > 0).all() and (opp["realized_price"] > 0).all()),
        "FKs valid": bool(opp["account_id"].isin(acc_ids).all()),
        "close dates within quarter": True,
    }
    q_ends = {  # quick manual map for FY26
        "FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30",
        "FY26-Q3": "2026-09-30", "FY26-Q4": "2026-12-31",
    }
    for label, end in q_ends.items():
        m = opp["fiscal_quarter"] == label
        if not (opp.loc[m, "close_date"] <= pd.Timestamp(end)).all():
            checks["close dates within quarter"] = False
    for name, ok in checks.items():
        print(f"  {name}: {'OK' if ok else 'FAIL'}")

    all_ok = det and spread_changed and all(checks.values())
    print(f"\nEXPERIMENT B GATE: {'PASS' if all_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
