"""Regression tests from live-smoke failures (calendar mismatch, empty windows)."""
import numpy as np
import pandas as pd
import pytest

from syngen.validator import checks
from syngen.validator.checks import QUARTER_ENDS, check_end_of_quarter_effect


ALT_CALENDAR = {
    "FY26-Q1": "2026-06-30", "FY26-Q2": "2026-09-30",
    "FY26-Q3": "2026-12-31", "FY26-Q4": "2027-03-31",
}


def make_opp_with_calendar(q_ends, n_per_q=150, seed=5):
    rng = np.random.default_rng(seed)
    rows = []
    for label, end_str in q_ends.items():
        q_end = pd.Timestamp(end_str)
        q_start = q_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        q_len = (q_end - q_start).days + 1
        for _ in range(n_per_q):
            day = int(rng.integers(1, q_len + 1))
            disc = 12.0 + (4.0 if day > q_len - 14 else 0.0) + rng.normal(0, 2)
            rows.append({
                "fiscal_quarter": label,
                "region": "AMER",
                "account_id": "ACC-0001",
                "close_date": q_start + pd.Timedelta(days=day - 1),
                "stage": "Closed Won" if rng.random() < 0.3 else "Closed Lost",
                "list_price": 50000.0,
                "discount_pct": round(float(np.clip(disc, 0, 40)), 2),
                "realized_price": 45000.0,
            })
    return pd.DataFrame(rows)


def test_checks_respect_calendar_from_criteria():
    """A valid-but-different drafted calendar must not fail sanity checks."""
    opp = make_opp_with_calendar(ALT_CALENDAR)
    accounts = pd.DataFrame({"account_id": ["ACC-0001"]})
    params = {"max_discount_pct": 40, "quarter_ends": ALT_CALENDAR}
    r = checks.check_data_sanity(opp, accounts, params)
    assert r["ok"], f"alt-calendar data should pass when calendar is known: {r['detail']}"


def test_sanity_fails_when_calendar_mismatched():
    """Same data checked against the WRONG calendar must fail loudly."""
    opp = make_opp_with_calendar(ALT_CALENDAR)
    accounts = pd.DataFrame({"account_id": ["ACC-0001"]})
    params = {"max_discount_pct": 40, "quarter_ends": QUARTER_ENDS}
    r = checks.check_data_sanity(opp, accounts, params)
    assert not r["ok"]
    assert "close dates outside" in r["detail"]


def test_eoq_empty_window_is_clean_fail_not_nan():
    opp = make_opp_with_calendar(QUARTER_ENDS)
    # force every won deal into the EOQ window -> mid-quarter bucket empty
    opp = opp[opp["stage"] == "Closed Won"].copy()
    q_starts = {l: pd.Timestamp(e) - pd.DateOffset(months=3) + pd.Timedelta(days=1)
                for l, e in QUARTER_ENDS.items()}
    for label, q_start in q_starts.items():
        m = opp["fiscal_quarter"] == label
        opp.loc[m, "discount_pct"] = 15.0
        opp.loc[m, "realized_price"] = 42500.0
    params = {"window_days": 80, "min_gap_pp": 3,
              "quarter_ends": dict(QUARTER_ENDS)}
    r = check_end_of_quarter_effect(opp, pd.DataFrame(), params)
    assert not r["ok"]
    assert "mid-quarter" in r["detail"] or "no deals" in r["actual"]
    assert "nan" not in str(r["actual"]).lower()


def test_default_calendar_still_works_without_override(good_data=None):
    """Backward compat: no quarter_ends param -> hardcoded FY26 defaults."""
    rng = np.random.default_rng(9)
    rows = []
    for label, end_str in QUARTER_ENDS.items():
        q_end = pd.Timestamp(end_str)
        q_start = q_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        for _ in range(100):
            rows.append({"fiscal_quarter": label,
                         "account_id": "ACC-0001", "region": "AMER",
                         "close_date": q_start + pd.Timedelta(days=10),
                         "stage": "Closed Won", "list_price": 100.0,
                         "discount_pct": 5.0, "realized_price": 95.0})
    opp = pd.DataFrame(rows)
    accounts = pd.DataFrame({"account_id": ["ACC-0001"]})
    r = checks.check_data_sanity(opp, accounts, {"max_discount_pct": 40})
    assert r["ok"], r["detail"]
