-- 06_dim_customer.sql
-- One row per identified customer. Guest checkouts (no Customer ID) are excluded
-- from every customer-level model.
CREATE OR REPLACE TABLE dim_customer AS
WITH orders AS (
    SELECT * FROM fct_orders WHERE customer_id IS NOT NULL
),
net AS (
    SELECT customer_id, SUM(revenue) AS net_revenue
    FROM fct_order_lines
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT
    o.customer_id,
    MODE(o.country)                                         AS country,
    MIN(o.date_key)                                         AS first_order_date,
    DATE_TRUNC('month', MIN(o.date_key))::DATE              AS cohort_month,
    MAX(o.date_key)                                         AS last_order_date,
    COUNT(*)                                                AS n_orders,
    SUM(o.order_value)                                      AS gross_revenue,
    ANY_VALUE(n.net_revenue)                                AS net_revenue
FROM orders o
LEFT JOIN net n USING (customer_id)
GROUP BY o.customer_id;
