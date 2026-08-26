"""Pack loader with import-time validation (DOMAIN_PACKS.md P0).

The manifest is normative. Validation fails hard when the pack references
something the bound kernel does not provide, or declares malformed
structure. Cross-checks against kernel registries make catalog drift a CI
failure instead of a silent divergence.
"""
import re
from pathlib import Path

from ..config import ConfigError, load_json
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


def _pack_prompt_dir(pack):
    """Prompt fragments live beside the manifest (packs/<name>/prompts/)."""
    if not pack.path:
        return None
    return Path(pack.path).parent / "prompts"


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
    pack = parse_manifest(manifest, path=str(manifest_path))
    if isinstance(pack.claims_matrix, str):
        matrix_path = (manifest_path.parent / pack.claims_matrix).resolve()
        if not matrix_path.exists():
            raise PackValidationError(
                f"{manifest_path}: claims_matrix file not found: {matrix_path}")
        try:
            pack.claims_matrix = load_json(matrix_path)
        except ConfigError as exc:
            raise PackValidationError(str(exc)) from exc
        pack.claims_matrix_path = str(matrix_path)
    if isinstance(manifest.get("check_signatures"), str):
        sig_path = (manifest_path.parent /
                    manifest["check_signatures"]).resolve()
        if not sig_path.exists():
            raise PackValidationError(
                f"{manifest_path}: check_signatures file not found: {sig_path}")
        try:
            pack.check_signatures = load_json(sig_path)
        except ConfigError as exc:
            raise PackValidationError(str(exc)) from exc
    schemas_ref = manifest.get("entity_schemas")
    if isinstance(schemas_ref, str):
        schemas_dir = (manifest_path.parent / schemas_ref).resolve()
        if not schemas_dir.is_dir():
            raise PackValidationError(
                f"{manifest_path}: entity_schemas dir not found: {schemas_dir}")
        for schema_file in sorted(schemas_dir.glob("*.json")):
            try:
                doc = load_json(schema_file)
            except ConfigError as exc:
                raise PackValidationError(str(exc)) from exc
            name = schema_file.stem
            if name in pack.entity_schemas:
                raise PackValidationError(
                    f"entity_schemas: duplicate schema '{name}'")
            doc["_source"] = str(schema_file)
            pack.entity_schemas[name] = doc
        pack.entity_schemas_path = str(schemas_dir)
    return pack


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
    if matrix is not None and not isinstance(matrix, (dict, str)):
        err("claims_matrix must be an object or a path string when present")

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
    from ..validator import checks as _checks_module

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
        prompt_dir = _pack_prompt_dir(pack)
        if prompt_dir and prompt_dir.is_dir() and \
                not (prompt_dir / f"{prompt}.txt").exists():
            errors.append(f"prompt fragment '{prompt}' does not exist")

    matrix_errors, matrix_warnings = validate_claims_matrix(pack)
    errors.extend(matrix_errors)
    warnings.extend(matrix_warnings)

    schema_errors, schema_warnings = validate_entity_schemas(pack)
    errors.extend(schema_errors)
    warnings.extend(schema_warnings)

    sig_errors, sig_warnings = validate_check_signatures(pack)
    errors.extend(sig_errors)
    warnings.extend(sig_warnings)

    if not _compat_satisfied(pack.kernel_compat):
        errors.append(
            f"pack requires kernel {pack.kernel_compat}; "
            f"this kernel may be incompatible"
        )

    return errors, warnings


