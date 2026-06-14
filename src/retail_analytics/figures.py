"""Every chart in the report. Each function takes tidy inputs and writes one PNG.

Titles state the *takeaway*, not the chart type ("Revenue was flat because...",
not "Revenue by month").
"""

from __future__ import annotations

import string
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import plotting as P

P.apply_style()


def _finish(fig, ax, title, sub=None):
    ax.set_title(title, pad=26 if sub else 14)
    if sub:
        P.subtitle(ax, sub)
    fig.tight_layout()


# ----------------------------------------------------------------------------- 1. data quality
def data_quality_waterfall(audit: pd.DataFrame, path) -> None:
    get = lambda step, rule=None: int(audit.loc[(audit.step == step) & ((audit.rule == rule) if rule else True), "rows"].iloc[0])  # noqa: E731
    raw = get("Raw input")
    steps = [
        ("Sheet overlap (1–9 Dec 2010 twice)", -get("Remove sheet overlap")),
        ("Exact duplicate lines", -get("Drop exact duplicates")),
        ("Cancellations (kept, flagged)", -get("Classify", "line_type = cancellation")),
        ("Postage, fees, vouchers (flagged)", -get("Classify", "line_type = non_product")),
        ("Stock write-offs (flagged)", -get("Classify", "line_type = stock_adjustment")),
        ("Free items (flagged)", -get("Classify", "line_type = zero_price")),
    ]
    final = get("Classify", "line_type = sale")
    labels = ["Raw rows"] + [s[0] for s in steps] + ["Clean sale lines"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    level = raw
    ax.barh(0, raw, color=P.SERIES[0], height=0.6)
    ax.text(raw, 0, f"  {raw:,}", va="center", color=P.INK, fontsize=9.5)
    for i, (_, delta) in enumerate(steps, start=1):
        ax.barh(i, delta, left=level, color=P.BASELINE, height=0.6)
        ax.text(level + delta, i, f"{delta:,}  ", va="center", ha="right", color=P.INK_2, fontsize=9)
        level += delta
    ax.barh(len(labels) - 1, final, color=P.SERIES[0], height=0.6)
    ax.text(final, len(labels) - 1, f"  {final:,}", va="center", color=P.INK, fontsize=9.5)
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlim(900_000, raw * 1.035)
    ax.set_xticks([900_000, 950_000, 1_000_000, 1_050_000])
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x / 1e6:.2f}M"))
    ax.grid(axis="y", visible=False)
    _finish(fig, ax, "34k rows were wrong; 30k more aren't product sales",
            "Rows at each cleaning step (axis starts at 0.9M to show the small steps)")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 2. monthly revenue
