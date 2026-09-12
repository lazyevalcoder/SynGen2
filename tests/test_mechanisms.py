"""P11 mechanism registry: addressable checkers with one Finding shape."""
from syngen import mechanisms
from syngen.mechanisms import Finding, hard, run

from test_p5_envelope import crit


def _doc():
    return {"criteria": [crit("AC1", "effective_capacity", target_pct=105,
                             band_pp=3)]}


def test_registry_lists_and_dispatches():
    assert set(mechanisms.names()) == {
        "capability", "geometry", "consistency", "schema", "structure",
        "required_blocks"}
    assert mechanisms.describe()["consistency"]


def test_capability_mechanism_flags_blocked_as_hard():
    doc = {"criteria": [crit("AC1", "quota_vs_potential", target_ratio_pct=120,
                             band_pp=5)]}
    findings = run("capability", doc=doc)
    assert findings and findings[0].criterion == "AC1"
    assert findings[0].severity == "hard"
    assert "blocked" in findings[0].message.lower()
    assert hard(findings)


def test_consistency_mechanism_returns_findings_list():
    doc = {"criteria": [crit("AC1", "effective_capacity", target_pct=90,
                             band_pp=3)]}
    findings = run("consistency", doc=doc)
    assert isinstance(findings, list)
    assert all(isinstance(f, Finding) for f in findings)


def test_schema_mechanism_flags_synonym_block_hard():
    findings = run("schema", cfg={"deals": {}})
    assert any(f.severity == "hard" and "R1" in f.message for f in findings)


def test_required_blocks_mechanism_reports_needs():
    findings = run("required_blocks", checks=["coverage_ratio"])
    assert findings[0].kind == "required_blocks"
    assert "pipeline" in findings[0].message and "quota" in findings[0].message


def test_finding_as_dict_roundtrip():
    f = Finding(kind="x", severity="hard", criterion="AC1", target=5.0)
    d = f.as_dict()
    assert d["kind"] == "x" and d["criterion"] == "AC1" and d["target"] == 5.0
