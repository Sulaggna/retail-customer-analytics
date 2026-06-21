"""Run the whole analysis end to end: raw Excel -> clean data -> warehouse -> analyses -> report.

    python -m retail_analytics.pipeline            # everything (~1 min after the first download)
    python -m retail_analytics.pipeline --skip-ingest

Outputs
    data/warehouse.duckdb          star schema + KPI views (gitignored)
    reports/figures/*.png          every chart in the README
    reports/tables/*.csv           the numbers behind them
    reports/metrics.json           headline numbers quoted in the README / summary
    docs/data_quality_report.md    generated cleaning audit
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import basket, clv, cleaning, cohorts, figures, forecasting, ingest, paths, revenue, segmentation, warehouse


def _step(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# csv floats are rounded: duckdb sums in parallel, so the last few digits
# otherwise change from run to run

def _r(x, nd=4):
    """Round for JSON, converting numpy scalars."""
    if isinstance(x, (np.floating, float)):
        return round(float(x), nd)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def run(skip_ingest: bool = False) -> dict:
    paths.ensure_dirs()
    F, T = paths.FIGURES_DIR, paths.TABLES_DIR
    m: dict = {}

    # 1. Ingest + clean --------------------------------------------------------
    if not skip_ingest or not paths.RAW_PARQUET.exists():
        _step("Ingest: download + Excel -> Parquet")
        ingest.main()
    _step("Clean + audit")
    raw = pd.read_parquet(paths.RAW_PARQUET)
    clean, log = cleaning.clean(raw)
    clean.to_parquet(paths.CLEAN_PARQUET, index=False)
    cleaning.render_quality_report(log, clean, paths.DOCS_DIR / "data_quality_report.md")
    audit = log.to_frame()
    audit.to_csv(float_format="%.4f", path_or_buf=T / "data_quality_audit.csv", index=False)
    figures.data_quality_waterfall(audit, F / "01_data_quality.png")
    sales = clean[clean["line_type"] == "sale"]
    m["data"] = {
        "raw_rows": int(len(raw)),
        "rows_removed_overlap": int(audit.loc[audit.step == "Remove sheet overlap", "rows"].iloc[0]),
        "rows_removed_duplicates": int(audit.loc[audit.step == "Drop exact duplicates", "rows"].iloc[0]),
        "overlap_revenue_double_counted_gbp": _r(audit.loc[audit.step == "Remove sheet overlap", "revenue_gbp"].iloc[0], 0),
        "clean_sale_lines": int(len(sales)),
        "invoices": int(sales["invoice"].nunique()),
        "customers": int(sales["customer_id"].nunique()),
        "products": int(sales["stock_code"].nunique()),
        "countries": int(sales["country"].nunique()),
        "guest_share_of_sales": _r(sales.loc[sales["is_guest"], "revenue"].sum() / sales["revenue"].sum()),
        "cancellations_matched_share": _r(clean.attrs["n_matched"] / clean.attrs["n_cancellations"]),
        "date_min": str(clean["invoice_date"].min().date()),
        "date_max": str(clean["invoice_date"].max().date()),
    }

    # 2. Warehouse --------------------------------------------------------------
    _step("Build DuckDB warehouse")
    m["warehouse_models"] = warehouse.build()

    # 3. Revenue -----------------------------------------------------------------
    _step("Revenue KPIs + bridge")
    kpi = warehouse.table("kpi_monthly")
    kpi.to_csv(float_format="%.4f", path_or_buf=T / "kpi_monthly.csv", index=False)
    ty = revenue.trading_year_summary()
    ty.to_csv(float_format="%.4f", path_or_buf=T / "trading_year_summary.csv")
    bridge = revenue.revenue_bridge(ty)
    bridge.to_csv(float_format="%.4f", path_or_buf=T / "revenue_bridge.csv")
    figures.monthly_revenue_yoy(kpi, F / "02_monthly_revenue.png")
    figures.revenue_bridge(bridge, ty, F / "03_revenue_bridge.png")
    figures.new_vs_returning(kpi, F / "04_new_vs_returning.png")
    k = kpi.assign(month=pd.to_datetime(kpi["month"]))
    nov = k.loc[k["month"].dt.month == 11, "net_revenue"].mean()
    avg = k.loc[(k["month"] >= "2010-01-01") & (k["month"] <= "2011-11-01"), "net_revenue"].mean()
    new10 = k.loc[k["month"].dt.year == 2010, "new_customer_sales"].sum()
    new11 = k.loc[(k["month"].dt.year == 2011) & (k["month"] <= "2011-11-01"), "new_customer_sales"].sum()
    new10_cmp = k.loc[(k["month"] >= "2010-01-01") & (k["month"] <= "2010-11-01"), "new_customer_sales"].sum()
    newc10 = k.loc[(k["month"] >= "2010-01-01") & (k["month"] <= "2010-11-01"), "new_customers"].sum()
    newc11 = k.loc[(k["month"] >= "2011-01-01") & (k["month"] <= "2011-11-01"), "new_customers"].sum()
    m["revenue"] = {
        "net_revenue_ty2010": _r(ty.loc[2010, "net_revenue"], 0),
        "net_revenue_ty2011": _r(ty.loc[2011, "net_revenue"], 0),
        "net_revenue_growth": _r(ty.loc[2011, "net_revenue"] / ty.loc[2010, "net_revenue"] - 1),
        "gross_sales_growth": _r(ty.loc[2011, "gross_sales"] / ty.loc[2010, "gross_sales"] - 1),
        "aov_ty2010": _r(ty.loc[2010, "aov"], 2), "aov_ty2011": _r(ty.loc[2011, "aov"], 2),
        "orders_per_customer_ty2010": _r(ty.loc[2010, "orders_per_customer"], 3),
        "orders_per_customer_ty2011": _r(ty.loc[2011, "orders_per_customer"], 3),
        "active_customers_ty2010": int(ty.loc[2010, "active_customers"]),
        "active_customers_ty2011": int(ty.loc[2011, "active_customers"]),
        "cancellation_rate_ty2010": _r(ty.loc[2010, "cancellation_rate"]),
        "cancellation_rate_ty2011": _r(ty.loc[2011, "cancellation_rate"]),
        "bridge_gbp": {k_: _r(v, 0) for k_, v in bridge["contribution_gbp"].items()},
        "november_vs_avg_month": _r(nov / avg, 2),
        "new_customer_sales_jan_nov_2010": _r(new10_cmp, 0),
        "new_customer_sales_jan_nov_2011": _r(new11, 0),
        "new_customer_sales_change": _r(new11 / new10_cmp - 1),
        "new_customers_jan_nov_2010": int(newc10), "new_customers_jan_nov_2011": int(newc11),
    }
    _ = new10

    country = warehouse.table("kpi_country")
    country.to_csv(float_format="%.4f", path_or_buf=T / "kpi_country.csv", index=False)
    figures.country_dumbbell(country, F / "12_international_markets.png")
    c11 = country[country["trading_year"] == 2011]
    m["revenue"]["uk_share_ty2011"] = _r(c11.loc[c11.country == "United Kingdom", "revenue_share"].iloc[0])
    m["revenue"]["intl_growth_ty2011"] = _r(
        c11.loc[c11.country != "United Kingdom", "net_revenue"].sum()
        / country[(country.trading_year == 2010) & (country.country != "United Kingdom")]["net_revenue"].sum() - 1)

    timing = warehouse.table("order_timing")
    figures.order_timing(timing, F / "11_order_timing.png")

    # 4. Customers: cohorts, RFM, concentration -----------------------------------
    _step("Cohorts + RFM segmentation")
    mat = cohorts.retention_matrix()
    sizes = cohorts.cohort_sizes()
    mat.to_csv(float_format="%.4f", path_or_buf=T / "cohort_retention.csv")
    figures.cohort_heatmap(mat, sizes, F / "05_cohort_retention.png")
    vint = cohorts.compare_cohort_vintages(mat)
    vint.to_csv(float_format="%.4f", path_or_buf=T / "cohort_vintages.csv")
    m["cohorts"] = {
        "vintages": {i: {c: _r(v) for c, v in row.items()} for i, row in vint.iterrows()},
        "established_base_m12_retention": _r(cohorts.established_base_retention(mat)),
        "new_cohort_avg_m1_retention_2010_2011": _r(mat.loc[(mat.index >= "2010-01-01") & (mat.index <= "2011-10-01"), 1].mean()),
    }
    gaps = warehouse.query("SELECT quantile_cont(days_since_prev_order, [0.5, 0.75, 0.9]) AS q FROM purchase_intervals")["q"].iloc[0]
    m["cohorts"]["days_between_orders_p50_p75_p90"] = [float(g) for g in gaps]

    rfm = segmentation.rfm_table()
    seg = segmentation.segment_summary(rfm)
    seg.to_csv(float_format="%.4f", path_or_buf=T / "rfm_segments.csv")
    figures.segment_shares(seg, F / "06_rfm_segments.png")
    km = segmentation.kmeans_check(rfm)
    km["profile"].to_csv(float_format="%.4f", path_or_buf=T / "kmeans_profile.csv")
    m["segments"] = {
        "customers_segmented": int(len(rfm)),
        "summary": {s: {"customer_share": _r(r.customer_share), "revenue_share": _r(r.revenue_share),
                        "median_recency_days": _r(r.median_recency_days, 0)} for s, r in seg.iterrows()},
        "kmeans_best_k": int(km["best_k"]),
        "kmeans_silhouette": {int(k_): _r(v, 3) for k_, v in km["silhouette"].items()},
    }

    prod = warehouse.table("product_performance")
    prod.head(50).to_csv(float_format="%.4f", path_or_buf=T / "top_products.csv", index=False)
    pc = segmentation.concentration(prod.set_index("stock_code")["net_revenue"])
    cust = warehouse.query("SELECT customer_id, net_revenue FROM dim_customer").set_index("customer_id")["net_revenue"]
    cc = segmentation.concentration(cust)
    figures.concentration(pc, cc, F / "07_concentration.png")
    m["concentration"] = {
        "top20_products_revenue_share": _r(segmentation.share_at(pc, 0.2)),
        "top20_customers_revenue_share": _r(segmentation.share_at(cc, 0.2)),
        "top1pct_customers_revenue_share": _r(segmentation.share_at(cc, 0.01)),
    }

    # 5. CLV -------------------------------------------------------------------------
    _step("CLV: BG/NBD + Gamma-Gamma")
    tx = clv.load_transactions()
    val = clv.holdout_validation(tx)
    val["buckets"].to_csv(float_format="%.4f", path_or_buf=T / "clv_holdout_buckets.csv")
    figures.clv_validation(val["buckets"], val["metrics"], F / "08_clv_validation.png")
    sens = clv.calibration_sensitivity(tx)
    sens.to_csv(float_format="%.4f", path_or_buf=T / "clv_calibration_sensitivity.csv", index=False)
    scored = clv.predict_clv(tx)
    seg_clv = (scored.join(rfm.set_index("customer_id")["segment"], how="inner")
               .groupby("segment", observed=True)
               .agg(customers=("clv_12m", "size"), clv_total=("clv_12m", "sum"),
                    clv_mean=("clv_12m", "mean"), median_p_alive=("p_alive", "median")))
    # BG/NBD assumes customers can only "die" right after a purchase, so one-time buyers
    # always get P(alive) = 1. Report P(alive) for repeat buyers only, where it is informative.
    repeat = scored[scored["x"] > 0].join(rfm.set_index("customer_id")["segment"], how="inner")
    seg_clv["p_alive_repeat"] = repeat.groupby("segment", observed=True)["p_alive"].median()
    seg_clv.to_csv(float_format="%.4f", path_or_buf=T / "clv_by_segment.csv")
    figures.clv_by_segment(seg_clv, F / "09_clv_by_segment.png")
    at_risk = seg_clv.loc[["At Risk", "Can't Lose Them"], "clv_total"].sum()
    m["clv"] = {k_: (_r(v) if not isinstance(v, dict) else {kk: _r(vv) for kk, vv in v.items()})
                for k_, v in val["metrics"].items()}
    m["clv"]["calibration_sensitivity"] = [{k_: _r(v) for k_, v in row.items()} for row in sens.to_dict("records")]
    m["clv"]["predicted_12m_revenue_total"] = _r(scored["clv_12m"].sum(), 0)
    m["clv"]["predicted_12m_at_risk_plus_cant_lose"] = _r(at_risk, 0)
    m["clv"]["by_segment_gbp"] = {s: _r(v, 0) for s, v in seg_clv["clv_total"].items()}

    # 6. Basket ------------------------------------------------------------------------
    _step("Market basket analysis")
    baskets = basket.load_baskets()
    rules = basket.pair_rules(baskets, min_support=0.01)
    n_baskets = rules.attrs["n_baskets"]
    rules = basket.dedupe_symmetric(basket.add_descriptions(rules))
    rules.attrs["n_baskets"] = n_baskets
    rules.to_csv(float_format="%.4f", path_or_buf=T / "association_rules.csv", index=False)
    figures.top_rules(rules, F / "10_basket_rules.png")
    m["basket"] = {
        "baskets": int(n_baskets),
        "rules_support_ge_1pct": int(len(rules)),
        "median_lift": _r(rules["lift"].median(), 2),
        "top50_same_collection_share": _r(basket.same_collection_share(rules.head(50))),
        "top_rule": {"a": rules.iloc[0]["antecedent_name"], "b": rules.iloc[0]["consequent_name"],
                     "lift": _r(rules.iloc[0]["lift"], 1), "confidence": _r(rules.iloc[0]["confidence"])},
    }

    # 7. Forecast ----------------------------------------------------------------------
    _step("Forecast backtest")
    series = forecasting.weekly_series()
    bt = forecasting.backtest(series)
    scores = forecasting.score(bt)
    scores.to_csv(float_format="%.4f", path_or_buf=T / "forecast_scores.csv")
    final = forecasting.final_forecast(series)
    final.to_csv(float_format="%.4f", path_or_buf=T / "forecast_next_8_weeks.csv")
    figures.forecast(series, bt, final, scores, F / "13_forecast.png")
    m["forecast"] = {
        "weeks": int(len(series)),
        "scores": {mdl: {c: _r(v) for c, v in row.items()} for mdl, row in scores.iterrows()},
        "ensemble_improvement_vs_seasonal_naive": _r(1 - scores.loc["ensemble", "WAPE (1-4 wk)"]
                                                     / scores.loc["seasonal_naive", "WAPE (1-4 wk)"]),
    }

    paths.METRICS_JSON.write_text(json.dumps(m, indent=2, default=str) + "\n")
    _step(f"Done -> {paths.METRICS_JSON.relative_to(paths.ROOT)}")
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-ingest", action="store_true", help="reuse data/processed/raw_transactions.parquet")
    run(skip_ingest=ap.parse_args().skip_ingest)


if __name__ == "__main__":
    main()
