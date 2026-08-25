"""Domain pack loader and manifest validation (M6 P0)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.packs import (
    DomainPack,
    PackValidationError,
    load_pack,
    resolve_pack_path,
)
from syngen.packs.loader import ensure_valid, parse_manifest, validate_against_kernel

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


def test_kernel_extra_checks_surface_as_warnings_not_errors(tmp_path):
    trimmed = [c for c in load_pack(REPO_PACK).checks if c != "data_sanity"]
    pack = parse_manifest(
        {**json.loads((REPO_PACK / "pack.json").read_text(encoding="utf-8")),
         "checks": trimmed}
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
