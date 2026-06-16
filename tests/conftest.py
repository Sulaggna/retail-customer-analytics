"""Small, hand-built fixtures so the test suite runs in seconds without the 45 MB dataset."""

import pandas as pd
import pytest


def _row(invoice, code, qty, price, ts, cust, country="United Kingdom", desc=None, sheet="Year 2010-2011"):
    return {
        "invoice": invoice, "stock_code": code, "description": desc or f"ITEM {code}",
        "quantity": qty, "invoice_date": pd.Timestamp(ts), "unit_price": price,
        "customer_id": cust, "country": country, "source_sheet": sheet,
    }


@pytest.fixture
def raw_sample() -> pd.DataFrame:
    rows = [
        # a normal sale, also present in BOTH sheets (the 1-9 Dec 2010 overlap)
        _row("536365", "85123A", 6, 2.55, "2010-12-01 08:26", 17850, sheet="Year 2009-2010"),
        _row("536365", "85123A", 6, 2.55, "2010-12-01 08:26", 17850),
        # an exact duplicate line inside one sheet
        _row("536366", "22633", 6, 1.85, "2010-12-02 09:00", 17850),
        _row("536366", "22633", 6, 1.85, "2010-12-02 09:00", 17850),
        # a sale that is later cancelled in full
        _row("536400", "21730", 10, 4.25, "2010-12-03 10:00", 13047),
        _row("C536401", "21730", -10, 4.25, "2010-12-03 10:30", 13047),
        # postage (non-product), a write-off, a free item, a bad-debt adjustment
        _row("536402", "POST", 1, 18.0, "2010-12-03 11:00", 12583),
        _row("536403", "21000", -50, 0.0, "2010-12-03 12:00", None, desc="damaged"),
        _row("536404", "21001", 2, 0.0, "2010-12-03 12:30", 12583),
        _row("A536405", "B", 1, -500.0, "2010-12-03 13:00", None, desc="Adjust bad debt"),
        # a guest checkout (no customer id)
        _row("536406", "22633", 3, 1.85, "2010-12-04 14:00", None),
    ]
    df = pd.DataFrame(rows)
    df["customer_id"] = df["customer_id"].astype("Int64")
    df["quantity"] = df["quantity"].astype("Int64")
    for c in ("invoice", "stock_code", "description", "country"):
        df[c] = df[c].astype("string")
    return df
