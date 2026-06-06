-- 15_customer_rfm_base.sql
-- Recency / Frequency / Monetary inputs per customer, measured at a snapshot
-- date one day after the last order in the data. Customers whose net spend is
-- <= 0 (everything they bought was returned) are excluded from segmentation.
CREATE OR REPLACE VIEW customer_rfm_base AS
WITH snap AS (
    SELECT MAX(date_key) + INTERVAL 1 DAY AS snapshot_date FROM fct_orders
)
SELECT
    c.customer_id,
    c.country,
    DATEDIFF('day', c.last_order_date, s.snapshot_date)              AS recency_days,
    c.n_orders                                                       AS frequency,
    c.net_revenue                                                    AS monetary,
    DATEDIFF('day', c.first_order_date, s.snapshot_date)             AS tenure_days
FROM dim_customer c
CROSS JOIN snap s
WHERE c.net_revenue > 0;