def monthly_revenue_yoy(kpi: pd.DataFrame, path) -> None:
    k = kpi.copy()
    k["month"] = pd.to_datetime(k["month"])
    k["ty"] = np.where(k["month"].dt.month == 12, k["month"].dt.year + 1, k["month"].dt.year)
    k["pos"] = (k["month"].dt.month % 12)  # Dec -> 0 ... Nov -> 11
    k = k[k["ty"].isin([2010, 2011])]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for ty, color, z in [(2010, P.MUTED, 2), (2011, P.SERIES[0], 3)]:
        d = k[k["ty"] == ty].sort_values("pos")
        ax.plot(d["pos"], d["net_revenue"], color=color, zorder=z, marker="o", markersize=4.5,
                markeredgecolor=P.SURFACE, markeredgewidth=1.2, label=f"Trading year {ty}")
    ax.set_xticks(range(12), ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"])
    ax.yaxis.set_major_formatter(P.GBP)
    ax.set_ylim(0, None)
    ax.set_xlim(-0.3, 11.3)
    ax.legend(loc="upper left")
    nov = k.loc[k["pos"] == 11, "net_revenue"].mean()
    ratio = nov / k["net_revenue"].mean()
    _finish(fig, ax, f"Two near-identical years; November alone is {ratio:.1f}× an average month",
            "Net revenue by month, trading year Dec–Nov")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 3. revenue bridge
def revenue_bridge(bridge: pd.DataFrame, ty: pd.DataFrame, path) -> None:
    start, end = ty.loc[2010, "gross_sales"], ty.loc[2011, "gross_sales"]
    names = ["TY2010"] + list(bridge.index) + ["TY2011"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.bar(0, start, color=P.MUTED, width=0.6)
    level = start
    for i, (name, row) in enumerate(bridge.iterrows(), start=1):
        v = row["contribution_gbp"]
        color = P.SERIES[0] if v >= 0 else P.SERIES[7]
        ax.bar(i, v, bottom=level, color=color, width=0.6)
        ax.text(i, level + v + (25_000 if v >= 0 else -25_000), f"{'+' if v >= 0 else '−'}£{abs(v) / 1e3:,.0f}k",
                ha="center", va="bottom" if v >= 0 else "top", fontsize=9.5, color=P.INK)
        level += v
    ax.bar(len(names) - 1, end, color=P.SERIES[0], width=0.6)
    for x, v in [(0, start), (len(names) - 1, end)]:
        ax.text(x, v + 25_000, f"£{v / 1e6:.2f}M", ha="center", va="bottom", fontsize=9.5, color=P.INK)
    ax.set_xticks(range(len(names)), ["\n".join(textwrap.wrap(n, 12)) for n in names])
    lo = min(start, end) * 0.9
    ax.set_ylim(lo, max(start, end) * 1.03)
    ax.yaxis.set_major_formatter(P.GBP)
    ax.grid(axis="x", visible=False)
    _finish(fig, ax, f"Sales grew {end / start - 1:.1%}, but customers ordered less often",
            "Gross merchandise sales, TY2010 → TY2011, LMDI driver decomposition (axis does not start at 0)")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 4. new vs returning
def new_vs_returning(kpi: pd.DataFrame, path) -> None:
    k = kpi.copy()
    k["month"] = pd.to_datetime(k["month"])
    k = k[(k["month"] >= "2010-01-01") & (k["month"] <= "2011-11-01")]
    parts = [("returning_customer_sales", "Returning customers", P.SERIES[0]),
             ("new_customer_sales", "New customers", P.SERIES[1]),
             ("guest_sales", "Guest checkouts (no ID)", P.SERIES[2])]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(k))
    bottom = np.zeros(len(k))
    for col, label, color in parts:
        vals = k[col].fillna(0).to_numpy()
        ax.bar(x, vals, bottom=bottom, color=color, width=0.78, label=label,
               edgecolor=P.SURFACE, linewidth=1.0)
        bottom += vals
    ax.set_xticks(x[::3], [d.strftime("%b\n%Y") for d in k["month"].iloc[::3]])
    ax.yaxis.set_major_formatter(P.GBP)
    ax.legend(loc="upper left", ncols=3)
    ax.set_ylim(0, bottom.max() * 1.15)
    ax.grid(axis="x", visible=False)
    jan_nov = k["month"].dt.month <= 11
    new_2010 = k.loc[jan_nov & (k["month"].dt.year == 2010), "new_customer_sales"].sum()
    new_2011 = k.loc[jan_nov & (k["month"].dt.year == 2011), "new_customer_sales"].sum()
    _finish(fig, ax, f"New-customer sales fell {1 - new_2011 / new_2010:.0%} (Jan–Nov, YoY): growth now rests on the existing base",
            "Gross sales by customer type per month (Dec-2009 excluded: everyone looks 'new' in month one)")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 5. cohort heatmap
def cohort_heatmap(mat: pd.DataFrame, sizes: pd.Series, path) -> None:
    m = mat.loc[(mat.index >= "2010-01-01") & (mat.index <= "2011-06-01"), list(range(1, 13))]
    fig, ax = plt.subplots(figsize=(10, 6.2))
    vmax = 0.4
    im = ax.imshow(m.to_numpy(dtype=float), cmap=P.SEQUENTIAL, vmin=0, vmax=vmax, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7.5,
                        color=P.ink_on(P.SEQUENTIAL(min(v / vmax, 1.0))))
    ax.set_xticks(range(12), [f"M{c}" for c in m.columns])
    ax.set_yticks(range(len(m)), [f"{d:%b %Y}  (n={sizes.loc[d]:,})" for d in m.index])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, format=P.PCT)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=P.MUTED)
    _finish(fig, ax, "Only ~1 in 5 new customers orders again in any given month",
            "Share of each monthly acquisition cohort placing an order N months after their first")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 6. RFM segments
def segment_shares(summary: pd.DataFrame, path) -> None:
    s = summary.iloc[::-1]
    y = np.arange(len(s))
    h = 0.38
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.barh(y + h / 2 + 0.01, s["customer_share"], height=h, color=P.MUTED, label="Share of customers")
    ax.barh(y - h / 2 - 0.01, s["revenue_share"], height=h, color=P.SERIES[0], label="Share of revenue")
    for yi, v in zip(y, s["revenue_share"]):
        ax.text(v + 0.006, yi - h / 2, f"{v:.0%}", va="center", fontsize=8.5, color=P.INK)
    for yi, v in zip(y, s["customer_share"]):
        ax.text(v + 0.006, yi + h / 2, f"{v:.0%}", va="center", fontsize=8.5, color=P.INK_2)
    ax.set_yticks(y, s.index)
    ax.xaxis.set_major_formatter(P.PCT)
    ax.set_xlim(0, max(s["revenue_share"].max(), s["customer_share"].max()) * 1.12)
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    champ = summary.loc["Champions"]
    _finish(fig, ax, f"Champions are {champ.customer_share:.0%} of customers but {champ.revenue_share:.0%} of revenue",
            "RFM segments: share of identified customers vs share of lifetime net revenue")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 7. concentration
