import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_WORKBOOK = Path("../B_config_generator/output/syngen_demo.xlsx")
OUT_DIR = Path("test_workbooks")


def run_validator(workbook):
    proc = subprocess.run(
        [sys.executable, "validate.py", str(workbook), "criteria.json"],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout


def load_opp():
    return pd.read_excel(BASE_WORKBOOK, sheet_name="opportunities")


def save(opp, accounts, name):
    path = OUT_DIR / name
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        accounts.to_excel(w, sheet_name="accounts", index=False)
        opp.to_excel(w, sheet_name="opportunities", index=False)
    return path


def make_broken_uniform():
    opp = load_opp()
    won = opp["stage"] == "Closed Won"
    rng = np.random.default_rng(7)
    opp.loc[won, "discount_pct"] = np.round(rng.normal(15.0, 0.5, int(won.sum())), 2)
    list_p = opp.loc[won, "list_price"]
    opp.loc[won, "realized_price"] = np.round(list_p * (1 - opp.loc[won, "discount_pct"] / 100), 2)
    return save(opp, read_accounts(), "broken_uniform.xlsx"), ["AC2", "AC3", "AC5", "AC6"]


def make_broken_winrate():
    opp = load_opp()
    rates = {"FY26-Q1": 0.15, "FY26-Q2": 0.40, "FY26-Q3": 0.20, "FY26-Q4": 0.35}
    for label, rate in rates.items():
        m = opp["fiscal_quarter"] == label
        idx = opp.index[m].to_numpy()
        n_won = int(round(len(idx) * rate))
        stages = np.array(["Closed Lost"] * len(idx), dtype=object)
        stages[:n_won] = "Closed Won"
        opp.loc[idx, "stage"] = stages
    return save(opp, read_accounts(), "broken_winrate.xlsx"), ["AC1"]


def make_broken_emea():
    opp = load_opp()
    won = opp["stage"] == "Closed Won"
    amer_avg_q = opp[won & (opp["region"] == "AMER")].groupby("fiscal_quarter")["discount_pct"].mean()
    emea_mask = won & (opp["region"] == "EMEA")
    opp.loc[emea_mask, "discount_pct"] = opp.loc[emea_mask, "fiscal_quarter"].map(amer_avg_q).round(2)
    list_p = opp.loc[emea_mask, "list_price"]
    opp.loc[emea_mask, "realized_price"] = np.round(list_p * (1 - opp.loc[emea_mask, "discount_pct"] / 100), 2)
    return save(opp, read_accounts(), "broken_emea.xlsx"), ["AC5"]


def make_broken_sanity():
    opp = load_opp()
    opp.loc[opp.index[0], "realized_price"] = -100.0
    opp.loc[opp.index[1], "account_id"] = "ACC-9999"
    return save(opp, read_accounts(), "broken_sanity.xlsx"), ["AC8"]


def read_accounts():
    return pd.read_excel(BASE_WORKBOOK, sheet_name="accounts")


def parse_failed_ids(stdout):
    failed = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in ("FAIL", "ERROR"):
            failed.append(parts[0])
    return failed


def main():
    OUT_DIR.mkdir(exist_ok=True)
    all_ok = True

    print("=" * 70)
    print("DIRECTION 1: broken data must FAIL the relevant criteria")
    print("=" * 70)
    makers = [make_broken_uniform, make_broken_winrate, make_broken_emea, make_broken_sanity]
    for maker in makers:
        path, expected_fails = maker()
        code, stdout = run_validator(path)
        failed_ids = parse_failed_ids(stdout)
        missing = [c for c in expected_fails if c not in failed_ids]
        ok = not missing
        all_ok &= ok
        status = "OK" if ok else "MISSED"
        print(f"{path.name:<28} exit={code}  expected fails: {expected_fails}")
        print(f"{'':28} actual fails: {failed_ids or 'none'}  -> {status}")

    print()
    print("=" * 70)
    print("DIRECTION 2: baseline workbook gets an honest mixed verdict")
    print("=" * 70)
    code, stdout = run_validator(BASE_WORKBOOK)
    print(stdout)

    print("\nVALIDATOR TEST GATE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
