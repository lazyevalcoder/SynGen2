"""Domain pack loader and manifest validation (M6 P0/P1)."""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.packs import (
    DomainPack,
    PackTaxonomy,
    PackValidationError,
    load_pack,
    resolve_pack_path,
)
from syngen.packs.loader import ensure_valid, parse_manifest, validate_against_kernel
from syngen.packs.cohorts import UnknownCohortError, apply, combined_mask, describe, mask

REPO_PACK = Path(__file__).resolve().parents[1] / "packs" / "revops"


@pytest.fixture(scope="module")
def revops():
    return load_pack(REPO_PACK)


def test_repo_revops_pack_loads(revops):
    assert isinstance(revops, DomainPack)
    assert revops.name == "revops"
    assert revops.version == "0.1.0"
    assert revops.entities["quota"].sheets == ["quota_plan"]
    assert len(revops.checks) == 33


def test_repo_pack_validates_against_kernel_with_zero_drift(revops):
    from syngen.linter import KNOWN_BLOCKS
    from syngen.validator.checks import CHECKS

    errors, warnings = validate_against_kernel(revops)
    assert errors == []
    assert warnings == []
    assert set(revops.checks) == set(CHECKS)
    assert set(revops.blocks) == set(KNOWN_BLOCKS)


def test_ensure_valid_on_repo_pack():
    pack, warnings = ensure_valid(REPO_PACK)
    assert warnings == []
    assert pack.name == "revops"