def concentration(products: pd.DataFrame, customers: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.plot([0, 1], [0, 1], color=P.BASELINE, linewidth=1)
    for curve, label, color in [(products, "Products (SKUs)", P.SERIES[0]), (customers, "Customers", P.SERIES[1])]:
        ax.plot(curve["entity_share"], curve["value_share"], color=color, label=label)
        v = float(np.interp(0.2, curve["entity_share"], curve["value_share"]))
        ax.plot([0.2], [v], "o", color=color, markersize=7, markeredgecolor=P.SURFACE, markeredgewidth=1.5)
        ax.annotate(f"top 20% {label.split()[0].lower()} = {v:.0%} of revenue", (0.2, v),
                    xytext=(12, -4 if color == P.SERIES[0] else -16), textcoords="offset points",
                    fontsize=9, color=P.INK)
    ax.text(0.62, 0.55, "equal share line", rotation=33, color=P.MUTED, fontsize=8.5)
    ax.xaxis.set_major_formatter(P.PCT)
    ax.yaxis.set_major_formatter(P.PCT)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Cumulative share of entities (largest first)")
    ax.set_ylabel("Cumulative share of net revenue")
    ax.legend(loc="lower right")
    _finish(fig, ax, "Revenue is concentrated in a few products and customers",
            "Lorenz-style concentration curves")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 8. CLV validation
def clv_validation(buckets: pd.DataFrame, metrics: dict, path) -> None:
    b = buckets.reset_index()
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.plot(b["x_bucket"], b["actual"], color=P.INK, marker="o", markersize=6, label="Actual (holdout)")
    ax.plot(b["x_bucket"], b["bgnbd"], color=P.SERIES[0], marker="o", markersize=6,
            markeredgecolor=P.SURFACE, markeredgewidth=1.2, label="BG/NBD prediction")
    ax.plot(b["x_bucket"], b["naive"], color=P.SERIES[1], marker="o", markersize=6,
            markeredgecolor=P.SURFACE, markeredgewidth=1.2, label="Naive run-rate")
    ax.set_xticks(b["x_bucket"], [str(v) if v < 10 else "10+" for v in b["x_bucket"]])
    ax.set_xlabel("Repeat purchases in calibration period (Dec-2009 → Jun-2011)")
    ax.set_ylabel("Avg purchases in 26-week holdout")
    ax.set_ylim(0, None)
    ax.legend(loc="upper left")
    _finish(fig, ax,
            f"Out-of-sample, BG/NBD is within {abs(metrics['bgnbd_total_purchases'] / metrics['actual_total_purchases'] - 1):.0%} "
            f"of actual purchases; the run-rate overshoots by {metrics['naive_total_purchases'] / metrics['actual_total_purchases'] - 1:.0%}",
            f"Per-customer MAE {metrics['bgnbd_mae']:.2f} vs {metrics['naive_mae']:.2f} (naive) · "
            f"{metrics['customers']:,} customers")
    P.save(fig, path)


def clv_by_segment(seg_clv: pd.DataFrame, path) -> None:
    s = seg_clv.sort_values("clv_total")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.barh(s.index, s["clv_total"], color=P.SERIES[0], height=0.62)
    for i, (v, n, pa) in enumerate(zip(s["clv_total"], s["customers"], s["p_alive_repeat"])):
        alive = f" · repeat buyers' P(alive) {pa:.0%}" if pd.notna(pa) else ""
        ax.text(v, i, f"  £{v / 1e3:,.0f}k · {n:,} customers{alive}", va="center", fontsize=8.5, color=P.INK_2)
    ax.xaxis.set_major_formatter(P.GBP)
    ax.set_xlim(0, s["clv_total"].max() * 1.6)
    ax.grid(axis="y", visible=False)
    _finish(fig, ax, "Where next year's revenue will come from",
            "Predicted 12-month revenue (BG/NBD × Gamma-Gamma) by RFM segment")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 9. basket rules
def top_rules(rules: pd.DataFrame, path, n: int = 12) -> None:
    r = rules.head(n).iloc[::-1]

    def short(s, w=30):
        s = string.capwords(str(s).lower())
        return s if len(s) <= w else s[: w - 1] + "…"

    labels = [f"{short(a)}  →  {short(b)}" for a, b in zip(r["antecedent_name"], r["consequent_name"])]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.barh(range(len(r)), r["lift"], color=P.SERIES[0], height=0.62)
    for i, (lift, conf) in enumerate(zip(r["lift"], r["confidence"])):
        ax.text(lift, i, f"  {lift:.0f}× · {conf:.0%} conf.", va="center", fontsize=8.5, color=P.INK_2)
    ax.set_yticks(range(len(r)), labels, fontsize=8.8)
    ax.set_xlim(0, r["lift"].max() * 1.25)
    ax.set_xlabel("Lift (how many times more often than chance)")
    ax.grid(axis="y", visible=False)
    _finish(fig, ax, "Customers buy collections, not items",
            f"Top product pairs by lift (support ≥ 1% of {rules.attrs.get('n_baskets', 0):,} baskets)")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 10. forecast
def forecast(series: pd.DataFrame, bt: pd.DataFrame, final: pd.DataFrame, scores: pd.DataFrame, path) -> None:
    hist = series.iloc[-60:]
    one = bt[(bt["model"] == "ensemble") & (bt["step"] == 1)]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(hist.index, hist["revenue"], color=P.INK, linewidth=1.6, label="Actual weekly revenue")
    ax.plot(one["week"], one["forecast"], color=P.SERIES[0], marker="o", markersize=4,
            markeredgecolor=P.SURFACE, markeredgewidth=1, label="Backtest: 1-week-ahead forecast")
    ax.fill_between(final.index, final["lower"], final["upper"], color=P.BLUE_RAMP[1], linewidth=0,
                    label="Forecast, 80% interval")
    ax.plot(final.index, final["forecast"], color=P.SERIES[0], linewidth=2)
    ax.axvline(series.index[-1] + pd.Timedelta(days=3.5), color=P.BASELINE, linewidth=1)
    ax.text(series.index[-1] + pd.Timedelta(days=6), ax.get_ylim()[1] * 0.95, "forecast →", color=P.MUTED, fontsize=9)
    ax.yaxis.set_major_formatter(P.GBP)
    ax.set_ylim(0, None)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncols=3)
    e = scores.loc["ensemble", "WAPE (1-4 wk)"]
    sn = scores.loc["seasonal_naive", "WAPE (1-4 wk)"]
    _finish(fig, ax, f"Ensemble forecast: {e:.1%} error vs {sn:.1%} for last-year's-week baseline",
            "Weekly net revenue; 26 rolling origins, 1–4 week horizon, WAPE")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 11. order timing
