"""Interactive dashboard on top of the DuckDB warehouse.

    make all          # build the warehouse first
    make dashboard    # then open http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from retail_analytics import paths  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
MUTED, GRID = "#898781", "#e1e0d9"

st.set_page_config(page_title="Retail Customer & Revenue Analytics", layout="wide")


@st.cache_resource
def con():
    return duckdb.connect(str(paths.WAREHOUSE), read_only=True)


@st.cache_data
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return con().execute(sql, list(params)).df()


@st.cache_data
def table(name: str) -> pd.DataFrame:
    return pd.read_csv(paths.TABLES_DIR / f"{name}.csv")


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=72, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0, title_text=""),
                      title=dict(y=0.98, yanchor="top"),
                      hoverlabel=dict(bgcolor="white"), font=dict(family="system-ui, -apple-system, sans-serif"))
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


if not paths.WAREHOUSE.exists():
    st.error("Warehouse not found. Run `make data` and `make all` first.")
    st.stop()

st.title("Retail Customer & Revenue Analytics")
st.caption("UCI Online Retail II · UK online gift wholesaler · Dec 2009 – Dec 2011 · 1M+ transactions")

# filters
months = q("SELECT DISTINCT DATE_TRUNC('month', date_key)::DATE AS m FROM fct_orders ORDER BY 1")["m"].tolist()
countries = q("SELECT country, SUM(revenue) r FROM fct_order_lines GROUP BY 1 ORDER BY 2 DESC")["country"].tolist()
f1, f2, f3 = st.columns([2, 2, 1])
start, end = f1.select_slider("Months", options=months, value=(months[0], months[-2]),
                              format_func=lambda d: pd.Timestamp(d).strftime("%b %Y"))
picked = f2.multiselect("Countries (empty = all)", countries)
excl_guest = f3.toggle("Identified customers only", value=False)



def where_clause(alias: str = "") -> str:
    """Filter predicate for any table that has date_key, country and is_guest columns."""
    a = f"{alias}." if alias else ""
    w = [f"{a}date_key >= ?::DATE", f"{a}date_key < ?::DATE + INTERVAL 1 MONTH"]
    if picked:
        w.append(f"{a}country IN ({','.join('?' * len(picked))})")
    if excl_guest:
        w.append(f"NOT {a}is_guest")
    return " AND ".join(w)


W = where_clause()
params: list = [start, end] + list(picked)

tab_overview, tab_customers, tab_products, tab_forecast = st.tabs(["Overview", "Customers", "Products & baskets", "Forecast"])

# overview
with tab_overview:
    kpi = q(f"""
        SELECT SUM(revenue) AS net, SUM(revenue) FILTER (WHERE line_type='sale') AS gross,
               COUNT(DISTINCT invoice) FILTER (WHERE line_type='sale') AS orders,
               COUNT(DISTINCT customer_id) AS customers,
               -SUM(revenue) FILTER (WHERE line_type='cancellation') AS cancelled
        FROM fct_order_lines WHERE {W}""", tuple(params)).iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net revenue", f"£{kpi.net / 1e6:,.2f}M")
    c2.metric("Orders", f"{kpi.orders:,.0f}")
    c3.metric("Customers", f"{kpi.customers:,.0f}")
    c4.metric("Average order value", f"£{kpi.gross / max(kpi.orders, 1):,.0f}")
    c5.metric("Cancellation rate", f"{kpi.cancelled / max(kpi.gross, 1):.1%}")

    monthly = q(f"""
        SELECT DATE_TRUNC('month', date_key)::DATE AS month, SUM(revenue) AS net_revenue,
               COUNT(DISTINCT invoice) FILTER (WHERE line_type='sale') AS orders
        FROM fct_order_lines WHERE {W} GROUP BY 1 ORDER BY 1""", tuple(params))
    fig = px.line(monthly, x="month", y="net_revenue", markers=True, color_discrete_sequence=SERIES,
                  labels={"net_revenue": "Net revenue (£)", "month": ""}, title="Net revenue by month")
    fig.update_traces(hovertemplate="%{x|%b %Y}<br>£%{y:,.0f}<extra></extra>", line_width=2)
    st.plotly_chart(style(fig), width="stretch")

    left, right = st.columns(2)
    by_country = q(f"""
        SELECT country, SUM(revenue) AS net_revenue FROM fct_order_lines WHERE {W}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 12""", tuple(params))
    fig = px.bar(by_country.iloc[::-1], x="net_revenue", y="country", orientation="h",
                 color_discrete_sequence=SERIES, title="Top countries", labels={"net_revenue": "£", "country": ""})
    fig.update_traces(hovertemplate="%{y}: £%{x:,.0f}<extra></extra>")
    left.plotly_chart(style(fig, 380), width="stretch")

    timing = q(f"""
        SELECT STRFTIME(order_ts, '%a') AS dow, ISODOW(order_ts) AS d, EXTRACT(hour FROM order_ts) AS hour,
               COUNT(*) AS orders
        FROM fct_orders WHERE {W} AND ISODOW(order_ts) <> 6
        GROUP BY ALL""", tuple(params))
    grid = timing.pivot_table(index=["d", "dow"], columns="hour", values="orders", aggfunc="sum").fillna(0)
    grid.index = grid.index.get_level_values(1)
    fig = px.imshow(grid, color_continuous_scale=BLUES, aspect="auto", title="When orders arrive",
                    labels=dict(color="orders", x="hour", y=""))
    right.plotly_chart(style(fig, 380), width="stretch")

# customers
with tab_customers:
    seg = table("rfm_segments").rename(columns={"Unnamed: 0": "segment"})
    l, r = st.columns([3, 2])
    melted = seg.melt(id_vars="segment", value_vars=["customer_share", "revenue_share"], var_name="measure")
    melted["measure"] = melted["measure"].map({"customer_share": "Share of customers", "revenue_share": "Share of revenue"})
    fig = px.bar(melted, x="value", y="segment", color="measure", barmode="group", orientation="h",
                 color_discrete_sequence=[MUTED, SERIES[0]], title="RFM segments",
                 labels={"value": "", "segment": ""})
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(categoryorder="array", categoryarray=seg["segment"].tolist()[::-1])
    fig.update_traces(hovertemplate="%{y}: %{x:.1%}<extra></extra>")
    l.plotly_chart(style(fig, 420), width="stretch")
    r.markdown("**What to do with each segment**")
    r.dataframe(seg[["segment", "customers", "action"]], hide_index=True, width="stretch", height=380)

    coh = table("cohort_retention").rename(columns={"cohort_month": "cohort"}).set_index("cohort")
    coh = coh.loc[(coh.index >= "2010-01-01") & (coh.index <= "2011-06-01"), [str(i) for i in range(1, 13)]]
    fig = px.imshow(coh, color_continuous_scale=BLUES, zmin=0, zmax=0.4, aspect="auto", text_auto=".0%",
                    title="Cohort retention: share of each monthly cohort ordering again N months later",
                    labels=dict(x="months since first order", y="cohort", color="retention"))
    st.plotly_chart(style(fig, 520), width="stretch")

    clv = table("clv_by_segment")
    fig = px.bar(clv.sort_values("clv_total"), x="clv_total", y="segment", orientation="h",
                 color_discrete_sequence=SERIES, title="Predicted next-12-month revenue by segment (BG/NBD × Gamma-Gamma)",
                 labels={"clv_total": "£", "segment": ""}, hover_data={"customers": True, "clv_mean": ":,.0f"})
    st.plotly_chart(style(fig, 380), width="stretch")

# products & baskets
with tab_products:
    prod = q(f"""
        SELECT p.stock_code, p.description, SUM(l.revenue) AS net_revenue,
               SUM(l.quantity) FILTER (WHERE l.line_type='sale') AS units
        FROM fct_order_lines l JOIN dim_product p USING (stock_code)
        WHERE {where_clause("l")}
        GROUP BY ALL ORDER BY net_revenue DESC LIMIT 25""", tuple(params))
    fig = px.bar(prod.iloc[::-1], x="net_revenue", y="description", orientation="h", color_discrete_sequence=SERIES,
                 title="Top 25 products by net revenue", labels={"net_revenue": "£", "description": ""},
                 hover_data={"stock_code": True, "units": ":,.0f"})
    st.plotly_chart(style(fig, 640), width="stretch")

    rules = table("association_rules")
    st.markdown("**Cross-sell explorer**: pick a product to see what's bought with it")
    names = sorted(set(rules["antecedent_name"].dropna()) | set(rules["consequent_name"].dropna()))
    choice = st.selectbox("Product", names, index=names.index("REGENCY CAKESTAND 3 TIER") if "REGENCY CAKESTAND 3 TIER" in names else 0)
    hits = rules[(rules["antecedent_name"] == choice) | (rules["consequent_name"] == choice)].copy()
    hits["bought with"] = hits.apply(lambda r: r["consequent_name"] if r["antecedent_name"] == choice else r["antecedent_name"], axis=1)
    st.dataframe(hits[["bought with", "support", "confidence", "lift"]].sort_values("lift", ascending=False)
                 .style.format({"support": "{:.1%}", "confidence": "{:.0%}", "lift": "{:.1f}×"}),
                 hide_index=True, width="stretch")

# forecast
with tab_forecast:
    scores = table("forecast_scores").rename(columns={"Unnamed: 0": "model"})
    nxt = table("forecast_next_8_weeks").rename(columns={"Unnamed: 0": "week"})
    hist = q("""SELECT DATE_TRUNC('week', date_key)::DATE AS week, SUM(revenue) AS revenue
                FROM fct_order_lines GROUP BY 1 ORDER BY 1""").iloc[:-1]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist["week"], y=hist["revenue"], name="Actual", line=dict(color="#0b0b0b", width=1.6),
                             hovertemplate="%{x|%d %b %Y}: £%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=list(nxt["week"]) + list(nxt["week"][::-1]), y=list(nxt["upper"]) + list(nxt["lower"][::-1]),
                             fill="toself", fillcolor="rgba(57,135,229,0.25)", line=dict(width=0), name="80% interval",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=nxt["week"], y=nxt["forecast"], name="Forecast", line=dict(color=SERIES[0], width=2),
                             hovertemplate="%{x|%d %b %Y}: £%{y:,.0f}<extra></extra>"))
    fig.update_layout(title="Weekly net revenue and the next 8 weeks")
    st.plotly_chart(style(fig, 420), width="stretch")
    st.markdown("**Backtest**: 26 rolling origins, 1-4 weeks ahead (lower is better)")
    st.dataframe(scores.style.format({c: "{:.1%}" for c in scores.columns if c != "model"}),
                 hide_index=True, width="stretch")
