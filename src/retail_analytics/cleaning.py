"""Data-quality audit and cleaning rules.

Philosophy: *flag, don't delete*. Rows that are genuinely wrong (exact
duplicates, the overlap between the two Excel sheets, unparseable records) are
removed. Everything else is kept and labelled with a ``line_type`` so each
downstream metric can choose what it includes — and so the choice is visible
in SQL instead of hidden in a preprocessing script.

Every rule appends an entry to an audit log (rows touched + revenue touched),
which is rendered to ``docs/data_quality_report.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Stock codes that are not merchandise: postage, fees, manual adjustments,
# vouchers, test SKUs. Identified by profiling every non-numeric code.
NON_PRODUCT_PATTERN = (
    r"^(?:POST|DOT|M|m|C2|C3|D|S|B|BANK CHARGES|ADJUST\d*|AMAZONFEE|CRUK|PADS"
    r"|TEST\d+|gift_\d+_\d+)$"
)

SHEET_BOUNDARY = pd.Timestamp("2010-12-01")

LINE_TYPES = (
    "sale",                 # a real product sold to a customer
    "cancellation",         # a 'C' invoice reversing (part of) a sale
    "non_product",          # postage, fees, discounts, vouchers, test SKUs
    "stock_adjustment",     # warehouse write-offs: damaged / lost / found stock
    "bad_debt_adjustment",  # 'A' invoices: accounting write-offs
    "zero_price",           # free-of-charge items
    "invalid",              # anything that fits none of the above
)


@dataclass
class AuditLog:
    steps: list[dict] = field(default_factory=list)

    def record(self, step: str, rule: str, rows: int, revenue: float, action: str) -> None:
        self.steps.append(
            {"step": step, "rule": rule, "rows": int(rows), "revenue_gbp": float(revenue), "action": action}
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.steps)


def _revenue(df: pd.DataFrame) -> pd.Series:
    return df["quantity"].astype("float64") * df["unit_price"]


def remove_sheet_overlap(df: pd.DataFrame, log: AuditLog) -> pd.DataFrame:
    """The 2009-10 sheet runs to 9 Dec 2010 and the 2010-11 sheet starts on 1 Dec 2010,
    so 1-9 Dec 2010 appears twice. A naive ``concat`` double-counts those nine days."""
    is_first = df["source_sheet"].str.contains("2009")
    overlap = is_first & (df["invoice_date"] >= SHEET_BOUNDARY)
    log.record(
        "Remove sheet overlap",
        "Rows dated >= 2010-12-01 in the 2009-2010 sheet (duplicated in the 2010-2011 sheet)",
        overlap.sum(), _revenue(df[overlap]).sum(), "removed",
    )
    return df.loc[~overlap].reset_index(drop=True)


def drop_invalid(df: pd.DataFrame, log: AuditLog) -> pd.DataFrame:
    bad = df["invoice_date"].isna() | df["quantity"].isna() | df["unit_price"].isna() | df["stock_code"].isna()
    log.record("Drop unparseable", "Missing date / quantity / price / stock code", bad.sum(), 0.0, "removed")
    return df.loc[~bad].reset_index(drop=True)


def drop_exact_duplicates(df: pd.DataFrame, log: AuditLog) -> pd.DataFrame:
    """Identical line items (same invoice, product, quantity, price, timestamp, customer).
    These are almost always double-scans; a genuine repeat would be a quantity change."""
    cols = [c for c in df.columns if c != "source_sheet"]
    dup = df.duplicated(subset=cols, keep="first")
    log.record("Drop exact duplicates", "Fully identical line items within an invoice", dup.sum(),
               _revenue(df[dup]).sum(), "removed")
    return df.loc[~dup].reset_index(drop=True)


def classify_lines(df: pd.DataFrame) -> pd.Series:
    """Assign every row exactly one ``line_type``. Order of the rules matters."""
    inv = df["invoice"]
    qty = df["quantity"]
    price = df["unit_price"]
    is_non_product = df["stock_code"].str.match(NON_PRODUCT_PATTERN, na=False)

    conditions = [
        inv.str.startswith("A"),
        is_non_product,
        inv.str.startswith("C"),
        (qty < 0) & (price == 0),
        (qty > 0) & (price == 0),
        (qty > 0) & (price > 0),
    ]
    choices = ["bad_debt_adjustment", "non_product", "cancellation", "stock_adjustment", "zero_price", "sale"]
    return pd.Series(np.select(conditions, choices, default="invalid"), index=df.index, dtype="string")


def canonical_descriptions(df: pd.DataFrame) -> pd.Series:
    """1,200+ stock codes carry several descriptions (typos, warehouse notes such as
    'damaged', renamed items). Use the most frequent description seen on *sale* lines."""
    sales = df[df["line_type"] == "sale"].dropna(subset=["description"])
    canon = (
        sales.groupby(["stock_code", "description"]).size()
        .sort_values(ascending=False)
        .reset_index()
        .drop_duplicates("stock_code")
        .set_index("stock_code")["description"]
    )
    return df["stock_code"].map(canon).fillna(df["description"])


def match_cancellations(df: pd.DataFrame) -> pd.DataFrame:
    """Link each cancellation to the most recent earlier sale of the same product, by
    the same customer, for the same quantity. Lets us (a) flag sales that were later
    reversed — e.g. the single 80,995-unit order cancelled 12 minutes later — and
    (b) measure time-to-cancel. Unmatched cancellations are partial or pre-period returns."""
    df = df.copy()
    df["qty_abs"] = df["quantity"].abs().astype("int64")
    df["_row"] = np.arange(len(df))

    sales = df[(df["line_type"] == "sale") & df["customer_id"].notna()][
        ["_row", "customer_id", "stock_code", "qty_abs", "invoice_date"]
    ].rename(columns={"_row": "sale_row", "invoice_date": "sale_date"})
    canc = df[(df["line_type"] == "cancellation") & df["customer_id"].notna()][
        ["_row", "customer_id", "stock_code", "qty_abs", "invoice_date"]
    ]

    sales = sales.sort_values("sale_date")
    canc = canc.sort_values("invoice_date")
    for frame in (sales, canc):
        frame["customer_id"] = frame["customer_id"].astype("int64")
        frame["stock_code"] = frame["stock_code"].astype(str)

    matched = pd.merge_asof(
        canc, sales,
        left_on="invoice_date", right_on="sale_date",
        by=["customer_id", "stock_code", "qty_abs"],
        direction="backward",
    ).dropna(subset=["sale_row"])
    # One sale can only be reversed once: keep the earliest cancellation per sale.
    matched = matched.sort_values("invoice_date").drop_duplicates("sale_row")

    df["was_cancelled"] = False
    df.loc[df["_row"].isin(matched["sale_row"].astype("int64")), "was_cancelled"] = True
    df["matched_cancellation"] = False
    df.loc[df["_row"].isin(matched["_row"]), "matched_cancellation"] = True
    hours = (matched["invoice_date"] - matched["sale_date"]).dt.total_seconds() / 3600
    df.attrs["hours_to_cancel"] = hours.to_numpy()
    return df.drop(columns=["qty_abs", "_row"])


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, AuditLog]:
    log = AuditLog()
    log.record("Raw input", "Both sheets of online_retail_II.xlsx stacked", len(raw), _revenue(raw).sum(), "loaded")

    df = remove_sheet_overlap(raw, log)
    df = drop_invalid(df, log)
    df = drop_exact_duplicates(df, log)

    df["line_type"] = classify_lines(df)
    df["revenue"] = _revenue(df)
    for lt in LINE_TYPES:
        part = df[df["line_type"] == lt]
        log.record("Classify", f"line_type = {lt}", len(part), part["revenue"].sum(), "flagged")

    df["description"] = canonical_descriptions(df)
    df = match_cancellations(df)
    hours = df.attrs.get("hours_to_cancel", np.array([]))
    n_canc = int((df["line_type"] == "cancellation").sum())
    n_match = int(df["matched_cancellation"].sum())
    log.record("Match cancellations", "Cancellation linked to its originating sale (same customer, SKU, qty)",
               n_match, df.loc[df["was_cancelled"], "revenue"].sum(), "flagged")

    df["is_guest"] = df["customer_id"].isna()
    guest_sales = df[(df["line_type"] == "sale") & df["is_guest"]]
    log.record("Guest checkouts", "Sale lines with no Customer ID (kept for revenue, excluded from customer analytics)",
               len(guest_sales), guest_sales["revenue"].sum(), "flagged")

    df["invoice_day"] = df["invoice_date"].dt.normalize()
    cols = [
        "invoice", "invoice_date", "invoice_day", "customer_id", "is_guest", "country",
        "stock_code", "description", "quantity", "unit_price", "revenue",
        "line_type", "was_cancelled", "matched_cancellation",
    ]
    df = df[cols]
    df.attrs = {
        "n_cancellations": n_canc,
        "n_matched": n_match,
        "median_hours_to_cancel": float(np.median(hours)) if len(hours) else float("nan"),
    }
    return df, log


def render_quality_report(log: AuditLog, clean_df: pd.DataFrame, path) -> None:
    """Write a human-readable Markdown data-quality report."""
    audit = log.to_frame()
    lines = [
        "# Data Quality Report",
        "",
        "_Generated by `python -m retail_analytics.pipeline` — do not edit by hand._",
        "",
        "Every cleaning rule, how many rows it touched and how much revenue (GBP, quantity × price) "
        "those rows carry. **Removed** rows are genuinely wrong; **flagged** rows are kept with a "
        "`line_type` so each metric decides what to include.",
        "",
        "| Step | Rule | Rows | Revenue (£) | Action |",
        "|---|---|---:|---:|---|",
    ]
    for r in audit.itertuples():
        lines.append(f"| {r.step} | {r.rule} | {r.rows:,} | {r.revenue_gbp:,.0f} | {r.action} |")

    attrs = clean_df.attrs
    sales = clean_df[clean_df["line_type"] == "sale"]
    lines += [
        "",
        "## Notes",
        "",
        f"- Final table: **{len(clean_df):,} rows**, of which **{len(sales):,} sale lines** across "
        f"**{sales['invoice'].nunique():,} invoices** and **{sales['customer_id'].nunique():,} identified customers**.",
        f"- {attrs.get('n_matched', 0):,} of {attrs.get('n_cancellations', 0):,} cancellation lines "
        f"({attrs.get('n_matched', 0) / max(attrs.get('n_cancellations', 1), 1):.0%}) were matched to the exact sale "
        f"they reversed; median time from sale to cancellation was "
        f"{attrs.get('median_hours_to_cancel', float('nan')):,.0f} hours. Unmatched cancellations are partial "
        "returns or reverse sales made before the data window.",
        "- Customer IDs are missing on ~23% of raw rows. These look like guest / manual orders: they are kept "
        "in revenue KPIs and excluded from anything customer-level (cohorts, RFM, CLV).",
        "- The two largest single lines in the data (80,995 and 74,215 units) were both cancelled within "
        "minutes. They are kept and netted out by their cancellations rather than deleted by hand.",
        "- 1,200+ stock codes have more than one description; the most frequent description on sale lines "
        "is used as the canonical product name.",
    ]
    path.write_text("\n".join(lines) + "\n")