def order_timing(timing: pd.DataFrame, path) -> None:
    t = timing[timing["iso_dow"] != 6]  # the shop is closed on Saturdays (30 stray orders)
    grid = t.pivot_table(index="dow_name", columns="hour", values="orders", aggfunc="sum").reindex(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sun"]).fillna(0)
    grid = grid.loc[:, [h for h in grid.columns if 7 <= h <= 20]]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    im = ax.imshow(grid.to_numpy(), cmap=P.SEQUENTIAL, aspect="auto")
    ax.set_xticks(range(grid.shape[1]), [f"{int(h):02d}:00" for h in grid.columns], fontsize=8.5)
    ax.set_yticks(range(grid.shape[0]), grid.index)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=P.MUTED)
    cb.set_label("orders", color=P.INK_2)
    peak = t.loc[t["orders"].idxmax()]
    _finish(fig, ax, f"Orders peak {peak.dow_name} around {int(peak.hour)}:00 — a B2B, office-hours pattern",
            "Orders by day of week and hour (Saturday: closed)")
    P.save(fig, path)


# ----------------------------------------------------------------------------- 12. countries
def country_dumbbell(country: pd.DataFrame, path, n: int = 10) -> None:
    c = country[country["country"] != "United Kingdom"]
    wide = c.pivot(index="country", columns="trading_year", values="net_revenue").fillna(0)
    wide = wide.sort_values(2011, ascending=False).head(n).iloc[::-1]
    y = np.arange(len(wide))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hlines(y, wide[2010], wide[2011], color=P.BASELINE, linewidth=2)
    ax.plot(wide[2010], y, "o", color=P.MUTED, markersize=7, label="TY2010")
    ax.plot(wide[2011], y, "o", color=P.SERIES[0], markersize=8, markeredgecolor=P.SURFACE, markeredgewidth=1.2, label="TY2011")
    for yi, (a, b) in enumerate(zip(wide[2010], wide[2011])):
        g = b / a - 1 if a > 0 else np.nan
        ax.text(max(a, b), yi, f"   {g:+.0%}" if pd.notna(g) else "   new", va="center", fontsize=8.5, color=P.INK_2)
    ax.set_yticks(y, wide.index)
    ax.xaxis.set_major_formatter(P.GBP)
    ax.set_xlim(0, wide.to_numpy().max() * 1.18)
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    _finish(fig, ax, "International: small but growing markets",
            "Net revenue by country outside the UK, trading year 2010 → 2011 (top 10)")
    P.save(fig, path)
