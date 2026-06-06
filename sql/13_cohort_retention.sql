-- 13_cohort_retention.sql
-- Monthly acquisition cohorts: share of each cohort that orders again N months
-- after their first order, plus the revenue each cohort generates over time.
CREATE OR REPLACE VIEW cohort_retention AS
WITH activity AS (
    SELECT
        o.customer_id,
        c.cohort_month,
        DATE_TRUNC('month', o.date_key)::DATE                AS activity_month,
        SUM(o.order_value)                                   AS sales
    FROM fct_orders o
    JOIN dim_customer c USING (customer_id)
    GROUP BY ALL
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM dim_customer
    GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    DATEDIFF('month', a.cohort_month, a.activity_month)      AS months_since_first,
    COUNT(*)                                                 AS active_customers,
    s.cohort_customers,
    COUNT(*) / s.cohort_customers                            AS retention_rate,
    SUM(a.sales)                                             AS cohort_sales,
    SUM(a.sales) / s.cohort_customers                        AS sales_per_cohort_customer
FROM activity a
JOIN cohort_size s USING (cohort_month)
GROUP BY a.cohort_month, months_since_first, s.cohort_customers
ORDER BY a.cohort_month, months_since_first;
