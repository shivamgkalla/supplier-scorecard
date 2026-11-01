import io

import pandas as pd
import pytest

from scorecard.features import load_orders, validate_orders
from scorecard.generate import generate_orders
from scorecard.scoring import load_config

# One supplier whose measures were worked out by hand (see test_features.py).
HAND_ROWS = """supplier_id,po_id,promised_date,delivered_date,qty_ordered,qty_received,qty_rejected,unit_price,invoiced_amount
S1,po1,2026-01-10,2026-01-10,100,100,0,10,1000
S1,po2,2026-01-10,2026-01-12,100,90,9,10,936
S1,po3,2026-01-10,2026-01-09,200,200,0,5,1000
S1,po4,2026-01-10,2026-01-14,100,100,1,10,960
S1,po5,2026-01-10,,50,0,0,10,0
"""


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture()
def hand_orders():
    return load_orders(io.StringIO(HAND_ROWS))


@pytest.fixture(scope="session")
def demo_raw():
    """Generator output exactly as written to CSV (dates still text)."""
    return generate_orders(n_suppliers=120, seed=11)


@pytest.fixture(scope="session")
def demo_orders(demo_raw):
    """The same rows after the validation every real upload goes through."""
    return validate_orders(demo_raw)


@pytest.fixture(scope="session")
def demo_csv(demo_raw):
    return demo_raw.to_csv(index=False).encode()
