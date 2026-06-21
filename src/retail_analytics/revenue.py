"""Trading-year KPIs and a revenue bridge.

Splits the change in identified-customer sales into

    sales = active customers x orders per customer x average order value

Plain differences on a product leave an interaction term, so this uses LMDI-I
(log-mean Divisia index), where the contributions add up to the total change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import warehouse

TY_SQL = """
SELECT
    d.trading_year,
    SUM(o.order_value)                                          AS gross_sales,
    COUNT(*)                                                    AS orders,
    SUM(o.order_value) FILTER (WHERE NOT o.is_guest)            AS customer_sales,
    COUNT(*) FILTER (WHERE NOT o.is_guest)                      AS customer_orders,
    COUNT(DISTINCT o.customer_id)                               AS active_customers,
    SUM(o.order_value) FILTER (WHERE o.is_guest)                AS guest_sales
FROM fct_orders o
JOIN dim_date d ON d.date_key = o.date_key
WHERE d.trading_year IN (2010, 2011)
GROUP BY 1
ORDER BY 1
"""

NET_SQL = """
SELECT d.trading_year, SUM(l.revenue) AS net_revenue,
       -SUM(l.revenue) FILTER (WHERE l.line_type = 'cancellation') AS cancelled
FROM fct_order_lines l JOIN dim_date d ON d.date_key = l.date_key
WHERE d.trading_year IN (2010, 2011)
GROUP BY 1 ORDER BY 1
"""


def trading_year_summary(db=None) -> pd.DataFrame:
    kw = {"db_path": db} if db else {}
    ty = warehouse.query(TY_SQL, **kw).merge(warehouse.query(NET_SQL, **kw), on="trading_year")
    ty["aov"] = ty["gross_sales"] / ty["orders"]
    ty["orders_per_customer"] = ty["customer_orders"] / ty["active_customers"]
    ty["customer_aov"] = ty["customer_sales"] / ty["customer_orders"]
    ty["cancellation_rate"] = ty["cancelled"] / ty["gross_sales"]
    return ty.set_index("trading_year")


def _log_mean(a: float, b: float) -> float:
    return a if np.isclose(a, b) else (a - b) / (np.log(a) - np.log(b))


def lmdi_bridge(before: dict[str, float], after: dict[str, float], total_key: str) -> pd.Series:
    """Additive LMDI-I decomposition of ``total = prod(drivers)``.

    ``before`` / ``after`` map driver names (and ``total_key``) to values.
    Returns each driver's contribution to the change in the total; the
    contributions sum to ``after[total_key] - before[total_key]``.
    """
    w = _log_mean(after[total_key], before[total_key])
    drivers = [k for k in before if k != total_key]
    return pd.Series({k: w * np.log(after[k] / before[k]) for k in drivers})


def revenue_bridge(ty: pd.DataFrame) -> pd.DataFrame:
    """TY2010 -> TY2011 bridge: identified-customer drivers plus guest sales."""
    b, a = ty.loc[2010], ty.loc[2011]

    def drivers(r):
        return {
            "customer_sales": r["customer_sales"],
            "Active customers": r["active_customers"],
            "Orders per customer": r["orders_per_customer"],
            "Average order value": r["customer_aov"],
        }

    contrib = lmdi_bridge(drivers(b), drivers(a), "customer_sales")
    contrib["Guest (no-ID) sales"] = a["guest_sales"] - b["guest_sales"]
    out = contrib.rename("contribution_gbp").to_frame()
    out["pct_of_base"] = out["contribution_gbp"] / b["gross_sales"]
    return out


def new_vs_returning(db=None) -> pd.DataFrame:
    kw = {"db_path": db} if db else {}
    m = warehouse.table("kpi_monthly", **kw)
    m["month"] = pd.to_datetime(m["month"])
    return m
