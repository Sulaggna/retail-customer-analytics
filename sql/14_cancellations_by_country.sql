-- 14_cancellations_by_country.sql
-- Where do cancellations concentrate? Rate = cancelled value / gross sales.
CREATE OR REPLACE VIEW cancellations_by_country AS
SELECT
    country,
    SUM(revenue) FILTER (WHERE line_type = 'sale')                   AS gross_sales,
    -SUM(revenue) FILTER (WHERE line_type = 'cancellation')          AS cancelled_value,
    COUNT(DISTINCT invoice) FILTER (WHERE line_type = 'cancellation') AS cancellation_invoices,
    -SUM(revenue) FILTER (WHERE line_type = 'cancellation')
        / SUM(revenue) FILTER (WHERE line_type = 'sale')             AS cancellation_rate
FROM fct_order_lines
GROUP BY country
HAVING SUM(revenue) FILTER (WHERE line_type = 'sale') > 50000
ORDER BY cancellation_rate DESC;
