"""Score suppliers from their features, using the rules in config/scorecard.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
import yaml

from .features import FEATURE_COLUMNS

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "scorecard.yaml"
INSUFFICIENT = "Insufficient data"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Feature:
    name: str
    weight: float
    thresholds: tuple
    points: tuple


@dataclass(frozen=True)
class Config:
    min_orders: int
    features: tuple
    tier_thresholds: tuple
    tier_names: tuple


def load_config(path: Union[str, Path] = DEFAULT_CONFIG) -> Config:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    features = []
    for name in FEATURE_COLUMNS:
        if name not in raw.get("features", {}):
            raise ConfigError(f"Feature '{name}' is missing from the config.")
        spec = raw["features"][name]
        thresholds = tuple(float(t) for t, _ in spec["bands"])
        points = tuple(float(p) for _, p in spec["bands"])
        _check_bands(name, thresholds, points)
        features.append(Feature(name, float(spec["weight"]), thresholds, points))

    total = sum(f.weight for f in features)
    if abs(total - 100.0) > 1e-9:
        raise ConfigError(f"Feature weights must add up to 100, they add up to {total}.")

    tiers = raw["risk_tiers"]
    tier_thresholds = tuple(float(t) for t, _ in tiers)
    tier_names = tuple(str(n) for _, n in tiers)
    _check_bands("risk_tiers", tier_thresholds, (0,) * len(tier_thresholds))
    return Config(int(raw["min_orders"]), tuple(features), tier_thresholds, tier_names)


def _check_bands(name: str, thresholds: tuple, points: tuple) -> None:
    if not thresholds or thresholds[0] != 0:
        raise ConfigError(f"'{name}': the first threshold must be 0.")
    if any(b <= a for a, b in zip(thresholds, thresholds[1:])):
        raise ConfigError(f"'{name}': thresholds must be strictly increasing.")
    if any(p < 0 or p > 100 for p in points):
        raise ConfigError(f"'{name}': points must be between 0 and 100.")


def band_lookup(values: np.ndarray, thresholds: tuple, outputs: tuple) -> np.ndarray:
    """Approximate-match lookup: the output of the highest threshold <= value."""
    idx = np.searchsorted(np.asarray(thresholds), values, side="right") - 1
    return np.asarray(outputs)[np.clip(idx, 0, len(outputs) - 1)]


def score_suppliers(features: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add per-feature points, the overall score, the risk tier and the main driver.

    The overall score is sum(weight * points) / 100, so it runs from 0 to 100.
    Suppliers with fewer than `min_orders` delivered orders get no score.
    """
    out = features.copy()
    for col in FEATURE_COLUMNS:
        if out[col].isna().any() or (out[col] < 0).any():
            raise ValueError(f"Feature '{col}' has missing or negative values.")

    shortfall = {}
    score = np.zeros(len(out))
    for f in cfg.features:
        pts = band_lookup(out[f.name].to_numpy(dtype=float), f.thresholds, f.points)
        out[f"{f.name}_points"] = pts
        score += f.weight * pts / 100.0
        shortfall[f.name] = f.weight * (100.0 - pts) / 100.0
    out["score"] = score

    tier = band_lookup(score, cfg.tier_thresholds, cfg.tier_names).astype(object)
    scored = out["n_orders"] >= cfg.min_orders
    out["risk_tier"] = np.where(scored, tier, INSUFFICIENT)
    out.loc[~scored, "score"] = np.nan

    gap = pd.DataFrame(shortfall, index=out.index)
    driver = gap.idxmax(axis=1).where(gap.max(axis=1) > 0, "none")
    out["main_driver"] = driver.where(scored, "")
    out["points_lost"] = gap.max(axis=1).where(scored)
    return out.sort_values(["score", "supplier_id"], na_position="last").reset_index(drop=True)


def tier_counts(scored: pd.DataFrame, cfg: Config) -> dict:
    order = list(cfg.tier_names)[::-1] + [INSUFFICIENT]
    counts = scored["risk_tier"].value_counts().to_dict()
    return {name: int(counts.get(name, 0)) for name in order}
