-- 12_product_performance.sql
-- SKU-level performance with a Pareto (cumulative revenue share) ranking and
-- cancellation rate. Window functions do the ranking in one pass.
CREATE OR REPLACE VIEW product_performance AS
WITH p AS (
    SELECT
        l.stock_code,
        d.description,
        d.price_band,
        SUM(l.revenue)                                                       AS net_revenue,
        SUM(l.quantity) FILTER (WHERE l.line_type = 'sale')                  AS units_sold,
        COALESCE(-SUM(l.quantity) FILTER (WHERE l.line_type = 'cancellation'), 0) AS units_cancelled,
        COUNT(DISTINCT l.invoice) FILTER (WHERE l.line_type = 'sale')        AS n_orders,
        COUNT(DISTINCT l.customer_id)                                        AS n_customers
    FROM fct_order_lines l
    JOIN dim_product d USING (stock_code)
    GROUP BY ALL
)
SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY net_revenue DESC)                            AS revenue_rank,
    SUM(net_revenue) OVER (ORDER BY net_revenue DESC
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / SUM(net_revenue) OVER ()                                           AS cum_revenue_share,
    ROW_NUMBER() OVER (ORDER BY net_revenue DESC) / COUNT(*) OVER ()         AS cum_sku_share,
    units_cancelled / NULLIF(units_sold, 0)                                  AS cancel_rate
FROM p
ORDER BY revenue_rank;
