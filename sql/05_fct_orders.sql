-- 05_fct_orders.sql
-- Fact table at order (invoice) grain. Only sale invoices count as orders;
-- cancellations are tracked against the order they reversed via was_cancelled.
CREATE OR REPLACE TABLE fct_orders AS
SELECT
    invoice,
    ANY_VALUE(customer_id)                         AS customer_id,
    BOOL_OR(is_guest)                              AS is_guest,
    ANY_VALUE(country)                             AS country,
    MIN(invoice_ts)                                AS order_ts,
    MIN(date_key)                                  AS date_key,
    COUNT(*)                                       AS n_lines,
    COUNT(DISTINCT stock_code)                     AS n_skus,
    SUM(quantity)                                  AS n_units,
    SUM(revenue)                                   AS order_value,
    BOOL_AND(was_cancelled)                        AS fully_cancelled
FROM fct_order_lines
WHERE line_type = 'sale'
GROUP BY invoice;
