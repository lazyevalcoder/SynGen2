"""Deterministic mechanism registry (P11).

One addressable name per checker, one normalized `Finding` shape. The
orchestrator can pull a mechanism on demand instead of hard-coding each call
site. Pure adapters over the existing gates - no behavior change, and each
mechanism is testable in isolation.

Nothing here calls an LLM. Mechanisms are the deterministic "tools" the
conductor dispatches; the model only drafts artifacts.
"""
from dataclasses import asdict, dataclass


@dataclass
class Finding:
    kind: str
    severity: str = "info"          # hard | soft | info
    criterion: str | None = None
    param: str | None = None
    target: float | None = None
    actual: float | None = None
    nearest: float | None = None
    message: str = ""

    def as_dict(self):
        return asdict(self)


_REGISTRY = {}


def register(name, description=""):
    def deco(fn):
        _REGISTRY[name] = {"fn": fn, "description": description}
        return fn
    return deco


def names():
    return sorted(_REGISTRY)


def describe():
    return {k: v["description"] for k, v in _REGISTRY.items()}


def run(name, **ctx):
    """Dispatch a mechanism by name. Unknown names are a programming error."""
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"unknown mechanism: {name}")
    return entry["fn"](**ctx)


def hard(findings):
    return [f for f in findings if f.severity == "hard"]


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


@register("capability", "per-criterion reachability, predicted value and gap")
def capability_mechanism(doc, cfg=None):
    from syngen.capability import assess_criteria
    out = []
    for f in assess_criteria(doc, cfg):
        reach = f.get("reachable")
        sev = "hard" if reach is False else ("info" if reach is True else "soft")
        out.append(Finding(
            kind="capability", severity=sev, criterion=f.get("id"),
            param=f.get("param"), target=_num(f.get("target")),
            actual=_num(f.get("predicted")), nearest=_num(f.get("nearest")),
            message=f.get("note") or "",
        ))
    return out


@register("geometry", "criteria coordinates must exist in the config")
def geometry_mechanism(cfg, doc, feasibility=False):
    from syngen.phases.criteria_lint import cross_lint
    return [Finding(kind="geometry", severity="hard", message=m)
            for m in cross_lint(cfg, doc, feasibility=feasibility)]


@register("consistency", "criteria must not be jointly unsatisfiable")
def consistency_mechanism(doc):
    from syngen.phases.criteria_lint import lint_criteria_internal
    h, notes = lint_criteria_internal(doc)
    return ([Finding(kind="consistency", severity="hard", message=m)
             for m in h]
            + [Finding(kind="consistency", severity="soft", message=m)
               for m in notes])


@register("schema", "simulator.json shape and internal consistency")
def schema_mechanism(cfg):
    from syngen.linter import lint
    out = []
    for rule, sev, msg in lint(cfg):
        out.append(Finding(kind="schema",
                           severity="hard" if sev == "FAIL" else "soft",
                           message=f"{rule}: {msg}"))
    return out


@register("structure", "workbook sheet/column contract")
def structure_mechanism(workbook_path, cfg=None):
    from syngen.linter import structure_findings
    return [Finding(kind="structure", severity="hard",
                    message=f"{rule}: {msg}")
            for rule, _sev, msg in structure_findings(workbook_path, cfg=cfg)]


@register("required_blocks", "config blocks a set of checks needs")
def required_blocks_mechanism(checks):
    from syngen.menu import required_blocks, required_features
    blocks = sorted(required_blocks(checks))
    feats = sorted(required_features(checks))
    msg = "required config blocks: " + (", ".join(blocks) or "none")
    if feats:
        msg += "; features: " + ", ".join(feats)
    return [Finding(kind="required_blocks", severity="info", message=msg)]
