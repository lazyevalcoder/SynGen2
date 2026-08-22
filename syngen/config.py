"""BOM-safe config loading and schema enforcement for SynGen artifacts."""
import json
from pathlib import Path


class ConfigError(ValueError):
    pass


def _read_text(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ConfigError(f"{path}: UTF-8 BOM detected - configs must be BOM-free")
    return raw.decode("utf-8")


def load_json(path):
    text = _read_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON ({e})") from e


REQUIRED_SIMULATOR_KEYS = {
    "seed": int,
    "time_model": dict,
    "output": dict,
    "accounts": dict,
    "opportunities": dict,
}
REQUIRED_TIME_MODEL_KEYS = {"fiscal_year", "quarter_labels", "quarter_end_dates"}
REQUIRED_OPPORTUNITY_KEYS = {
    "per_quarter", "win_rate", "win_rate_jitter", "owners",
    "deal_duration_days", "close_clustering", "deal_size_lognormal", "discount",
}
REQUIRED_DISCOUNT_KEYS = {
    "base_by_quarter", "noise_sd_pp", "end_of_quarter_boost_pp",
    "end_of_quarter_window_days", "min_pct", "max_pct",
}


def _check_keys(mapping, required, label):
    missing = set(required) - set(mapping)
    if missing:
        raise ConfigError(f"{label}: missing keys {sorted(missing)}")


def load_simulator(path):
    return validate_simulator_doc(load_json(path), source=str(path))


def validate_simulator_doc(cfg, source="simulator"):
    _check_keys(cfg, REQUIRED_SIMULATOR_KEYS, source)
    _check_keys(cfg["time_model"], REQUIRED_TIME_MODEL_KEYS, "time_model")
    _check_keys(cfg["opportunities"], REQUIRED_OPPORTUNITY_KEYS, "opportunities")
    discount = cfg["opportunities"]["discount"]
    _check_keys(discount, REQUIRED_DISCOUNT_KEYS, "opportunities.discount")

    labels = cfg["time_model"]["quarter_labels"]
    ends = cfg["time_model"]["quarter_end_dates"]
    if len(labels) != len(ends):
        raise ConfigError("time_model: quarter_labels and quarter_end_dates length mismatch")

    potential = cfg["accounts"].get("market_potential_usd")
    if potential is not None:
        lo, hi = potential.get("min"), potential.get("max")
        if lo is None or hi is None or not (0 <= lo < hi):
            raise ConfigError(
                "accounts.market_potential_usd must be {min, max} with 0 <= min < max")

    curves = discount["base_by_quarter"]
    if not curves:
        raise ConfigError("discount.base_by_quarter must define at least one region curve")
    curve_len = len(next(iter(curves.values())))
    for region, curve in curves.items():
        if len(curve) != curve_len:
            raise ConfigError(f"discount.base_by_quarter['{region}'] length != {curve_len}")
    if curve_len != len(labels):
        raise ConfigError("discount base curves must have one value per quarter")

    lo, hi = discount["min_pct"], discount["max_pct"]
    if not (0 <= lo < hi):
        raise ConfigError("discount bounds must satisfy 0 <= min_pct < max_pct")

    # optional WS3 aggregate-targets block (M4)
    quota = cfg.get("quota")
    if quota is not None:
        by_segment = quota.get("by_segment")
        if not isinstance(by_segment, dict) or not by_segment:
            raise ConfigError("quota.by_segment must define at least one segment curve")
        segments = cfg["accounts"].get("segments", {})
        for seg, curve in by_segment.items():
            if seg not in segments:
                raise ConfigError(
                    f"quota.by_segment['{seg}'] is not a known account segment "
                    f"(known: {sorted(segments)})")
            if len(curve) != len(labels):
                raise ConfigError(
                    f"quota.by_segment['{seg}'] needs one target per quarter "
                    f"({len(labels)} expected, got {len(curve)})")
            if any(float(t) <= 0 for t in curve):
                raise ConfigError(f"quota targets must be positive ('{seg}')")
        ratios = quota.get("attainment_by_segment", {})
        if not isinstance(ratios, dict):
            raise ConfigError("quota.attainment_by_segment must be a dict")
        for seg, ratio in ratios.items():
            if seg not in by_segment:
                raise ConfigError(
                    f"quota.attainment_by_segment['{seg}'] has no matching "
                    "by_segment entry")
            if not (0 < float(ratio) < 3):
                raise ConfigError(
                    f"quota.attainment_by_segment['{seg}'] must be a sane "
                    "ratio (0 < r < 3)")

    return cfg


REQUIRED_CRITERIA_KEYS = {"definitions", "criteria"}


def load_criteria(path):
    return validate_criteria_doc(load_json(path))


def validate_criteria_doc(doc):
    _check_keys(doc, REQUIRED_CRITERIA_KEYS, "criteria document")
    seen = set()
    for c in doc["criteria"]:
        for key in ("id", "name", "check", "params"):
            if key not in c:
                raise ConfigError(f"criterion missing '{key}': {c}")
        if c["id"] in seen:
            raise ConfigError(f"duplicate criterion id: {c['id']}")
        seen.add(c["id"])
    return doc
