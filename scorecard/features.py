"""Turn purchase-order rows into one row of features per supplier."""

from __future__ import annotations

from typing import IO, Union

import pandas as pd

REQUIRED_COLUMNS = [
    "supplier_id",
    "po_id",
    "promised_date",
    "delivered_date",
    "qty_ordered",
    "qty_received",
    "qty_rejected",
    "unit_price",
    "invoiced_amount",
]
NUMERIC_COLUMNS = ["qty_ordered", "qty_received", "qty_rejected", "unit_price", "invoiced_amount"]
FEATURE_COLUMNS = ["on_time_rate", "avg_delay_days", "fill_rate", "reject_rate", "price_variance"]


class InputError(ValueError):
    """The uploaded data cannot be scored. The message says why, in plain words."""


def load_orders(source: Union[str, IO]) -> pd.DataFrame:
    try:
        df = pd.read_csv(source)
    except Exception as exc:  # unreadable or not a CSV
        raise InputError(f"Could not read the file as CSV: {exc}") from exc
    return validate_orders(df)


def validate_orders(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise InputError(f"Missing required column(s): {', '.join(missing)}")
    if df.empty:
        raise InputError("The file has no rows.")

    df = df.copy()
    df["supplier_id"] = df["supplier_id"].astype("string").str.strip()
    if df["supplier_id"].isna().any() or (df["supplier_id"] == "").any():
        raise InputError("Some rows have an empty supplier_id.")
    if df["po_id"].duplicated().any():
        dupes = df.loc[df["po_id"].duplicated(), "po_id"].head(3).tolist()
        raise InputError(f"Duplicate po_id values found, for example: {dupes}")

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            bad = int(df[col].isna().sum())
            raise InputError(f"Column '{col}' has {bad} missing or non-numeric value(s).")
        if (df[col] < 0).any():
            raise InputError(f"Column '{col}' contains negative values.")
    if (df["qty_rejected"] > df["qty_received"]).any():
        raise InputError("qty_rejected is larger than qty_received on some rows.")

    for col in ["promised_date", "delivered_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    if df["promised_date"].isna().any():
        raise InputError("Some rows have a missing or invalid promised_date.")
    return df


def build_features(orders: pd.DataFrame) -> pd.DataFrame:
    """One row per supplier. Orders without a delivered_date are still open and are
    left out of every measure; `open_orders` reports how many were skipped."""
    open_mask = orders["delivered_date"].isna()
    open_counts = orders[open_mask].groupby("supplier_id").size()
    done = orders[~open_mask].copy()

    days_late = (done["delivered_date"] - done["promised_date"]).dt.days
    done["late_days"] = days_late.clip(lower=0)
    done["is_on_time"] = days_late <= 0
    done["is_late"] = days_late > 0
    done["expected_amount"] = done["qty_received"] * done["unit_price"]
    done["abs_price_gap"] = (done["invoiced_amount"] - done["expected_amount"]).abs()

    g = done.groupby("supplier_id")
    agg = g.agg(
        n_orders=("po_id", "count"),
        on_time=("is_on_time", "sum"),
        late_orders=("is_late", "sum"),
        late_days=("late_days", "sum"),
        ordered=("qty_ordered", "sum"),
        received=("qty_received", "sum"),
        rejected=("qty_rejected", "sum"),
        expected=("expected_amount", "sum"),
        gap=("abs_price_gap", "sum"),
    )

    out = pd.DataFrame(index=agg.index)
    out["n_orders"] = agg["n_orders"]
    out["on_time_rate"] = agg["on_time"] / agg["n_orders"]
    out["avg_delay_days"] = (agg["late_days"] / agg["late_orders"]).where(agg["late_orders"] > 0, 0.0)
    out["fill_rate"] = (agg["received"] / agg["ordered"]).where(agg["ordered"] > 0, 0.0)
    out["reject_rate"] = (agg["rejected"] / agg["received"]).where(agg["received"] > 0, 0.0)
    out["price_variance"] = (agg["gap"] / agg["expected"]).where(agg["expected"] > 0, 0.0)
    out["open_orders"] = open_counts.reindex(out.index).fillna(0).astype(int)
    return out.reset_index()
