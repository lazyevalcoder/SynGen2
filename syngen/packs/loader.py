"""Pack loader with import-time validation (DOMAIN_PACKS.md P0).

The manifest is normative. Validation fails hard when the pack references
something the bound kernel does not provide, or declares malformed
structure. Cross-checks against kernel registries make catalog drift a CI
failure instead of a silent divergence.
"""
import re
from pathlib import Path

from ..config import ConfigError, load_json
from ..prompts import PROMPT_DIR
from ..validator import checks as _checks_module
from .api import (
    KNOWN_MANIFEST_KEYS,
    LIST_MANIFEST_KEYS,
    REQUIRED_MANIFEST_KEYS,
    DomainPack,
    Entity,
    PackValidationError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_DIR = REPO_ROOT / "packs" / "revops"

_COMPAT_RE = re.compile(r"^\s*(>=|<=|==|~=)?\s*(\d+)\.(\d+)(?:\.(\d+))?\s*$")


def resolve_pack_path(path=None):
    return Path(path) if path else DEFAULT_PACK_DIR


def load_pack(path=None):
    """Load and validate a pack manifest; returns a DomainPack."""
    pack_dir = resolve_pack_path(path)
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        raise PackValidationError(f"pack manifest not found: {manifest_path}")
    try:
        manifest = load_json(manifest_path)
    except ConfigError as exc:
        raise PackValidationError(str(exc)) from exc
    return parse_manifest(manifest, path=str(manifest_path))


def parse_manifest(manifest, *, path="<manifest>"):
    errors = []

    def err(msg):
        errors.append(f"{path}: {msg}")

    if not isinstance(manifest, dict):
        raise PackValidationError(f"{path}: manifest must be a JSON object")

    unknown = sorted(set(manifest) - KNOWN_MANIFEST_KEYS)
    if unknown:
        err(f"unknown manifest keys: {', '.join(unknown)}")
    missing = REQUIRED_MANIFEST_KEYS - set(manifest)
    if missing:
        err(f"missing required keys: {', '.join(sorted(missing))}")
    if errors:
        raise PackValidationError("; ".join(errors))

    name = manifest["name"]
    version = manifest["version"]
    compat = manifest["kernel_compat"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        err(f"invalid pack name: {name!r}")
    if not isinstance(version, str) or not _COMPAT_RE.match(version):
        err(f"invalid pack version: {version!r}")
    if not isinstance(compat, str):
        err("kernel_compat must be a string constraint")
    for key in ("description",):
        if not isinstance(manifest.get(key, ""), str):
            err(f"{key} must be a string")

    lists = {}
    for key in LIST_MANIFEST_KEYS:
        value = manifest.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            err(f"{key} must be a list of strings")
            value = []
        dupes = _duplicates(value)
        if dupes:
            err(f"{key} contains duplicates: {', '.join(dupes)}")
        lists[key] = list(value)

    entities = {}
    raw_entities = manifest.get("entities", {})
    if not isinstance(raw_entities, dict):
        err("entities must be an object keyed by entity name")
    else:
        for ename, spec in raw_entities.items():
            if not isinstance(ename, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", ename):
                err(f"invalid entity name: {ename!r}")
                continue
            if not isinstance(spec, dict) or "binding" not in spec:
                err(f"entity {ename}: requires a 'binding' description")
                continue
            sheets = spec.get("sheets", [])
            if not isinstance(sheets, list) or not all(isinstance(s, str) for s in sheets):
                err(f"entity {ename}: 'sheets' must be a list of strings")
                continue
            entities[ename] = Entity(
                name=ename,
                binding=str(spec["binding"]),
                sheets=[str(s) for s in sheets],
                notes=str(spec.get("notes", "")),
            )

    matrix = manifest.get("claims_matrix")
    if matrix is not None and not isinstance(matrix, dict):
        err("claims_matrix must be an object when present")

    if errors:
        raise PackValidationError("; ".join(errors))

    return DomainPack(
        name=name,
        version=version,
        kernel_compat=compat,
        entities=entities,
        blocks=lists["blocks"],
        checks=lists["checks"],
        prompts=lists["prompts"],
        cohorts=lists["cohorts"],
        solvers=lists["solvers"],
        recipes=lists["recipes"],
        examples=lists["examples"],
        claims_matrix=matrix,
        description=str(manifest.get("description", "")),
        path=path,
    )


def validate_against_kernel(pack):
    """Cross-check the manifest against this kernel's built-in registries.

    Returns (errors, warnings): errors mean the pack cannot be trusted as
    the single source of truth; warnings flag kernel capabilities that are
    not registered in the pack (unregistered = invisible to derivation).
    """
    from ..linter import KNOWN_BLOCKS

    errors = []
    warnings = []

    for check_name in pack.checks:
        if not hasattr(_checks_module, f"check_{check_name}") and \
                check_name not in getattr(_checks_module, "CHECKS", {}):
            errors.append(f"check '{check_name}' is not provided by this kernel")

    unregistered_checks = sorted(
        set(getattr(_checks_module, "CHECKS", {})) - set(pack.checks)
    )
    if unregistered_checks:
        warnings.append(
            "kernel checks not declared in pack: " + ", ".join(unregistered_checks)
        )

    for block in pack.blocks:
        if block not in KNOWN_BLOCKS:
            errors.append(f"block '{block}' is not a known engine block")

    undeclared_blocks = sorted(KNOWN_BLOCKS - set(pack.blocks))
    if undeclared_blocks:
        warnings.append(
            "engine blocks not declared in pack: " + ", ".join(undeclared_blocks)
        )

    for prompt in pack.prompts:
        if not (PROMPT_DIR / f"{prompt}.txt").exists():
            errors.append(f"prompt fragment '{prompt}' does not exist")

    if not _compat_satisfied(pack.kernel_compat):
        errors.append(
            f"pack requires kernel {pack.kernel_compat}; "
            f"this kernel may be incompatible"
        )

    return errors, warnings


def ensure_valid(path=None):
    """Load + cross-validate; raises on any error. Warnings returned."""
    pack = load_pack(path)
    errors, warnings = validate_against_kernel(pack)
    if errors:
        raise PackValidationError("; ".join(errors))
    return pack, warnings


def _duplicates(values):
    seen, dupes = set(), []
    for v in values:
        if v in seen and v not in dupes:
            dupes.append(v)
        seen.add(v)
    return dupes


def _compat_satisfied(constraint):
    import syngen

    match = _COMPAT_RE.match(constraint or "")
    if not match:
        return False
    op, major, minor = match.group(1), int(match.group(2)), int(match.group(3))
    kernel_parts = syngen.__version__.split(".")
    k_major = int(kernel_parts[0])
    k_minor = int(kernel_parts[1]) if len(kernel_parts) > 1 else 0
    if op in (None, "=="):
        return (k_major, k_minor) == (major, minor)
    if op == ">=":
        return (k_major, k_minor) >= (major, minor)
    if op == "<=":
        return (k_major, k_minor) <= (major, minor)
    if op == "~=":
        return (k_major,) == (major,) and k_minor >= minor
    return False
