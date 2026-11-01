"""Parity: the Python pipeline must give the same answers as the spreadsheet formulas."""

import numpy as np
import pandas as pd
import pytest

from scorecard.features import FEATURE_COLUMNS, build_features
from scorecard.scoring import score_suppliers
from tests.excel_reference import build_reference_workbook, read_model, recalculate, soffice_path

pytestmark = [
    pytest.mark.excel,
    pytest.mark.skipif(soffice_path() is None, reason="LibreOffice is not installed"),
]


def _boundary_rows(cfg) -> pd.DataFrame:
    """Values sitting exactly on, just below and just above every band edge, where an
    off-by-one in the lookup rule would show up."""
    rows = []
    for f in cfg.features:
        for t in f.thresholds:
            for v in (t, t * 0.999999 if t else 0.0, t * 1.000001 + (1e-9 if t == 0 else 0)):
                base = {c: 0.5 for c in FEATURE_COLUMNS}
                base[f.name] = float(v)
                rows.append(base)
    df = pd.DataFrame(rows)
    df.insert(0, "supplier_id", [f"EDGE-{i:03d}" for i in range(len(df))])
    df.insert(1, "n_orders", 10)
    df["open_orders"] = 0
    return df


def test_python_matches_excel_formulas(tmp_path, demo_orders, cfg):
    real = build_features(demo_orders)
    features = pd.concat([real, _boundary_rows(cfg)], ignore_index=True)
    scored = score_suppliers(features, cfg)
    scored = scored[scored["risk_tier"] != "Insufficient data"].copy()

    # The spreadsheet is fed the same features, in the same order, as the pipeline scored.
    sheet_input = scored[["supplier_id"] + FEATURE_COLUMNS].reset_index(drop=True)
    book = tmp_path / "legacy_model.xlsx"
    build_reference_workbook(sheet_input, cfg, book)
    excel = read_model(recalculate(book, tmp_path))

    assert len(excel) == len(scored) > 150
    assert excel["supplier_id"].tolist() == scored["supplier_id"].tolist()
    for f in cfg.features:
        np.testing.assert_allclose(
            excel[f"{f.name}_points"].astype(float), scored[f"{f.name}_points"], atol=1e-9, err_msg=f.name
        )
    np.testing.assert_allclose(excel["score"].astype(float), scored["score"], atol=1e-9)
    assert excel["risk_tier"].tolist() == scored["risk_tier"].tolist()