def _write_pack(tmp_path, **overrides):
    base = json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8"))
    base.update(overrides)
    d = tmp_path / "pack_under_test"
    d.mkdir()
    (d / "pack.json").write_text(json.dumps(base), encoding="utf-8")
    (d / "claims").mkdir()
    (d / "claims" / "matrix.json").write_text(
        (REPO_PACK / "claims" / "matrix.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    shutil.copytree(REPO_PACK / "prompts", d / "prompts")
    return d


def test_unknown_check_name_is_hard_error(tmp_path):
    pack_dir = _write_pack(tmp_path, checks=["win_rate_flat", "no_such_metric"])
    with pytest.raises(PackValidationError, match="no_such_metric"):
        ensure_valid(pack_dir)


def test_unknown_block_is_hard_error(tmp_path):
    pack_dir = _write_pack(tmp_path, blocks=["seed", "invoice_rollup"])
    with pytest.raises(PackValidationError, match="invoice_rollup"):
        ensure_valid(pack_dir)


def test_missing_prompt_fragment_is_hard_error(tmp_path):
    pack_dir = _write_pack(tmp_path, prompts=["precheck", "ghost_prompt"])
    with pytest.raises(PackValidationError, match="ghost_prompt"):
        ensure_valid(pack_dir)


def test_kernel_extra_checks_surface_as_warnings_not_errors():
    trimmed = [c for c in load_pack(REPO_PACK).checks if c != "data_sanity"]
    pack = parse_manifest(
        {**json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8")),
         "checks": trimmed, "claims_matrix": None}
    )
    errors, warnings = validate_against_kernel(pack)
    assert errors == []
    assert any("data_sanity" in w for w in warnings)


def test_missing_required_key_rejected(tmp_path):
    manifest = json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8"))
    del manifest["kernel_compat"]
    with pytest.raises(PackValidationError, match="kernel_compat"):
        parse_manifest(manifest)


def test_unknown_manifest_key_rejected():
    with pytest.raises(PackValidationError, match="unknown manifest keys"):
        parse_manifest({"bogus": 1})


def test_duplicate_check_names_rejected():
    manifest = json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8"))
    manifest["checks"] = ["win_rate_flat", "win_rate_flat"]
    with pytest.raises(PackValidationError, match="duplicates"):
        parse_manifest(manifest)


def test_entity_without_binding_rejected():
    manifest = json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8"))
    manifest["entities"] = {"orphan": {"sheets": ["x"]}}
    with pytest.raises(PackValidationError, match="'binding'"):
        parse_manifest(manifest)


def test_incompatible_kernel_constraint_rejected_at_crosscheck(revops):
    bad = DomainPack(
        name=revops.name,
        version=revops.version,
        kernel_compat="<0.1.0",
        entities=revops.entities,
        blocks=revops.blocks,
        checks=revops.checks,
        prompts=revops.prompts,
    )
    errors, _ = validate_against_kernel(bad)
    assert any("incompatible" in e or "kernel" in e for e in errors)


def test_resolve_default_path():
    assert resolve_pack_path() == REPO_PACK


def test_missing_manifest_rejected(tmp_path):
    with pytest.raises(PackValidationError, match="not found"):
        load_pack(tmp_path)


# --- claim matrix (M6 P1) ----------------------------------------------------


def test_repo_matrix_loads_and_covers_every_check():
    from syngen.validator.checks import CHECKS

    pack = load_pack(REPO_PACK)
    assert isinstance(pack.claims_matrix, dict)
    cells = pack.claims_matrix["cells"]
    assert len(cells) == len(CHECKS)
    errors, warnings = validate_against_kernel(pack)
    assert errors == []
    assert warnings == []
    proven = {c for cell in cells for c in cell["checks"]}
    assert proven == set(CHECKS)


def test_taxonomy_adapter_roundtrip(revops):
    taxonomy = PackTaxonomy(revops)
    assert len(taxonomy.cells()) == 33
    hits = taxonomy.cells_for_check("revenue_vs_plan")
    assert hits and hits[0]["kpi"] == "plan_attainment"
    assert "ex_outlier" in taxonomy.cohorts()


def test_matrix_file_reference_resolved_relative_to_manifest():
    pack = load_pack(REPO_PACK)
    assert pack.claims_matrix_path.endswith("matrix.json")
    assert isinstance(pack.claims_matrix["cells"], list)


def _write_matrix_variant(tmp_path, mutate):
    base = json.loads((REPO_PACK / "claims" / "matrix.json").read_text(encoding="utf-8"))
    mutate(base)
    d = _write_pack(tmp_path)
    (d / "claims" / "matrix.json").write_text(json.dumps(base), encoding="utf-8")
    return d


def test_duplicate_cell_id_rejected(tmp_path):
    def dup(m):
        m["cells"].append(dict(m["cells"][0]))
    with pytest.raises(PackValidationError, match="duplicated"):
        ensure_valid(_write_matrix_variant(tmp_path, dup))


def test_unknown_check_in_cell_rejected(tmp_path):
    def bad(m):
        m["cells"][0]["checks"] = ["no_such_check"]
        m["cells"][0]["id"] = "x.unique.id"
    with pytest.raises(PackValidationError, match="unknown check"):
        ensure_valid(_write_matrix_variant(tmp_path, bad))


def test_unknown_entity_in_cell_rejected(tmp_path):
    def bad(m):
        m["cells"][0]["entity"] = "unicorn"
        m["cells"][0]["id"] = "x.unique.id"
    with pytest.raises(PackValidationError, match="unknown entity"):
        ensure_valid(_write_matrix_variant(tmp_path, bad))


def test_unknown_cohort_in_cell_rejected(tmp_path):
    def bad(m):
        m["cells"][0]["cohort"] = "left_handed_accounts"
        m["cells"][0]["id"] = "x.unique.id"
    with pytest.raises(PackValidationError, match="unknown cohort"):
        ensure_valid(_write_matrix_variant(tmp_path, bad))


def test_unknown_metric_in_cell_rejected(tmp_path):
    def bad(m):
        m["cells"][0]["metric"] = "vibes"
        m["cells"][0]["id"] = "x.unique.id"
    with pytest.raises(PackValidationError, match="unknown metric"):
        ensure_valid(_write_matrix_variant(tmp_path, bad))


def test_uncovered_check_surfaces_as_warning(tmp_path):
    def drop_last(m):
        m["cells"] = [c for c in m["cells"] if c["checks"] != ["data_sanity"]]
    pack = load_pack(_write_matrix_variant(tmp_path, drop_last))
    _, warnings = validate_against_kernel(pack)
    assert any("data_sanity" in w for w in warnings)


def test_generic_flag_marks_hygiene_cell(revops):
    taxonomy = PackTaxonomy(revops)
    sanity = taxonomy.cells()["hygiene.data_sanity.all"]
    assert sanity.get("generic") is True


# --- generated prompt catalogs (M6 P2) ---------------------------------------


def test_check_catalog_covers_exactly_the_kernel_registry():
    from syngen.validator.checks import CHECKS

    taxonomy = PackTaxonomy(load_pack(REPO_PACK))
    catalog_names = [line[2:].split(":")[0]
                     for line in taxonomy.check_catalog().splitlines()]
    assert set(catalog_names) == set(CHECKS)
    assert len(catalog_names) == len(CHECKS)
    assert set(taxonomy.check_names(" | ").split(" | ")) == set(CHECKS)


def test_every_cell_documents_its_vocabulary():
    pack = load_pack(REPO_PACK)
    undocumented = [c["id"] for c in pack.claims_matrix["cells"]
                    if not c.get("vocab")]
    assert undocumented == []


def test_decompose_prompt_renders_generated_catalog_not_hardcoded_list():
    from syngen.phases.intake import _pack_taxonomy
    from syngen.prompts import load_prompt

    tax = _pack_taxonomy()
    text = load_prompt("decompose", user_decisions="none", story="s",
                       check_catalog=tax.check_catalog(),
                       check_names=tax.check_names())
    assert "{{check_catalog}}" not in text
    assert "{{check_names}}" not in text
    for check in ("revenue_vs_plan", "effective_capacity",
                  "activity_potential_misalignment", "data_sanity"):
        assert f"- {check}:" in text


def test_intake_taxonomy_cache_returns_same_instance():
    from syngen.phases.intake import _pack_taxonomy
    assert _pack_taxonomy() is _pack_taxonomy()


# --- cohort algebra ----------------------------------------------------------


def _sample_frame():
    return pd.DataFrame({
        "stage": ["Closed Won", "Closed Lost", "Proposal", "Negotiation"],
        "is_outlier": [True, False, False, False],
        "icp": [True, False, True, False],
        "in_commit": [True, None, None, None],
    })


def test_cohort_masks_basic_partitions():
    df = _sample_frame()
    assert mask(df, "won").tolist() == [True, False, False, False]
    assert mask(df, "lost").tolist() == [False, True, False, False]
    assert mask(df, "closed").tolist() == [True, True, False, False]
    assert mask(df, "open_pipeline").tolist() == [False, False, True, True]
    assert mask(df, "outliers").tolist() == [True, False, False, False]


def test_missing_column_defaults_match_engine_semantics():
    no_flags = pd.DataFrame({"stage": ["Closed Won", "Proposal"]})
    assert mask(no_flags, "ex_outlier").all()
    assert not mask(pd.DataFrame({"stage": ["Closed Won"]}), "in_commit").any()


def test_combined_mask_is_conjunction():
    df = _sample_frame()
    got = combined_mask(df, ["closed", "ex_outlier"])
    assert got.tolist() == [False, True, False, False]
    assert len(apply(df, ["icp"])) == 2


def test_unknown_cohort_raises_with_known_names():
    with pytest.raises(UnknownCohortError, match="known"):
        mask(pd.DataFrame({"a": [1]}), "bogus")
    assert "open_pipeline" in describe()
