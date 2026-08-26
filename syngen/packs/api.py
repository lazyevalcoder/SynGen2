"""Domain pack data contracts.

A pack is the normative description of one vertical ("the bible"): every
kernel layer either derives from it or validates against it. P0 ships the
manifest shape and validation; capability classes below are the stable
interfaces later phases bind implementations to.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

REQUIRED_MANIFEST_KEYS = {"name", "version", "kernel_compat"}
KNOWN_MANIFEST_KEYS = REQUIRED_MANIFEST_KEYS | {
    "description",
    "entities",
    "entity_schemas",
    "check_signatures",
    "blocks",
    "checks",
    "prompts",
    "cohorts",
    "solvers",
    "recipes",
    "examples",
    "claims_matrix",
}
LIST_MANIFEST_KEYS = ("blocks", "checks", "prompts", "cohorts", "solvers", "recipes", "examples")

COLUMN_TYPE_VOCAB = frozenset({
    "id", "fk", "string", "categorical", "boolean", "decimal", "integer",
    "date", "derived",
})

METRIC_VOCAB = frozenset({
    "level", "trend", "share", "ratio", "divergence", "concentration",
    "correlation", "timing", "aging", "composite", "generic",
})
DIRECTION_VOCAB = frozenset({"up", "down", "flat", None})


class PackValidationError(ValueError):
    pass


@dataclass
class Entity:
    """One canonical entity: name plus where it materializes."""

    name: str
    binding: str
    sheets: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DomainPack:
    name: str
    version: str
    kernel_compat: str
    entities: Dict[str, Entity]
    blocks: List[str]
    checks: List[str]
    prompts: List[str]
    cohorts: List[str] = field(default_factory=list)
    solvers: List[str] = field(default_factory=list)
    recipes: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    claims_matrix: Optional[Dict[str, Any]] = None
    check_signatures: Dict[str, Any] = field(default_factory=dict)
    entity_schemas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    entity_schemas_path: Optional[str] = None
    description: str = ""
    path: Optional[str] = None


class ClaimTaxonomy:
    """Cell registry + cohort algebra. P1 populates it from claims/matrix.json."""

    def cells(self) -> Dict[str, Dict[str, Any]]:
        raise NotImplementedError

    def cohorts(self) -> Dict[str, Callable[[Any], Any]]:
        raise NotImplementedError


class ProofPlugin:
    """Check functions following the margin contract."""

    def checks(self) -> Dict[str, Callable[..., dict]]:
        raise NotImplementedError


class SolverPlugin:
    """Calibration algebras bound to matrix cells."""

    def solvers(self) -> Dict[str, Callable[..., Any]]:
        raise NotImplementedError


class SchemaProvider:
    """Entity/sheet schemas the pack generates."""

    def schema(self) -> Dict[str, Any]:
        raise NotImplementedError


class SemanticPrompts:
    """Prompt fragments injected per kernel phase."""

    def fragments(self) -> Dict[str, str]:
        raise NotImplementedError


class RecipeLibrary:
    """Autopilot block-synthesis templates."""

    def recipes(self) -> Dict[str, Callable[..., Any]]:
        raise NotImplementedError


class CaseMemory:
    """Landed configs for few-shot retrieval."""

    def examples(self) -> List[Any]:
        raise NotImplementedError
