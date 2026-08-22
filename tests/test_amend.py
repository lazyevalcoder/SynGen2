"""M3: criteria dependency propagation (GAPS G10) - deterministic graph walk."""
import pytest

from syngen.phases.amend import (
    apply_amendments,
    apply_criterion_overrides,
    apply_structured_amendments,
    consistency_report,
    dependency_closure,
)


def make_doc():
    return {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "win rate", "check": "win_rate_flat",
             "params": {"band_pp": 3}},
            {"id": "AC2", "name": "q1 discount",
             "check": "avg_discount_quarter",
             "params": {"quarter": "FY26-Q1", "target_pct": 12}},
            {"id": "AC7", "name": "realized vs list",
             "check": "realized_vs_list",
             "depends_on": ["AC2"], "params": {"target_end_pct": 82}},
            {"id": "AC9", "name": "chained", "check": "win_rate_flat",
             "depends_on": ["AC7"], "params": {"band_pp": 5}},
        ],
    }


def test_direct_dependent_in_closure():
    """AC7 depends on AC2 (no further chain): amending AC2 surfaces AC7."""
    doc = make_doc()
    del next(c for c in doc["criteria"] if c["id"] == "AC9")["depends_on"]
    assert dependency_closure(doc["criteria"], {"AC2"}) == ["AC7"]


def test_transitive_closure():
    """AC9 depends on AC7 which depends on AC2: amending AC2 hits both."""
    doc = make_doc()
    assert dependency_closure(doc["criteria"], {"AC2"}) == ["AC7", "AC9"]


def test_changed_ids_excluded_from_closure():
    doc = make_doc()
    assert dependency_closure(doc["criteria"], {"AC2", "AC7"}) == ["AC9"]


def test_no_dependencies_empty_closure():
    doc = make_doc()
    assert dependency_closure(doc["criteria"], {"AC1"}) == []


def test_apply_amendments_reports_affected():
    doc = make_doc()
    doc, changed, affected = apply_amendments(doc, "AC2.target_pct=14")
    ac2 = next(c for c in doc["criteria"] if c["id"] == "AC2")
    assert ac2["params"]["target_pct"] == 14
    assert changed == ["AC2"]
    assert affected == ["AC7", "AC9"]


def test_apply_amendments_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown criterion"):
        apply_amendments(make_doc(), "AC99.x=1")


def test_apply_structured_amendments_splits_errors():
    doc = make_doc()
    doc, applied, errors = apply_structured_amendments(doc, [
        {"id": "AC2", "param": "target_pct", "to": 13},
        {"id": "NOPE", "param": "x", "to": 1},
        {"id": "AC7", "param": "", "to": 1},
    ])
    assert len(applied) == 1 and len(errors) == 2
    ac2 = next(c for c in doc["criteria"] if c["id"] == "AC2")
    assert ac2["params"]["target_pct"] == 13


def test_consistency_report_lists_edges():
    report = consistency_report(make_doc())
    assert "AC7 <- depends on AC2" in report
    assert "AC9 <- depends on AC7" in report
    empty = consistency_report({"criteria": [{"id": "AC1"}]})
    assert "no dependencies" in empty


def test_override_parser_still_available_from_old_path():
    """Backward compat: tests/CLI import this from syngen.pipeline."""
    from syngen.pipeline import apply_criterion_overrides as via_pipeline
    doc = make_doc()
    via_pipeline(doc, "AC1.band_pp=10")
    assert next(c for c in doc["criteria"]
                if c["id"] == "AC1")["params"]["band_pp"] == 10
