-- 10_kpi_monthly.sql
-- Monthly business KPIs. Definitions live in docs/metric_definitions.md.
--   gross_sales      merchandise sales before cancellations
--   net_revenue      gross_sales + cancellations (cancellations are negative)
--   aov              gross_sales / orders
--   new vs returning split uses the customer's first order month in the data window
--   (Dec-2009 "new" customers are left-censored: many were existing customers).
CREATE OR REPLACE VIEW kpi_monthly AS
WITH money AS (
    SELECT
        DATE_TRUNC('month', date_key)::DATE                          AS month,
        SUM(revenue) FILTER (WHERE line_type = 'sale')               AS gross_sales,
        SUM(revenue) FILTER (WHERE line_type = 'cancellation')       AS cancellations,
        SUM(revenue)                                                 AS net_revenue,
        SUM(quantity) FILTER (WHERE line_type = 'sale')              AS units
    FROM fct_order_lines
    GROUP BY 1
),
orders AS (
    SELECT
        DATE_TRUNC('month', o.date_key)::DATE                        AS month,
        COUNT(*)                                                     AS orders,
        COUNT(*) FILTER (WHERE o.is_guest)                           AS guest_orders,
        COUNT(DISTINCT o.customer_id)                                AS active_customers,
        COUNT(DISTINCT o.customer_id)
            FILTER (WHERE c.cohort_month = DATE_TRUNC('month', o.date_key))  AS new_customers,
        SUM(o.order_value)
            FILTER (WHERE c.cohort_month = DATE_TRUNC('month', o.date_key))  AS new_customer_sales,
        SUM(o.order_value)
            FILTER (WHERE c.cohort_month < DATE_TRUNC('month', o.date_key))  AS returning_customer_sales,
        SUM(o.order_value) FILTER (WHERE o.is_guest)                 AS guest_sales
    FROM fct_orders o
    LEFT JOIN dim_customer c USING (customer_id)
    GROUP BY 1
)
SELECT
    m.month,
    m.gross_sales,
    m.cancellations,
    m.net_revenue,
    m.units,
    o.orders,
    o.guest_orders,
    o.active_customers,
    o.new_customers,
    o.new_customer_sales,
    o.returning_customer_sales,
    o.guest_sales,
    m.gross_sales / o.orders                                         AS aov,
    -m.cancellations / m.gross_sales                                 AS cancellation_rate
FROM money m
JOIN orders o USING (month)
ORDER BY m.month;
