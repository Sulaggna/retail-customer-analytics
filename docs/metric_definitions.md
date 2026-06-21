# Metric definitions

These are used the same way in the SQL, the Python code and the dashboard. Where a definition
needed a judgement call I've noted why.

## Revenue

| Metric | Definition | Notes |
|---|---|---|
| **Gross sales** | Σ `quantity × unit_price` over `line_type = 'sale'` | Merchandise only. Postage, fees, vouchers and adjustments are `non_product` and excluded. |
| **Cancellations** | Σ revenue over `line_type = 'cancellation'` (negative) | 'C'-prefixed invoices. |
| **Net revenue** | Gross sales + cancellations | The headline revenue figure. |
| **Orders** | Count of distinct sale invoices | A cancellation invoice is not an order. |
| **AOV** | Gross sales ÷ orders | Uses gross, not net, so a late cancellation doesn't retroactively shrink an order. |
| **Cancellation rate** | −Cancellations ÷ gross sales | Value-weighted, not count-weighted. |
| **Trading year (TY)** | December → November, labelled by the year it ends | Keeps the Christmas peak inside one year. TY2010 = Dec-2009–Nov-2010. |

## Customers

| Metric | Definition | Notes |
|---|---|---|
| **Customer** | A distinct, non-null `Customer ID` | Guest checkouts (no ID, 13% of sales) are excluded from all customer metrics. |
| **Active customers** | Customers with ≥ 1 order in the period | |
| **Orders per customer** | Identified-customer orders ÷ active customers | |
| **New customer (in month m)** | First order in the data falls in month m | Left-censored: the dataset starts Dec-2009, so customers who bought before then look new when they first appear. Dec-2009 is therefore excluded from new/returning splits, and Jan–Nov 2010 "new" counts are an upper bound. |
| **Cohort** | Calendar month of a customer's first order | |
| **Retention (month N)** | Share of a cohort placing ≥ 1 order in month N after the cohort month | Calendar-month based, not rolling 30-day windows. |

## Segmentation (RFM)

| Input | Definition |
|---|---|
| **Recency** | Days from last order to the snapshot date (day after the last order in the data, 10-Dec-2011) |
| **Frequency** | Number of orders |
| **Monetary** | Lifetime net revenue; customers with net ≤ 0 (everything returned) are excluded |
| **R, F, M scores** | Quintiles 1–5 on ranks (5 = best; lower recency is better) |
| **FM score** | ⌈(F + M) ÷ 2⌉ |

Segments are rules on the (R, FM) grid, listed in `segmentation.SEGMENT_RULES` and evaluated top to bottom.

## Lifetime value

| Metric | Definition |
|---|---|
| **Purchase** (for CLV) | A customer-day with positive order value; same-day invoices are merged and fully cancelled orders dropped |
| **x / t_x / T** | Repeat purchases; weeks from first to last purchase; weeks from first purchase to end of observation |
| **P(alive)** | BG/NBD probability that the customer has not silently churned. By model construction it is 1 for customers with no repeat purchase, so it is only reported for repeat buyers |
| **12-month CLV** | Expected purchases in the next 52 weeks (BG/NBD) × expected spend per purchase (Gamma-Gamma). Revenue-based and undiscounted |

## Basket analysis

For products A and B over N baskets (sale invoices, fully cancelled orders excluded):

- **support(A,B)** = baskets containing both ÷ N
- **confidence(A→B)** = support(A,B) ÷ support(A)
- **lift(A→B)** = confidence(A→B) ÷ support(B), i.e. how many times more often they're bought together than if purchases were independent
- **leverage** = support(A,B) − support(A)·support(B)

## Forecasting

- **WAPE** = Σ|forecast − actual| ÷ Σ actual. Used instead of MAPE because the Christmas closure weeks are close to zero and MAPE blows up on them.
- **Bias** = Σ(forecast − actual) ÷ Σ actual. Negative means under-forecasting.
- **Rolling-origin backtest**: each of the last 26 weeks is used as a forecast origin; models are refit on data before the origin and forecast 1–4 weeks ahead.
