"""Experiment F: verify tweaked session keeps structure identical, values different."""
import sys
from pathlib import Path

import pandas as pd

BASE = Path("../../experiments/B_config_generator/output/syngen_demo.xlsx")
TWEAKED = Path("output/tweaked.xlsx")


def structure(path):
    xl = pd.ExcelFile(path)
    return {s: list(pd.read_excel(path, sheet_name=s).columns) for s in xl.sheet_names}


def main():
    base_struct = structure(BASE)
    tweak_struct = structure(TWEAKED)

    print("Check 1: identical structure (sheets + columns)")
    same = base_struct == tweak_struct
    print(f"  sheets baseline: {list(base_struct)}")
    print(f"  sheets tweaked:  {list(tweak_struct)}")
    print(f"  identical: {same}")

    print("\nCheck 2: CSB segment present in tweaked data")
    acc = pd.read_excel(TWEAKED, sheet_name="accounts")
    opp = pd.read_excel(TWEAKED, sheet_name="opportunities")
    csb_accounts = (acc["segment"] == "CSB").sum()
    csb_opps = (opp["segment"] == "CSB").sum()
    print(f"  CSB accounts: {csb_accounts}, CSB opportunities: {csb_opps}")
    csb_ok = csb_accounts > 0 and csb_opps > 0

    print("\nCheck 3: values actually changed vs baseline")
    base_opp = pd.read_excel(BASE, sheet_name="opportunities")
    q4_base = base_opp[base_opp["stage"] == "Closed Won"].groupby("fiscal_quarter")["discount_pct"].mean()
    q4_tweak = opp[opp["stage"] == "Closed Won"].groupby("fiscal_quarter")["discount_pct"].mean()
    changed = not base_opp["discount_pct"].equals(opp["discount_pct"])
    print(f"  Q4 avg discount: baseline={q4_base['FY26-Q4']:.2f}% -> tweaked={q4_tweak['FY26-Q4']:.2f}%")
    print(f"  values differ: {changed}")

    ok = same and csb_ok and changed
    print(f"\nSTRUCTURE CHECK GATE: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
