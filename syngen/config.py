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
    if not isinstance(mapping, dict):
        raise ConfigError(f"{label}: expected an object, got "
                          f"{type(mapping).__name__}")
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
        # F28: optional per-territory / per-region overrides {min, max}
        pot_overrides = potential.get("by_territory") or \
            potential.get("by_region")
        if pot_overrides is not None:
            if not isinstance(pot_overrides, dict):
                raise ConfigError(
                    "market_potential_usd.by_territory/by_region must be a "
                    "map of unit to {min, max}")
            if potential.get("by_territory"):
                known_units = set(cfg["accounts"].get("territories", {}))
                label = "by_territory"
            else:
                known_units = set(cfg["accounts"].get("regions", {}))
                label = "by_region"
            for r, r_spec in pot_overrides.items():
                if r not in known_units:
                    raise ConfigError(
                        f"market_potential_usd.{label}['{r}'] is not a "
                        f"known unit (known: {sorted(known_units)})")
                rlo, rhi = r_spec.get("min"), r_spec.get("max")
                if rlo is None or rhi is None or not (0 <= rlo < rhi):
                    raise ConfigError(
                        f"market_potential_usd.{label}['{r}'] must be "
                        "{min, max} with 0 <= min < max")

    # M4 domain B: deal_duration_days is [lo, hi] or {means: [...], spread}
    dur = cfg["opportunities"]["deal_duration_days"]
    if isinstance(dur, dict):
        means = dur.get("means")
        if not isinstance(means, list) or not means:
            raise ConfigError(
                "deal_duration_days.means must be a non-empty per-quarter list")
        if len(means) != len(labels):
            raise ConfigError(
                f"deal_duration_days.means needs one value per quarter "
                f"({len(labels)} expected, got {len(means)})")
        spread = dur.get("spread", 10)
        if not (isinstance(spread, (int, float)) and spread > 0):
            raise ConfigError("deal_duration_days.spread must be positive")

    mult = cfg["opportunities"].get("volume_multipliers")
    if mult is not None:
        if not isinstance(mult, list) or len(mult) != len(labels):
            raise ConfigError(
                f"volume_multipliers needs one value per quarter "
                f"({len(labels)} expected)")
        if any(float(m) <= 0 for m in mult):
            raise ConfigError("volume_multipliers must be positive")

    # M5 iter 1 extensions -----------------------------------------------

    medians = cfg["opportunities"]["deal_size_lognormal"].get(
        "medians_by_quarter")
    if medians is not None:
        if not isinstance(medians, list) or len(medians) != len(labels):
            raise ConfigError(
                f"deal_size_lognormal.medians_by_quarter needs one value per "
                f"quarter ({len(labels)} expected)")
        if any(float(m) <= 0 for m in medians):
            raise ConfigError("deal_size_lognormal medians must be positive")

    icp_share = cfg["accounts"].get("icp_share")
    if icp_share is not None and not (0 <= float(icp_share) <= 1):
        raise ConfigError("accounts.icp_share must be between 0 and 1")

    icp_w = cfg["accounts"].get("icp_sampling_weights_by_quarter")
    if icp_w is not None:
        if not isinstance(icp_w, dict) or set(icp_w) != {"icp", "non_icp"}:
            raise ConfigError(
                "accounts.icp_sampling_weights_by_quarter must have exactly "
                "the keys 'icp' and 'non_icp'")
        for key, curve in icp_w.items():
            if not isinstance(curve, list) or len(curve) != len(labels):
                raise ConfigError(
                    f"icp_sampling_weights_by_quarter['{key}'] needs one "
                    f"weight per quarter ({len(labels)} expected)")
            if any(float(w) <= 0 for w in curve):
                raise ConfigError("icp sampling weights must be positive")

    for dim in ("regions", "segments"):
        for name, val in cfg["accounts"].get(dim, {}).items():
            if isinstance(val, dict):
                curve = val.get("weights_by_quarter")
                if not isinstance(curve, list) or len(curve) != len(labels):
                    raise ConfigError(
                        f"accounts.{dim}['{name}'].weights_by_quarter needs "
                        f"one weight per quarter ({len(labels)} expected)")
                if any(float(w) < 0 for w in curve):
                    raise ConfigError(
                        f"accounts.{dim}['{name}'] weights must be >= 0")
        # per-quarter weights across the dimension should sum to ~1
        curves = [v["weights_by_quarter"] for v in cfg["accounts"].get(dim, {}).values()
                  if isinstance(v, dict)]
        if curves:
            for qi in range(len(labels)):
                total = sum(float(c[qi]) for c in curves)
                static = [float(v) for v in cfg["accounts"][dim].values()
                          if not isinstance(v, dict)]
                total += sum(static)
                if abs(total - 1.0) > 0.05:
                    raise ConfigError(
                        f"accounts.{dim} weights (incl. by-quarter curves) "
                        f"sum to {total:.3f} at quarter index {qi}; expected ~1.0")

    out = cfg["opportunities"].get("outlier_deals")
    if out is not None:
        share = out.get("share")
        multiplier = out.get("multiplier")
        if share is None or not (0 < float(share) < 0.5):
            raise ConfigError("outlier_deals.share must be between 0 and 0.5")
        if multiplier is None or float(multiplier) <= 1:
            raise ConfigError("outlier_deals.multiplier must be > 1")

    curves = discount["base_by_quarter"]
    if not isinstance(curves, dict) or not curves:
        raise ConfigError(
            "discount.base_by_quarter must map regions to per-quarter "
            "curves")
    for region, curve in curves.items():
        if not isinstance(curve, list):
            raise ConfigError(
                f"discount.base_by_quarter['{region}'] must be a list of "
                "per-quarter values")
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

    # optional WS3 aggregate-targets block (M4); M5 iter 2 adds territory
    # plan units alongside segments
    quota = cfg.get("quota")
    if quota is not None:
        by_segment = quota.get("by_segment")
        by_territory = quota.get("by_territory")
        by_motion = quota.get("by_motion")
        dims = {"segment": by_segment, "territory": by_territory,
                "motion": by_motion}
        chosen = [k for k, v in dims.items() if v]
        if len(chosen) != 1:
            raise ConfigError(
                "quota must define exactly one of by_segment / "
                "by_territory / by_motion")
        dim_name = chosen[0]
        targets = dims[dim_name]
        if not isinstance(targets, dict) or not targets:
            raise ConfigError(
                f"quota.by_{dim_name} must define at least one unit curve")
        if dim_name == "motion":
            known_units = {"New Logo", "Expansion"}
        else:
            known_units = set(cfg["accounts"].get(
                "territories" if dim_name == "territory" else "segments", {}))
        for unit, curve in targets.items():
            if unit not in known_units:
                raise ConfigError(
                    f"quota.by_{dim_name}['{unit}'] is not a known account "
                    f"{dim_name} (known: {sorted(known_units)})")
            if len(curve) != len(labels):
                raise ConfigError(
                    f"quota.by_{dim_name}['{unit}'] needs one target per "
                    f"quarter ({len(labels)} expected, got {len(curve)})")
            if any(float(t) <= 0 for t in curve):
                raise ConfigError(f"quota targets must be positive ('{unit}')")
        ratios = quota.get("attainment") or \
            quota.get("attainment_by_segment", {})
        if not isinstance(ratios, dict):
            raise ConfigError("quota.attainment must be a dict")
        for unit, ratio in ratios.items():
            if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
                raise ConfigError(
                    f"quota.attainment['{unit}'] must be a number, got "
                    f"{type(ratio).__name__}")
            if unit not in targets:
                raise ConfigError(
                    f"quota.attainment['{unit}'] has no matching "
                    f"by_{dim_name} entry")
            if not (0 < float(ratio) < 3):
                raise ConfigError(
                    f"quota.attainment['{unit}'] must be a sane "
                    "ratio (0 < r < 3)")
        # WS8 mixtures (#25): ex-outlier attainment ratios
        ex_ratios = quota.get("attainment_ex_outliers")
        if ex_ratios is not None:
            if not isinstance(ex_ratios, dict):
                raise ConfigError(
                    "quota.attainment_ex_outliers must be a dict")
            for unit, ratio in ex_ratios.items():
                if unit not in targets:
                    raise ConfigError(
                        f"quota.attainment_ex_outliers['{unit}'] has no "
                        f"matching by_{dim_name} entry")
                if not isinstance(ratio, (int, float)) or \
                        isinstance(ratio, bool) or \
                        not (0 < float(ratio) < 3):
                    raise ConfigError(
                        f"quota.attainment_ex_outliers['{unit}'] must be a "
                        "sane ratio (0 < r < 3)")

    # M5 iteration 2: products, territories -------------------------------

    terr = cfg["accounts"].get("territories")
    if terr is not None:
        regions = cfg["accounts"].get("regions", {})
        if not isinstance(terr, dict) or not terr:
            raise ConfigError("accounts.territories must be a non-empty map")
        seen_terr = set()
        for tname, members in terr.items():
            if tname in seen_terr:
                raise ConfigError(f"duplicate territory '{tname}'")
            seen_terr.add(tname)
            if not isinstance(members, list) or not members:
                raise ConfigError(
                    f"accounts.territories['{tname}'] must list regions")
            for r in members:
                if r not in regions:
                    raise ConfigError(
                        f"accounts.territories['{tname}'] references unknown "
                        f"region '{r}' (known: {sorted(regions)})")

    prods = cfg.get("products")
    if prods is not None:
        catalog = prods.get("catalog")
        if not isinstance(catalog, list) or not catalog:
            raise ConfigError("products.catalog must be a non-empty list")
        ids = [p.get("id") for p in catalog]
        if any(not i for i in ids) or len(set(ids)) != len(ids):
            raise ConfigError("products.catalog entries need unique 'id's")
        tiers = {p.get("tier") for p in catalog}
        if None in tiers or not all(isinstance(t, str) for t in tiers):
            raise ConfigError("products.catalog entries need a 'tier'")
        margin = prods.get("margin_by_tier", {})
        missing = tiers - set(margin)
        if missing:
            raise ConfigError(
                f"products.margin_by_tier missing tiers: {sorted(missing)}")
        for t, m in margin.items():
            if not (0 < float(m) < 1):
                raise ConfigError(
                    f"products.margin_by_tier['{t}'] must be between 0 and 1")
        for p in catalog:
            share = p.get("share")
            if isinstance(share, dict):
                curve = share.get("weights_by_quarter")
                if not isinstance(curve, list) or len(curve) != len(labels):
                    raise ConfigError(
                        f"products.catalog['{p['id']}'].share."
                        f"weights_by_quarter needs one weight per quarter "
                        f"({len(labels)} expected)")
                if any(float(w) < 0 for w in curve):
                    raise ConfigError(
                        f"product '{p['id']}' weights must be >= 0")
            elif not (0 <= float(share or 0) <= 1):
                raise ConfigError(
                    f"products.catalog['{p['id']}'].share must be 0..1")
        curves = [p["share"]["weights_by_quarter"] for p in catalog
                  if isinstance(p.get("share"), dict)]
        if curves:
            static = [float(p["share"]) for p in catalog
                      if not isinstance(p.get("share"), dict)]
            for qi in range(len(labels)):
                total = sum(float(c[qi]) for c in curves) + sum(static)
                if abs(total - 1.0) > 0.05:
                    raise ConfigError(
                        f"product shares sum to {total:.3f} at quarter "
                        f"index {qi}; expected ~1.0")
        price_mult = prods.get("price_multiplier_by_tier", {})
        unknown = set(price_mult) - tiers
        if unknown:
            raise ConfigError(
                f"price_multiplier_by_tier has unknown tiers: {sorted(unknown)}")
        if any(float(v) <= 0 for v in price_mult.values()):
            raise ConfigError("price multipliers must be positive")
        disc_delta = prods.get("discount_delta_pp_by_tier", {})
        unknown = set(disc_delta) - tiers
        if unknown:
            raise ConfigError(
                f"discount_delta_pp_by_tier has unknown tiers: "
                f"{sorted(unknown)}")
        infl = prods.get("cogs_inflation_by_quarter")
        if infl is not None:
            if not isinstance(infl, list) or len(infl) != len(labels):
                raise ConfigError(
                    f"cogs_inflation_by_quarter needs one value per quarter "
                    f"({len(labels)} expected)")
            if any(float(v) <= 0 for v in infl):
                raise ConfigError("cogs inflation factors must be positive")

    # M5 iter 3 (P4): open-pipeline state machine --------------------------
    pipe = cfg.get("pipeline")
    if pipe is not None:
        stages = pipe.get("stage_names")
        if not isinstance(stages, list) or not stages or \
                not all(isinstance(s, str) and s for s in stages):
            raise ConfigError(
                "pipeline.stage_names must be a non-empty list of strings")
        weights = pipe.get("stage_weights")
        if weights is not None:
            if not isinstance(weights, list) or len(weights) != len(stages):
                raise ConfigError(
                    "pipeline.stage_weights needs one weight per stage")
            if any(float(w) < 0 for w in weights):
                raise ConfigError("pipeline.stage_weights must be >= 0")
        for key, lo in (("share_open_by_quarter", 0.0),
                        ("slippage_rate_by_quarter", 0.0)):
            curve = pipe.get(key)
            if curve is None:
                continue
            if not isinstance(curve, list) or len(curve) != len(labels):
                raise ConfigError(
                    f"pipeline.{key} needs one value per quarter "
                    f"({len(labels)} expected)")
            hi = 1.0 if key == "slippage_rate_by_quarter" else 0.95
            if any(not (lo <= float(v) <= hi) for v in curve):
                raise ConfigError(
                    f"pipeline.{key} values must be within [{lo}, {hi}]")
        if pipe.get("share_open_by_quarter") is None:
            raise ConfigError(
                "pipeline.share_open_by_quarter is required when a "
                "pipeline block is present")

    # M5 iter 4 (WS1 rest): rep/capacity block ------------------------------
    cap = cfg.get("capacity")
    if cap is not None:
        by_territory = cap.get("by_territory")
        by_region = cap.get("by_region")
        if bool(by_territory) == bool(by_region):
            raise ConfigError(
                "capacity must define exactly one of by_territory / by_region")
        dim_name = "territory" if by_territory else "region"
        units = by_territory or by_region
        if not isinstance(units, dict) or not units:
            raise ConfigError(
                f"capacity.by_{dim_name} must define at least one unit spec")
        known_units = set(cfg["accounts"].get(
            "territories" if by_territory else "regions", {}))
        for unit, spec in units.items():
            label = f"capacity.by_{dim_name}['{unit}']"
            if unit not in known_units:
                raise ConfigError(
                    f"{label} is not a known account {dim_name} "
                    f"(known: {sorted(known_units)})")
            if not isinstance(spec, dict):
                raise ConfigError(f"{label} must be an object")
            hc = spec.get("headcount_plan")
            if not isinstance(hc, list) or len(hc) != len(labels):
                raise ConfigError(
                    f"{label}.headcount_plan needs one value per quarter "
                    f"({len(labels)} expected)")
            if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
                   for v in hc):
                raise ConfigError(
                    f"{label}.headcount_plan values must be positive integers")
            actual = spec.get("headcount_actual")
            if actual is not None:
                if not isinstance(actual, list) or len(actual) != len(labels):
                    raise ConfigError(
                        f"{label}.headcount_actual needs one value per "
                        f"quarter ({len(labels)} expected)")
                if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                       for v in actual):
                    raise ConfigError(
                        f"{label}.headcount_actual values must be "
                        "non-negative integers")
            ramping = spec.get("ramping_reps_by_quarter")
            if ramping is not None:
                if not isinstance(ramping, list) or len(ramping) != len(labels):
                    raise ConfigError(
                        f"{label}.ramping_reps_by_quarter needs one value "
                        f"per quarter ({len(labels)} expected)")
                for qi, v in enumerate(ramping):
                    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                        raise ConfigError(
                            f"{label}.ramping_reps_by_quarter values must be "
                            "non-negative integers")
                    ref = actual if actual is not None else hc
                    if v > ref[qi]:
                        raise ConfigError(
                            f"{label}.ramping_reps_by_quarter[{qi}] exceeds "
                            "actual headcount that quarter")
            prod = spec.get("ramp_productivity_pct")
            if prod is not None and not (0 < float(prod) <= 100):
                raise ConfigError(
                    f"{label}.ramp_productivity_pct must be within (0, 100]")

    # M5 iter 4 (WS7): ownership-history block ------------------------------
    own = cfg.get("ownership")
    if own is not None:
        if not isinstance(own, dict):
            raise ConfigError("ownership must be an object")
        for key in ("unowned_share_by_quarter", "churn_share_by_quarter"):
            curve = own.get(key)
            if curve is None:
                continue
            if not isinstance(curve, list) or len(curve) != len(labels):
                raise ConfigError(
                    f"ownership.{key} needs one value per quarter "
                    f"({len(labels)} expected)")
            if any(not (0 <= float(v) <= 1) for v in curve):
                raise ConfigError(f"ownership.{key} values must be 0..1")
        pool = own.get("owner_pool")
        if pool is not None:
            if not isinstance(pool, list) or \
                    not all(isinstance(p, str) and p for p in pool) or not pool:
                raise ConfigError(
                    "ownership.owner_pool must be a non-empty list of names")

    # M5 iter 4 (WS7): activity, forecast blocks ----------------------------
    act = cfg.get("activity")
    if act is not None:
        means = act.get("mean_touches_per_account_by_quarter")
        if not isinstance(means, list) or len(means) != len(labels):
            raise ConfigError(
                f"activity.mean_touches_per_account_by_quarter needs one "
                f"value per quarter ({len(labels)} expected)")
        if any(float(m) < 0 for m in means):
            raise ConfigError("activity mean touches must be >= 0")
    fc = cfg.get("forecast")
    if fc is not None:
        ratios = fc.get("commit_ratio_by_quarter")
        if not isinstance(ratios, list) or len(ratios) != len(labels):
            raise ConfigError(
                f"forecast.commit_ratio_by_quarter needs one value per "
                f"quarter ({len(labels)} expected)")
        if any(float(r) <= 0 for r in ratios):
            raise ConfigError("commit ratios must be positive")
        shares = fc.get("commit_share_of_won_by_quarter")
        if shares is not None:
            if not isinstance(shares, list) or len(shares) != len(labels):
                raise ConfigError(
                    f"forecast.commit_share_of_won_by_quarter needs one "
                    f"value per quarter ({len(labels)} expected)")
            if any(not (0 <= float(s) <= 1) for s in shares):
                raise ConfigError(
                    "commit shares must be within [0, 1]")
        bias = fc.get("low_activity_bias")
        if bias is not None and float(bias) < 0:
            raise ConfigError("low_activity_bias must be >= 0")

    # M5 iter 4 (WS8 mixtures / demand response) ----------------------------
    pr = cfg.get("pricing_response")
    if pr is not None:
        curve = pr.get("price_change_pct_by_quarter")
        if not isinstance(curve, list) or len(curve) != len(labels):
            raise ConfigError(
                f"pricing_response.price_change_pct_by_quarter needs one "
                f"value per quarter ({len(labels)} expected)")
        elas = pr.get("elasticity")
        if elas is None or float(elas) >= 0:
            raise ConfigError(
                "pricing_response.elasticity must be negative "
                "(higher price -> lower conversion)")
        mit = pr.get("potential_mitigation")
        if mit is not None and not (0 <= float(mit) <= 1):
            raise ConfigError("potential_mitigation must be within [0, 1]")

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
