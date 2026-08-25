"""Named cohort filters over generated RevOps frames (M6 P1).

Cohorts are the composable vocabulary the claim matrix references: every
matrix cell names a cohort registered here, so guard logic reasons over a
closed set instead of free-text filters. Each filter returns a boolean
mask aligned to the frame's index; combine with ``combined_mask`` (AND
algebra - negation is provided by dedicated ex_* cohorts).

Missing-column semantics mirror engine reality: a frame generated without
the outlier block has no whales (ex_outlier = all rows), without the
forecast block nothing is in_commit, and so on. Filters that cannot be
evaluated at all (no stage column) raise a clear error.
"""
import pandas as pd

TERMINAL_STAGES = frozenset({"Closed Won", "Closed Lost"})


class UnknownCohortError(ValueError):
    pass


def _require(df, col):
    if col not in df.columns:
        raise KeyError(f"cohort filter requires column '{col}'; "
                       f"frame has {sorted(df.columns)}")


def _flag_default_true(df, col):
    if col not in df.columns:
        return pd.Series(True, index=df.index)
    return df[col].astype(bool)


def _flag_default_false(df, col):
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def _m_won(df):
    _require(df, "stage")
    return df["stage"] == "Closed Won"


def _m_lost(df):
    _require(df, "stage")
    return df["stage"] == "Closed Lost"


def _m_closed(df):
    _require(df, "stage")
    return df["stage"].isin(TERMINAL_STAGES)


def _m_open(df):
    if "stage" in df.columns:
        return ~df["stage"].isin(TERMINAL_STAGES)
    _require(df, "close_date")
    return df["close_date"].isna()


COHORTS = {
    "all": (lambda df: pd.Series(True, index=df.index), "every row"),
    "won": (_m_won, "stage == Closed Won"),
    "lost": (_m_lost, "stage == Closed Lost"),
    "closed": (_m_closed, "stage in terminal states (Won/Lost)"),
    "open_pipeline": (_m_open, "not in a terminal stage"),
    "ex_outlier": (lambda df: ~_flag_default_false(df, "is_outlier"),
                   "rows that are not whale deals (missing flag = none)"),
    "outliers": (lambda df: _flag_default_false(df, "is_outlier"),
                 "whale deals only (missing flag = empty)"),
    "icp": (lambda df: _flag_default_false(df, "icp"),
            "ideal-customer-profile accounts"),
    "non_icp": (lambda df: ~_flag_default_false(df, "icp"),
                "non-ICP accounts"),
    "in_commit": (lambda df: _flag_default_false(df, "in_commit"),
                  "deals flagged into the org's commit (missing flag = none)"),
}


def names():
    return sorted(COHORTS)


def describe():
    return {n: desc for n, (_, desc) in COHORTS.items()}


def mask(df, cohort_name):
    """Boolean mask for one named cohort."""
    try:
        fn, _ = COHORTS[cohort_name]
    except KeyError:
        raise UnknownCohortError(
            f"unknown cohort '{cohort_name}'; known: {names()}") from None
    m = fn(df)
    if not isinstance(m, pd.Series) or len(m) != len(df):
        raise ValueError(f"cohort '{cohort_name}' did not produce an "
                         "aligned boolean mask")
    return m


def combined_mask(df, cohort_names):
    """Conjunction of named cohorts (AND). Negation via ex_* cohorts."""
    result = pd.Series(True, index=df.index)
    for name in cohort_names or []:
        result &= mask(df, name)
    return result


def apply(df, cohort_names):
    return df[combined_mask(df, cohort_names)]
