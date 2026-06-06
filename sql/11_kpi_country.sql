-- 11_kpi_country.sql
-- Country performance per trading year (Dec–Nov), with year-on-year growth.
CREATE OR REPLACE VIEW kpi_country AS
WITH base AS (
    SELECT
        d.trading_year,
        l.country,
        SUM(l.revenue)                                               AS net_revenue,
        COUNT(DISTINCT l.invoice) FILTER (WHERE l.line_type = 'sale') AS orders,
        COUNT(DISTINCT l.customer_id)                                AS customers,
        SUM(l.revenue) FILTER (WHERE l.line_type = 'sale')           AS gross_sales
    FROM fct_order_lines l
    JOIN dim_date d ON d.date_key = l.date_key
    WHERE d.trading_year IN (2010, 2011)                             -- complete trading years only
    GROUP BY ALL
)
SELECT
    *,
    gross_sales / NULLIF(orders, 0)                                  AS aov,
    net_revenue / LAG(net_revenue) OVER w - 1                        AS revenue_yoy,
    net_revenue / SUM(net_revenue) OVER (PARTITION BY trading_year)  AS revenue_share
FROM base
WINDOW w AS (PARTITION BY country ORDER BY trading_year)
ORDER BY trading_year, net_revenue DESC;
