import io

import pytest

from scorecard.features import InputError, build_features, load_orders
from tests.conftest import HAND_ROWS


def test_hand_calculated_features(hand_orders):
    f = build_features(hand_orders).set_index("supplier_id").loc["S1"]
    assert f["n_orders"] == 4                       # the open order is excluded
    assert f["open_orders"] == 1
    assert f["on_time_rate"] == pytest.approx(2 / 4)    # po1 on time, po3 early
    assert f["avg_delay_days"] == pytest.approx((2 + 4) / 2)  # late orders only
    assert f["fill_rate"] == pytest.approx(490 / 500)
    assert f["reject_rate"] == pytest.approx(10 / 490)
    assert f["price_variance"] == pytest.approx((36 + 40) / 3900)


def test_supplier_with_no_late_orders_has_zero_delay():
    rows = (
        "supplier_id,po_id,promised_date,delivered_date,qty_ordered,qty_received,qty_rejected,unit_price,invoiced_amount\n"
        "A,1,2026-02-01,2026-01-30,10,10,0,1,10\n"
    )
    f = build_features(load_orders(io.StringIO(rows)))
    assert f.loc[0, "avg_delay_days"] == 0
    assert f.loc[0, "on_time_rate"] == 1


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda t: t.replace("qty_rejected", "rejected_qty", 1), "Missing required column"),
        (lambda t: t.replace(",po2,", ",po1,"), "Duplicate po_id"),
        (lambda t: t.replace(",90,9,", ",9,90,"), "qty_rejected is larger"),
        (lambda t: t.replace(",100,100,0,10,1000\n", ",abc,100,0,10,1000\n", 1), "non-numeric"),
        (lambda t: t.replace(",100,0,10,1000\n", ",100,-1,10,1000\n", 1), "negative"),
        (lambda t: t.replace("2026-01-14", "2026-01-14").replace("S1,po4,2026-01-10", "S1,po4,"), "promised_date"),
    ],
)
def test_bad_input_gives_a_plain_message(mutate, message):
    with pytest.raises(InputError, match=message):
        load_orders(io.StringIO(mutate(HAND_ROWS)))


def test_empty_file_is_rejected():
    header = HAND_ROWS.splitlines()[0] + "\n"
    with pytest.raises(InputError, match="no rows"):
        load_orders(io.StringIO(header))
