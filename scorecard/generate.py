"""Synthetic purchase-order data.

All data in this project is generated here from a seed. No real supplier,
customer or company data is used anywhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# (share of suppliers, on-time probability, mean late days, fill mean,
#  reject probability per unit, invoice noise sd)
ARCHETYPES = {
    "reliable": (0.45, 0.97, 1.0, 0.995, 0.004, 0.002),
    "average": (0.35, 0.82, 3.0, 0.95, 0.025, 0.012),
    "problem": (0.20, 0.55, 8.0, 0.84, 0.08, 0.045),
}


def generate_orders(n_suppliers: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = list(ARCHETYPES)
    shares = [ARCHETYPES[n][0] for n in names]
    rows = []
    for i in range(n_suppliers):
        supplier_id = f"SUP-{i + 1:04d}"
        kind = ARCHETYPES[rng.choice(names, p=shares)]
        _, p_on_time, mean_late, fill_mean, p_reject, price_sd = kind
        # Suppliers differ within a group too, so scores form a continuous spread.
        p_on_time = float(np.clip(p_on_time + rng.normal(0, 0.09), 0.2, 1.0))
        mean_late = max(0.5, mean_late * float(rng.uniform(0.6, 1.6)))
        fill_mean = float(np.clip(fill_mean + rng.normal(0, 0.03), 0.7, 1.0))
        p_reject = max(0.0005, p_reject * float(rng.uniform(0.4, 1.8)))
        price_sd = max(0.0005, price_sd * float(rng.uniform(0.4, 1.8)))
        # A few suppliers have too little history to be scored fairly.
        n_orders = int(rng.integers(1, 5)) if rng.random() < 0.06 else int(rng.integers(8, 70))
        for j in range(n_orders):
            order_date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=int(rng.integers(0, 240)))
            lead = int(rng.integers(5, 30))
            promised = order_date + pd.Timedelta(days=lead)
            if rng.random() < p_on_time:
                delay = -int(rng.integers(0, 3))
            else:
                delay = max(1, int(rng.exponential(mean_late)))
            delivered = promised + pd.Timedelta(days=delay)
            qty_ordered = int(rng.integers(50, 2000))
            fill = float(np.clip(rng.normal(fill_mean, 0.04), 0.3, 1.05))
            qty_received = int(round(qty_ordered * fill))
            qty_rejected = int(rng.binomial(qty_received, p_reject)) if qty_received else 0
            unit_price = round(float(rng.uniform(2, 180)), 2)
            expected = qty_received * unit_price
            invoiced = round(expected * (1 + rng.normal(0, price_sd)), 2)
            rows.append(
                {
                    "supplier_id": supplier_id,
                    "po_id": f"PO-{supplier_id[-4:]}-{j + 1:03d}",
                    "order_date": order_date.date().isoformat(),
                    "promised_date": promised.date().isoformat(),
                    "delivered_date": delivered.date().isoformat(),
                    "qty_ordered": qty_ordered,
                    "qty_received": qty_received,
                    "qty_rejected": qty_rejected,
                    "unit_price": unit_price,
                    "invoiced_amount": invoiced,
                }
            )
    return pd.DataFrame(rows)
