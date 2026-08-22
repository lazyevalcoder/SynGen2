"""M2 vertical slice: the whole new-story flow runs offline against FakeLLM."""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.pipeline import apply_criterion_overrides, run_new_story
from syngen.session import Session


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


PRECHECK = {
    "claims": [
        {"claim": "Q4 discounts deeper", "classification": "COMPUTABLE", "note": ""},
        {"claim": "EMEA worst", "classification": "COMPUTABLE", "note": ""},
    ],
    "proceed": ["Q4 discounts deeper"],
    "questions_for_user": [],
}

CRITERIA = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "win rate flat", "check": "win_rate_flat",
         "params": {"band_pp": 10}, "classification": "statistical",
         "source_claim": "steady"},
        {"id": "AC2", "name": "Q1 discount", "check": "avg_discount_quarter",
         "params": {"quarter": "FY26-Q1", "target_pct": 12.0, "tolerance_pp": 4},
         "classification": "parametric", "source_claim": "creep"},
        {"id": "AC5", "name": "EMEA premium", "check": "region_discount_premium",
         "params": {"region": "EMEA", "vs": ["AMER", "APAC"],
                    "min_premium_pp": 8, "quarters": ["FY26-Q3", "FY26-Q4"]},
         "classification": "parametric", "source_claim": "worst in EMEA"},
        {"id": "AC6", "name": "EOQ effect", "check": "end_of_quarter_effect",
         "params": {"window_days": 14, "min_gap_pp": 3},
         "classification": "parametric", "source_claim": "quarter-end crunch"},
        {"id": "AC8", "name": "sanity", "check": "data_sanity",
         "params": {"max_discount_pct": 40}, "classification": "parametric",
         "source_claim": "realism"},
    ],
}

PERSONAS = {"domain_expert": ["ok"], "bi_engineer": ["ok"],
            "outsider": [], "conflicts": []}

# Deliberately BROKEN config: no EMEA premium -> AC5 must fail on iteration 1.
BROKEN_SIM = {
    "seed": 42,
    "time_model": {
        "fiscal_year": "FY26",
        "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
        "quarter_end_dates": ["2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"],
    },
    "output": {"workbook": "output/dataset.xlsx"},
    "accounts": {
        "count": 40,
        "regions": {"AMER": 0.45, "EMEA": 0.30, "APAC": 0.25},
        "segments": {"Enterprise": 0.3, "Mid-Market": 0.4, "SMB": 0.3},
        "industries": ["Software", "Retail"],
    },
    "opportunities": {
        "per_quarter": 120,
        "win_rate": 0.27,
        "win_rate_jitter": 0.005,
        "owners": ["A Rep", "B Rep"],
        "deal_duration_days": [20, 90],
        "close_clustering": {"share_in_end_of_quarter_window": 0.25},
        "deal_size_lognormal": {"median_usd": 45000, "sigma": 0.8},
        "discount": {
            "base_by_quarter": {
                "AMER": [12, 12, 12, 12],
                "APAC": [12, 12, 12, 12],
                "EMEA": [12, 12, 12, 12],
            },
            "noise_sd_pp": 3,
            "end_of_quarter_boost_pp": 6.5,
            "end_of_quarter_window_days": 14,
            "min_pct": 0,
            "max_pct": 40,
        },
    },
}

FIX_PROPOSAL = {
    "diagnosis": [{"criterion": "AC5", "type": "parametric",
                   "reason": "no EMEA premium in base curves"}],
    "changes": [
        {"path": "opportunities.discount.base_by_quarter.EMEA[2]", "from": 12,
         "to": 20, "predicted_effect": "AC5 premium appears", "compensates_for_index": None},
        {"path": "opportunities.discount.base_by_quarter.EMEA[3]", "from": 12,
         "to": 22, "predicted_effect": "AC5 premium holds in Q4", "compensates_for_index": None},
    ],
}


class SilentIO:
    def __init__(self):
        self.messages = []

    def inform(self, text):
        self.messages.append(str(text))

    def confirm(self, prompt, default=True):
        return True

    def ask(self, prompt, default=""):
        return default

    def free_text(self, prompt):
        return ""


def make_fake_client():
    return FakeLLM([
        llm_json(PRECHECK),
        llm_json(CRITERIA),
        llm_json(PERSONAS),
        llm_json(BROKEN_SIM),
        llm_json(FIX_PROPOSAL),
    ])


@pytest.fixture
def run_in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_full_vertical_slice_converges_offline(run_in_tmp):
    client = make_fake_client()
    io = SilentIO()
    result = run_new_story(client, "Q4 discounts deepened, worst in EMEA.",
                           io, sessions_dir="sessions", slug="test")

    assert result["status"] == "converged"
    assert result["iterations"] == 2, f"expected fix on iteration 2: {result}"
    assert result["llm_proposals"] == 1

    session_dir = run_in_tmp / "sessions"
    sessions = list(session_dir.iterdir())
    assert len(sessions) == 1
    sdir = sessions[0]
    for artifact in ("story-criteria.json", "spec.md", "simulator.json",
                     "session_log.md", "validation_report.md"):
        # criteria.json written under its contract name
        expected = "criteria.json" if artifact == "story-criteria.json" else artifact
        assert (sdir / expected).exists(), f"missing artifact: {expected}"

    sim = json.loads((sdir / "simulator.json").read_text(encoding="utf-8"))
    emea = sim["opportunities"]["discount"]["base_by_quarter"]["EMEA"]
    assert emea[2:] == [20, 22], "knob patch must persist to simulator.json"

    # Live-M3 regression: the workbook MUST land inside the session folder,
    # not in <cwd>/output (converge used to ignore its own resolved path)
    assert (sdir / "output" / "dataset.xlsx").exists(), \
        "workbook must be written to <session>/output/, contracts section 8"

    log_text = (sdir / "session_log.md").read_text(encoding="utf-8")
    assert "GATE 1 passed" in log_text
    assert "GATE 2 passed" in log_text
    assert "Iteration 2" in log_text


def test_overrides_parser_updates_params():
    doc = json.loads(json.dumps(CRITERIA))
    updated = apply_criterion_overrides(
        doc, "AC5.min_premium_pp=6; AC6.window_days=7")
    ac5 = next(c for c in updated["criteria"] if c["id"] == "AC5")
    ac6 = next(c for c in updated["criteria"] if c["id"] == "AC6")
    assert ac5["params"]["min_premium_pp"] == 6
    assert ac6["params"]["window_days"] == 7


def test_overrides_reject_unknown_criterion():
    with pytest.raises(ValueError, match="unknown criterion"):
        apply_criterion_overrides(json.loads(json.dumps(CRITERIA)), "AC99.x=1")


def test_bad_llm_criteria_shape_is_rejected(run_in_tmp):
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json({"oops": "no criteria here"}),
        llm_json(CRITERIA),
        llm_json(PERSONAS),
        llm_json(BROKEN_SIM),
    ])
    io = SilentIO()
    with pytest.raises(Exception):
        # malformed decomposition must surface, not silently produce a dataset
        run_new_story(client, "story text", io, sessions_dir="sessions", slug="bad")
