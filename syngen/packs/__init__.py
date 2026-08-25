"""Kernel-side plugin interfaces for domain packs (M6 / DOMAIN_PACKS.md).

P0 discipline: these contracts are declarative. Nothing in the kernel is
rewired yet; the loader validates the pack manifest against the kernel's
built-in registries so drift between them becomes a hard error instead of
silent duplication.
"""
from .api import (
    CaseMemory,
    ClaimTaxonomy,
    DomainPack,
    ProofPlugin,
    RecipeLibrary,
    SchemaProvider,
    SemanticPrompts,
    SolverPlugin,
)
from .loader import PackValidationError, load_pack, resolve_pack_path

__all__ = [
    "CaseMemory",
    "ClaimTaxonomy",
    "DomainPack",
    "PackValidationError",
    "ProofPlugin",
    "RecipeLibrary",
    "SchemaProvider",
    "SemanticPrompts",
    "SolverPlugin",
    "load_pack",
    "resolve_pack_path",
]
