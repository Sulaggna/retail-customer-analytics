-- 16_purchase_intervals.sql
-- Days between consecutive orders for each customer (LAG window function).
-- The distribution tells us what "late" means for a customer, which grounds
-- the "At Risk" thresholds in segmentation instead of picking them by gut feel.
CREATE OR REPLACE VIEW purchase_intervals AS
WITH ordered AS (
    SELECT
        customer_id,
        date_key,
        LAG(date_key) OVER (PARTITION BY customer_id ORDER BY order_ts) AS prev_date
    FROM fct_orders
    WHERE customer_id IS NOT NULL
)
SELECT customer_id, date_key, DATEDIFF('day', prev_date, date_key) AS days_since_prev_order
FROM ordered
WHERE prev_date IS NOT NULL
  AND date_key > prev_date;                                          -- ignore same-day re-orders
