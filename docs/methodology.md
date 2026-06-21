# Methodology notes

Why I made the choices I did, including a couple of things that went wrong first.

## 1. Cleaning

I profiled every column before starting the analysis and found five problems that a plain `pd.read_excel` would pass straight through:

1. The two Excel sheets overlap. 1-9 Dec 2010 is in both, so stacking them double counts 22,523 rows and about £377k. I checked that every invoice in the overlap really is in both sheets before cutting it from the first one.
2. 11,812 exact duplicate lines (same invoice, product, quantity, price and timestamp).
3. Not every row is a sale. Cancellations (`C` invoices), postage and fees (`POST`, `DOT`, `M`, `AMAZONFEE`, ...), stock write-offs (negative quantity at £0 with notes like "damaged"), free items and accounting adjustments (`A` invoices, including a -£53,594 bad debt write-off) are all in the same table.
4. 1,214 stock codes have more than one description.
5. `85123` and `85123A` are different products, so the codes have to be read as text. Reading the column as numbers mixes up the types.

I didn't delete the rows in 3-5. Each row gets a `line_type`, and the SQL filters on it (`WHERE line_type = 'sale'`). That keeps the rule visible in the query, and the data quality report can account for every pound.

To match cancellations, I used `merge_asof` to link each one to the latest earlier sale with the same customer, product and quantity. 34% match exactly. The rest are partial returns or returns of things bought before the data starts. This also handles the two biggest lines in the data (80,995 and 74,215 units, each cancelled within minutes) without deleting them by hand.

## 2. Data model

It's a small star schema in DuckDB: two fact tables (`fct_order_lines`, `fct_orders`), three dimensions (`dim_date`, `dim_product`, `dim_customer`) and analysis views on top. I used DuckDB because it runs inside Python with no server, reads parquet directly and supports window functions, `FILTER` and `GROUP BY ALL`. The SQL should move to Postgres, Snowflake or BigQuery with small changes.

## 3. Revenue bridge

Sales = customers x orders per customer x average order value. Because it's a product, splitting the change with simple differences leaves an interaction term, and how big that term is depends on which order you apply the changes in. LMDI (log-mean Divisia index) weights each driver's log change so the contributions add up to the total exactly, whatever the order. Guest sales have no customer ID, so they get their own bar.

## 4. Cohorts and the Dec 2009 problem

The data starts on 1 Dec 2009, so everyone who orders that month looks like a new customer, including long-time wholesalers. I treat the Dec 2009 group (951 customers) as the existing base, not a cohort, and leave it out of the new vs returning split and the cohort comparisons. The same effect, though weaker, inflates the "new" counts in early 2010. So the 2010 vs 2011 drop in new customers is probably a bit smaller than it looks.

## 5. Segmentation

RFM is the main segmentation because it's easy to explain and act on. The scores are quintiles of ranks, not raw values, because 28% of customers have exactly one order and `qcut` can't split that many ties. Ties are broken in a fixed order (sorted by customer id). An earlier version didn't do this, and the segment counts shifted by a few customers between runs.

K-means on log-scaled, standardised R/F/M is just a check. The silhouette score is highest at k = 4 (0.36). The four clusters are active high-value, lapsing mid-value, active low-value, and one-time customers who have gone quiet. That's the same structure as the RFM segments, only less detailed.

## 6. Lifetime value (BG/NBD + Gamma-Gamma)

In this kind of business you never see a customer cancel. They just stop ordering. A simple "average spend per month x expected lifetime" treats someone who ordered 10 times in their first month and never again the same as someone who orders every month. BG/NBD separates how often a customer buys while they're active from the chance that they've stopped. Gamma-Gamma pulls each customer's noisy average spend toward the overall average, more strongly for customers with few purchases.

I implemented both from the Fader, Hardie & Lee (2005) papers using scipy. One test simulates customers from known parameters and checks that the fit recovers them.

Two things went wrong at first:

- Without bounds, the optimiser pushed a towards 0 and b to around 10^15 and reported a likelihood that was better than any sensible fit. At that scale the `gammaln` differences are just rounding error. The predictions came out negative, which is how I noticed. Bounding the parameters and adding a small L2 penalty (the `lifetimes` package does the same) fixed it.
- How much history the model gets matters a lot. With 12 months of calibration ending right after the Christmas peak, it over-predicted the next year by 54%, because customers who first bought in Q4 look like heavy buyers.

| Calibration | Holdout | Predicted / actual purchases | MAE BG/NBD | MAE naive | Rank corr. |
|---|---|---:|---:|---:|---:|
| Dec-2009 to Dec-2010 | 52 wk | 1.54 | 2.50 | 5.78 | 0.57 |
| Dec-2009 to Mar-2011 | 39 wk | 1.13 | 1.53 | 2.93 | 0.61 |
| Dec-2009 to Jun-2011 | 26 wk | 0.98 | 1.04 | 1.70 | 0.62 |

Limitations: BG/NBD assumes customers can only drop out right after a purchase, so anyone with a single purchase gets P(alive) = 1. I only report P(alive) for repeat buyers. The model also under-predicts spend in the holdout by 16%, because Q4 orders are bigger than the yearly average it learns from. The correlation between frequency and spend is 0.13, which is low enough for Gamma-Gamma's independence assumption.

## 7. Basket analysis

For pairs, a single sparse matrix product (`X.T @ X`, where X is the invoice x product 0/1 matrix) gives every co-occurrence count. You don't need an apriori loop, and it runs in under a second on 39k orders. Products below the support threshold are dropped first, which doesn't lose anything because a pair can't be more frequent than its rarer item. Rules need at least 1% support so that a high lift isn't coming from three orders.

## 8. Forecasting

With about two years of weekly data, the real question was whether anything beats the simple baselines. Each model is refit at each of the last 26 weeks and scored on 1-4 week ahead WAPE. MAPE doesn't work here because the Christmas closure weeks are near zero.

| Model | How it works |
|---|---|
| Seasonal naive | Same week last year |
| Run rate | Average daily revenue over the last 4 open weeks x trading days |
| Damped Holt | Exponential smoothing on revenue per trading day |
| Harmonic regression | OLS on a trend, 4 yearly Fourier pairs and trading days |
| Average | Mean of seasonal naive and harmonic |

The average of the two did best (13.7% vs 15.6% for seasonal naive). They make different mistakes: seasonal naive repeats last year's noise, and the harmonic model smooths out real spikes. Trading days (normally 6, fewer around Christmas and bank holidays) are known ahead of time, so they're fine to use as a regressor. The 80% interval comes from the spread of the backtest errors rather than assuming normal errors.

## 9. Reproducibility

- `make all` rebuilds everything from the raw download, and `reports/metrics.json` comes out identical on every run.
- The numbers in the README and the executive summary are taken from `metrics.json`.
- The 28 tests use small hand-made fixtures, so CI doesn't need the dataset.