def validate_claims_matrix(pack):
    """Structural validation of the claim matrix against the pack.

    Errors: malformed cells, unknown ids (entity/cohort/check), duplicate
    cell ids, unknown metric/direction vocabulary.
    Warnings: pack checks no cell proves; cells with no checks.
    """
    from .api import DIRECTION_VOCAB, METRIC_VOCAB
    from .cohorts import names as cohort_names

    errors, warnings = [], []
    matrix = pack.claims_matrix
    if not matrix:
        warnings.append("pack declares no claim matrix")
        return errors, warnings
    if not isinstance(matrix, dict) or not isinstance(
            matrix.get("cells"), list):
        return [f"{pack.path}: claims_matrix must contain a 'cells' list"], []

    seen_ids = set()
    covered_checks = set()
    entity_names = set(pack.entities)
    known_cohorts = set(cohort_names())
    for cell in matrix["cells"]:
        cid = cell.get("id")
        where = f"cell {cid!r}" if cid else "unnamed cell"
        if not isinstance(cid, str) or not re.fullmatch(r"[a-z0-9_.]+", cid):
            errors.append(f"{where}: invalid cell id")
            continue
        if cid in seen_ids:
            errors.append(f"cell id duplicated: {cid}")
        seen_ids.add(cid)
        for key in ("kpi", "entity", "metric", "cohort"):
            if not isinstance(cell.get(key), str) or not cell[key]:
                errors.append(f"{where}: missing required field '{key}'")
        if errors and where.startswith("cell None"):
            continue
        checks = cell.get("checks", [])
        if not isinstance(checks, list) or not checks:
            errors.append(f"{where}: 'checks' must be a non-empty list")
            continue
        if not all(isinstance(c, str) for c in checks):
            errors.append(f"{where}: 'checks' entries must be strings")
            continue
        unknown_checks = [c for c in checks if c not in pack.checks]
        if unknown_checks:
            errors.append(f"{where}: unknown check(s): {', '.join(unknown_checks)}")
        covered_checks.update(checks)
        if cell.get("entity") not in entity_names:
            errors.append(f"{where}: unknown entity '{cell.get('entity')}'")
        if cell.get("cohort") not in known_cohorts:
            errors.append(f"{where}: unknown cohort '{cell.get('cohort')}'")
        if cell.get("metric") not in METRIC_VOCAB:
            errors.append(f"{where}: unknown metric '{cell.get('metric')}'")
        direction = cell.get("direction")
        if direction is not None and direction not in DIRECTION_VOCAB:
            errors.append(f"{where}: unknown direction {direction!r}")
        if not isinstance(cell.get("vocab"), str) or not cell["vocab"]:
            warnings.append(f"{cid}: no vocabulary doc (prompt catalogs "
                            "will render this check bare)")

    uncovered = sorted(set(pack.checks) - covered_checks)
    if uncovered:
        warnings.append("checks proven by no matrix cell: "
                        + ", ".join(uncovered))
    return errors, warnings


