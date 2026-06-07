"""Cohort retention: do customers come back, and is that getting better or worse?"""

from __future__ import annotations

import pandas as pd

from . import warehouse


def retention_matrix(db=None, max_months: int = 12) -> pd.DataFrame:
    """Cohort (rows) x months-since-first-order (columns) -> share of cohort active."""
    kw = {"db_path": db} if db else {}
    cr = warehouse.table("cohort_retention", **kw)
    cr["cohort_month"] = pd.to_datetime(cr["cohort_month"])
    mat = cr.pivot(index="cohort_month", columns="months_since_first", values="retention_rate")
    return mat.loc[:, [c for c in mat.columns if c <= max_months]]


def cohort_sizes(db=None) -> pd.Series:
    kw = {"db_path": db} if db else {}
    cr = warehouse.table("cohort_retention", **kw)
    cr["cohort_month"] = pd.to_datetime(cr["cohort_month"])
    return cr.drop_duplicates("cohort_month").set_index("cohort_month")["cohort_customers"]


def compare_cohort_vintages(mat: pd.DataFrame, horizons=(1, 3, 6)) -> pd.DataFrame:
    """Average retention at fixed horizons for 2010 vs 2011 acquisition cohorts.

    The Dec-2009 cohort is excluded: it is left-censored (it contains every
    pre-existing customer who happened to order in the first month of data),
    so its "retention" describes the established base, not new customers.
    """
    m = mat.loc[mat.index > "2009-12-01"]
    rows = {}
    for label, sel in {"2010 cohorts (Jan-Jun)": (m.index >= "2010-01-01") & (m.index < "2010-07-01"),
                       "2011 cohorts (Jan-Jun)": (m.index >= "2011-01-01") & (m.index < "2011-07-01")}.items():
        rows[label] = {f"M{h}": m.loc[sel, h].mean() for h in horizons}
    return pd.DataFrame(rows).T


def established_base_retention(mat: pd.DataFrame) -> float:
    """Share of the Dec-2009 (largely pre-existing) base still ordering 12 months later."""
    return float(mat.loc[pd.Timestamp("2009-12-01"), 12])
