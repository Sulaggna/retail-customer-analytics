# Methodology & Decisions

The *why* behind each analytical choice — including the ones that were wrong first.

## 1. Data cleaning: flag, don't delete

Profiling every column before writing any analysis surfaced five problems a naive
`pd.read_excel` would silently propagate:

1. **The two Excel sheets overlap.** 1–9 Dec 2010 appears in both. Stacking them
   double-counts 22,523 rows and **£377k** of revenue. The fix is a date cut on the
   first sheet, verified by checking every overlapping invoice exists in both sheets.
2. **11,812 exact duplicate lines** (same invoice, product, quantity, price, second).
3. **Not every row is a sale.** Cancellations (`C` invoices), postage and fees
   (`POST`, `DOT`, `M`, `AMAZONFEE`…), warehouse write-offs (negative quantity at
   £0 with notes like "damaged"), free items, and accounting adjustments (`A`
   invoices, including a −£53,594 bad-debt write-off) all live in the same table.
4. **Product names drift.** 1,214 stock codes have more than one description.
5. **Mixed-type keys.** `85123` and `85123A` are different products; reading the
   column as numeric would merge or drop them. Everything is read as text first.

Rather than deleting categories 3–5, every row gets a `line_type`, and SQL filters on
it explicitly. That keeps the business rule visible in the query (`WHERE line_type =
'sale'`) and lets the data-quality report reconcile every pound.

**Cancellation matching.** `merge_asof` links each cancellation to the most recent
earlier sale with the same customer, product and quantity. 34% match exactly; the
rest are partial returns or reverse sales made before the data window. This is how the
two largest lines in the data (80,995 and 74,215 units, each cancelled within minutes)
are neutralised without hand-deleting "outliers".

## 2. Data model

A small star schema in DuckDB: two facts (`fct_order_lines`, `fct_orders`) and three
dimensions (`dim_date`, `dim_product`, `dim_customer`), with analysis views on top.
DuckDB was chosen because it runs in-process (no server), reads Parquet directly and
speaks Postgres-flavoured SQL with window functions, `FILTER`, `QUALIFY` and `GROUP BY
ALL` — so the SQL here ports to Snowflake / BigQuery / Postgres with minor edits.

## 3. Revenue bridge (LMDI)

Revenue = customers × orders per customer × AOV is multiplicative, so splitting a
change between drivers with simple differences leaves an unexplained "interaction"
residual whose size depends on the order you apply the changes. The **LMDI-I
(log-mean Divisia index)** method weights each driver's log change by the logarithmic
mean of the totals; the contributions sum to the total change exactly and don't depend
on ordering. Guest sales sit outside the identity (no customer key) and are shown as
their own bar.

## 4. Cohorts and the left-censoring trap

The data starts on 1-Dec-2009, so *every* customer who orders that month looks "new" —
including long-standing wholesalers. The Dec-2009 cohort (951 customers) is therefore
treated as the **established base**, not a cohort, and excluded from new-vs-returning
splits and vintage comparisons. The same effect, weaker, inflates "new" counts for
early 2010; the 2010-vs-2011 new-customer comparison should be read as an upper bound
on the decline.

## 5. Segmentation

**RFM** is the primary segmentation because a CRM team can act on it and explain it.
Scores are quintiles of *ranks*: 28% of customers have frequency = 1, which breaks
`qcut` on raw values. Ties are broken deterministically (sort by customer id first),
which matters — an early version produced segment counts that drifted by a few
customers between runs.

**k-means** on log-scaled, standardised RFM is a cross-check, not the deliverable. The
silhouette score peaks at k = 4 (0.36): an active high-value group, a lapsing mid-value
group, an active low-value group and a dormant one-time group — the same structure
the RFM rules encode with finer, more actionable splits.

## 6. Customer lifetime value (BG/NBD + Gamma-Gamma)

**Why a probabilistic model.** In non-contractual retail, churn is never observed.
"Historical spend ÷ tenure × horizon" treats a customer who bought 10 times in their
first month and never again the same as one who buys monthly. BG/NBD separates *how
often someone buys while active* from *the chance they have quietly left*; Gamma-Gamma
shrinks noisy per-customer average spend toward the population mean.

**Implemented from scratch** (`clv.py`) from Fader, Hardie & Lee (2005) with SciPy,
and unit-tested by simulating customers from known parameters and recovering them.

**Two numerical lessons.**

- Unbounded, the optimiser drove *a* → 0 and *b* → 10¹⁵ and reported a likelihood
  *better* than any sensible fit. It was climbing floating-point noise: `gammaln(b)`
  differences lose all precision at that scale. Parameter bounds plus a small L2
  penalty (as in the `lifetimes` library) fixed it.
- **Calibration length matters more than model choice.** With 12 months of calibration
  (ending in the pre-Christmas peak) the model over-forecast the next year by 54%:
  customers acquired in Q4 look like heavy buyers. Extending calibration to 18 months
  brought total predicted purchases within 1.5% of actual.

| Calibration | Holdout | Predicted ÷ actual purchases | MAE BG/NBD | MAE naive | Rank corr. |
|---|---|---:|---:|---:|---:|
| Dec-2009 → Dec-2010 | 52 wk | 1.54 | 2.50 | 5.78 | 0.57 |
| Dec-2009 → Mar-2011 | 39 wk | 1.13 | 1.53 | 2.93 | 0.61 |
| Dec-2009 → Jun-2011 | 26 wk | **0.98** | **1.04** | 1.70 | **0.62** |

**Known limitations.** BG/NBD assumes customers can only churn immediately after a
purchase, so one-time buyers always get P(alive) = 1 (P(alive) is reported for repeat
buyers only). Spend is under-forecast by 16% in the holdout because Q4 baskets are
larger than the year-round average the model learns. Correlation between frequency and
spend is 0.13, close enough to the Gamma-Gamma independence assumption.

## 7. Market-basket analysis

Pairwise rules via one sparse matrix product (`X.T @ X` on an invoice × product
incidence matrix) rather than an iterative Apriori loop — for pairs the result is
identical and it runs in under a second on 39k baskets. Items below the support
threshold are pruned first, which is lossless (a pair can't be more frequent than its
rarer item). Rules are ranked by lift with a 1% support floor so a lift of 46 isn't
coming from three baskets.

## 8. Forecasting

Only ~2 years of weekly data, so the bar is: **does anything beat the obvious
baselines in an honest backtest?** Every model is refit at each of 26 rolling origins
and scored on 1–4-week-ahead WAPE (MAPE is undefined in Christmas-closure weeks).

| Model | Idea |
|---|---|
| Seasonal naive | Same week last year |
| Run-rate | Last 4 open weeks' daily average × known trading days |
| Damped Holt | Exponential smoothing on revenue per trading day |
| Harmonic regression | OLS on trend + 4 yearly Fourier pairs + trading-days regressor |
| **Ensemble** | Mean of seasonal naive and harmonic |

The ensemble wins (13.7% vs 15.6% for seasonal naive): the two models make different
mistakes — seasonal naive copies last year's noise, the harmonic model smooths real
spikes — so averaging cancels part of each. Trading days (6 normally, 0–4 around
Christmas and bank holidays) are known in advance, so using them as a regressor is not
leakage. The 80% interval comes from empirical backtest residual quantiles rather than
a normality assumption.

## 9. Reproducibility

- `make all` rebuilds everything from the raw download; `reports/metrics.json` is
  byte-identical across runs.
- Every number in the README and executive summary is copied from `metrics.json`.
- `pytest` (28 tests, ~3 s) runs on small hand-built fixtures, so CI doesn't need the
  45 MB dataset.
