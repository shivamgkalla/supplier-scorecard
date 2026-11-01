from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml

from scorecard.features import build_features, validate_orders
from scorecard.generate import generate_orders
from scorecard.scoring import (
    INSUFFICIENT,
    ConfigError,
    band_lookup,
    load_config,
    score_suppliers,
)


def test_band_lookup_matches_approximate_match_rule():
    thresholds, points = (0, 0.5, 0.9), (10, 50, 90)
    values = np.array([0.0, 0.4999, 0.5, 0.7, 0.9, 5.0])
    assert band_lookup(values, thresholds, points).tolist() == [10, 10, 50, 50, 90, 90]


def test_hand_calculated_score(hand_orders, cfg):
    one_order_ok = replace(cfg, min_orders=1)
    row = score_suppliers(build_features(hand_orders), one_order_ok).iloc[0]
    assert row["on_time_rate_points"] == 25
    assert row["avg_delay_days_points"] == 60
    assert row["fill_rate_points"] == 100
    assert row["reject_rate_points"] == 80
    assert row["price_variance_points"] == 80
    # 30*25/100 + 15*60/100 + 20*100/100 + 20*80/100 + 15*80/100
    assert row["score"] == pytest.approx(64.5)
    assert row["risk_tier"] == "High"
    assert row["main_driver"] == "on_time_rate"
    assert row["points_lost"] == pytest.approx(22.5)


def test_thin_history_is_not_scored(hand_orders, cfg):
    row = score_suppliers(build_features(hand_orders), cfg).iloc[0]   # 4 orders < 5
    assert row["risk_tier"] == INSUFFICIENT
    assert np.isnan(row["score"])
    assert row["main_driver"] == ""


def test_scores_are_between_0_and_100_and_sorted(demo_orders, cfg):
    scored = score_suppliers(build_features(demo_orders), cfg).dropna(subset=["score"])
    assert scored["score"].between(0, 100).all()
    assert scored["score"].is_monotonic_increasing


def test_same_input_gives_identical_output(cfg):
    a = score_suppliers(build_features(validate_orders(generate_orders(60, 3))), cfg)
    b = score_suppliers(build_features(validate_orders(generate_orders(60, 3))), cfg)
    assert a.equals(b)


def _config_with(tmp_path: Path, edit) -> Path:
    raw = yaml.safe_load((Path(__file__).parent.parent / "config" / "scorecard.yaml").read_text())
    edit(raw)
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda r: r["features"]["fill_rate"].update(weight=25), "add up to 100"),
        (lambda r: r["features"]["fill_rate"].update(bands=[[0.1, 0], [0.9, 100]]), "first threshold"),
        (lambda r: r["features"]["fill_rate"].update(bands=[[0, 0], [0.9, 100], [0.8, 50]]), "increasing"),
        (lambda r: r["features"]["fill_rate"].update(bands=[[0, 0], [0.9, 140]]), "between 0 and 100"),
        (lambda r: r["features"].pop("reject_rate"), "missing from the config"),
    ],
)
def test_bad_config_is_rejected(tmp_path, edit, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_config_with(tmp_path, edit))


def test_changing_a_weight_changes_the_score_without_code_changes(tmp_path, demo_orders, cfg):
    def shift(raw):
        raw["features"]["on_time_rate"]["weight"] = 40
        raw["features"]["price_variance"]["weight"] = 5

    features = build_features(demo_orders)
    base = score_suppliers(features, cfg).set_index("supplier_id")["score"]
    alt = score_suppliers(features, load_config(_config_with(tmp_path, shift))).set_index("supplier_id")["score"]
    assert not base.dropna().equals(alt.dropna().reindex(base.dropna().index))