def validate_entity_schemas(pack):
    """Structural validation of column-level entity schemas.

    Errors: malformed schema docs, duplicate/invalid column names, unknown
    types, block references this kernel does not know.
    Warnings: schemas whose 'entities' links name taxonomy entries the pack
    does not declare; declared entities no schema materializes.
    """
    from .api import COLUMN_TYPE_VOCAB

    errors, warnings = [], []
    if not pack.entity_schemas:
        warnings.append("pack declares no entity schemas")
        return errors, warnings

    def _block_ref_ok(ref):
        if not isinstance(ref, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*(\.[a-z_]+)*", ref):
            return False
        return True

    linked_entities = set()
    for sname, doc in sorted(pack.entity_schemas.items()):
        where = f"entity_schemas/{sname}"
        for key in ("entity", "sheet", "grain", "presence", "columns"):
            if key not in doc:
                errors.append(f"{where}: missing required key '{key}'")
        if errors and any(e.startswith(where) for e in errors):
            continue
        presence = doc["presence"]
        if presence != "always":
            if not _block_ref_ok(presence):
                errors.append(f"{where}: invalid presence {presence!r}")
            elif presence.split(".")[0] not in _known_blocks():
                errors.append(f"{where}: presence block "
                              f"'{presence}' is not a known engine block")
        columns = doc.get("columns")
        if not isinstance(columns, list) or not columns:
            errors.append(f"{where}: 'columns' must be a non-empty list")
            continue
        seen_cols = set()
        for col in columns:
            cname = col.get("name") if isinstance(col, dict) else None
            cwhere = f"{where} column {cname!r}" if cname else \
                f"{where}: unnamed column"
            if not isinstance(cname, str) or not re.fullmatch(
                    r"[a-z][a-z0-9_]*", cname):
                errors.append(f"{cwhere}: invalid column name")
                continue
            if cname in seen_cols:
                errors.append(f"{where}: duplicate column '{cname}'")
            seen_cols.add(cname)
            if col.get("type") not in COLUMN_TYPE_VOCAB:
                errors.append(
                    f"{cwhere}: unknown type {col.get('type')!r}")
            when = col.get("when")
            if when is not None:
                if not _block_ref_ok(when):
                    errors.append(f"{cwhere}: invalid 'when' ref {when!r}")
                elif when.split(".")[0] not in _known_blocks():
                    errors.append(
                        f"{cwhere}: 'when' block '{when}' is not known")
            alts = col.get("alternatives")
            if alts is not None and (
                    not isinstance(alts, list)
                    or not all(isinstance(a, str) for a in alts)):
                errors.append(f"{cwhere}: 'alternatives' must be a list "
                              "of strings")
        derived = doc.get("derived", [])
        if not isinstance(derived, list):
            errors.append(f"{where}: 'derived' must be a list when present")
        else:
            for d in derived:
                if not isinstance(d, dict) or "field" not in d or \
                        "formula" not in d:
                    errors.append(
                        f"{where}: derived entries need 'field'+'formula'")
        linked = doc.get("entities", [])
        if isinstance(linked, list):
            linked_entities.update(linked)
        for ref in doc.get("blocks_used", []):
            if not _block_ref_ok(ref):
                errors.append(f"{where}: invalid blocks_used ref {ref!r}")
            elif ref.split(".")[0] not in _known_blocks():
                errors.append(f"{where}: blocks_used '{ref}' "
                              "is not a known engine block")

    unknown_links = sorted(linked_entities - set(pack.entities))
    if unknown_links:
        warnings.append("entity schemas link undeclared taxonomy entities: "
                        + ", ".join(unknown_links))
    materialized = set()
    for doc in pack.entity_schemas.values():
        materialized.update(doc.get("entities", []))
    unmaterialized = sorted(set(pack.entities) - materialized)
    if unmaterialized:
        warnings.append("taxonomy entities no schema materializes: "
                        + ", ".join(unmaterialized))
    return errors, warnings


def _known_blocks():
    from ..linter import KNOWN_BLOCKS
    return KNOWN_BLOCKS


def validate_check_signatures(pack):
    """Structural validation of the coordinate signature registry.

    Errors: signatures naming unknown checks, malformed coordinate entries,
    unknown unit-space references.
    Warnings: pack checks with no declared signature.
    """
    errors, warnings = [], []
    sigs = pack.check_signatures
    if not sigs:
        warnings.append("pack declares no check signatures")
        return errors, warnings
    if not isinstance(sigs, dict) or not isinstance(
            sigs.get("signatures"), dict):
        return [f"{pack.path}: check_signatures must contain a "
                "'signatures' object"], []
    spaces = sigs.get("unit_spaces", {})
    if not isinstance(spaces, dict):
        return [f"{pack.path}: unit_spaces must be an object"], []
    for sname, spec in sorted(spaces.items()):
        if not isinstance(spec, dict) or "source" not in spec:
            errors.append(f"check_signatures: unit space '{sname}' "
                          "needs a 'source'")
    for cname, sig in sorted(sigs["signatures"].items()):
        where = f"check_signatures/{cname}"
        if cname not in pack.checks:
            errors.append(f"{where}: signature names unknown check "
                          f"'{cname}'")
        if not isinstance(sig, dict):
            errors.append(f"{where}: signature must be an object")
            continue
        coords = sig.get("coordinates", [])
        if not isinstance(coords, list):
            errors.append(f"{where}: 'coordinates' must be a list")
            continue
        seen_params = set()
        for coord in coords:
            if not isinstance(coord, dict) or \
                    not isinstance(coord.get("param"), str):
                errors.append(f"{where}: coordinate entries need 'param'")
                continue
            pname = coord["param"]
            if pname in seen_params:
                errors.append(f"{where}: duplicate coordinate '{pname}'")
            seen_params.add(pname)
            space = coord.get("space")
            if space is not None and not isinstance(space, str):
                errors.append(f"{where}/{pname}: 'space' must be a string "
                              "or null (dimension selector)")
            elif isinstance(space, str) and space not in spaces and \
                    space != "quota_units":
                errors.append(f"{where}/{pname}: unknown unit space "
                              f"'{space}'")
            via = coord.get("via_dimension")
            if via is not None and (
                    not isinstance(via, str)
                    or via not in {c.get("param") for c in coords}):
                errors.append(f"{where}/{pname}: via_dimension must name "
                              "another coordinate param of this check")
    undeclared = sorted(set(pack.checks) - set(sigs["signatures"]))
    if undeclared:
        warnings.append("checks with no declared signature: "
                        + ", ".join(undeclared))
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
