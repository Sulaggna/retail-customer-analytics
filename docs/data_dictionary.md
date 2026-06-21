# Data Dictionary

## Source

UCI Online Retail II, Chen, D. (2019). UCI Machine Learning Repository.
<https://doi.org/10.24432/C5CG6D> · licence CC BY 4.0.

All transactions of a UK-based, registered non-store online retailer of all-occasion
giftware between 01-Dec-2009 and 09-Dec-2011. Many customers are wholesalers. The data
ships as one Excel workbook with two sheets (2009-2010, 2010-2011).

| Raw column | Type | Description |
|---|---|---|
| `Invoice` | text | 6-digit invoice number. Prefix `C` = cancellation, `A` = accounting adjustment |
| `StockCode` | text | 5-digit product code, sometimes with a letter suffix (`85123A`); non-numeric codes are services/fees |
| `Description` | text | Product name (inconsistent; also used for warehouse notes such as "damaged") |
| `Quantity` | integer | Units per line; negative on cancellations and stock write-offs |
| `InvoiceDate` | timestamp | Invoice date and time |
| `Price` | decimal | Unit price in GBP |
| `Customer ID` | integer | 5-digit customer number; missing on ~23% of raw rows |
| `Country` | text | Customer's country |

## Warehouse (`data/warehouse.duckdb`)

Built by the SQL files in [`sql/`](../sql), in filename order.

### `stg_transactions` (every cleaned row, with flags)

| Column | Description |
|---|---|
| `invoice`, `invoice_ts`, `invoice_date` | Invoice id, timestamp, date |
| `customer_id`, `is_guest` | Customer key (NULL for guests) and a guest flag |
| `country`, `stock_code`, `description` | Description is the canonical (most frequent) name per stock code |
| `quantity`, `unit_price`, `revenue` | `revenue = quantity × unit_price` (negative for cancellations) |
| `line_type` | `sale`, `cancellation`, `non_product`, `stock_adjustment`, `bad_debt_adjustment`, `zero_price` |
| `was_cancelled` | Sale line later reversed by a matched cancellation |
| `matched_cancellation` | Cancellation line linked to its originating sale |

### Facts

| Table | Grain | Key columns |
|---|---|---|
| `fct_order_lines` | One row per sale or cancellation line | `invoice`, `date_key`, `customer_id`, `stock_code`, `quantity`, `revenue`, `line_type` |
| `fct_orders` | One row per sale invoice | `order_ts`, `n_lines`, `n_skus`, `n_units`, `order_value`, `fully_cancelled` |

### Dimensions

| Table | Grain | Key columns |
|---|---|---|
| `dim_date` | Day | `month_start`, `week_start`, `iso_dow`, `is_weekend`, `trading_year` |
| `dim_product` | Merchandise SKU | `description`, `median_unit_price`, `price_band`, `first_sold`, `last_sold` |
| `dim_customer` | Identified customer | `country` (mode), `first_order_date`, `cohort_month`, `n_orders`, `gross_revenue`, `net_revenue` |

### Analysis views

| View | What it answers |
|---|---|
| `kpi_monthly` | Monthly gross/net revenue, orders, AOV, new vs returning vs guest sales |
| `kpi_country` | Country revenue per trading year, YoY growth and share |
| `product_performance` | SKU revenue, Pareto rank, cumulative share, cancellation rate |
| `cohort_retention` | Monthly cohort × months-since-first-order retention and revenue |
| `cancellations_by_country` | Cancellation rate for countries with > £50k sales |
| `customer_rfm_base` | Recency / frequency / monetary inputs per customer |
| `purchase_intervals` | Days between consecutive orders (LAG) |
| `order_timing` | Orders by weekday × hour |
