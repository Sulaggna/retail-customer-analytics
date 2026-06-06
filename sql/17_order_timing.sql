-- 17_order_timing.sql
-- When do orders arrive? Day-of-week x hour-of-day grid for staffing and
-- campaign scheduling.
CREATE OR REPLACE VIEW order_timing AS
SELECT
    ISODOW(order_ts)                     AS iso_dow,
    STRFTIME(order_ts, '%a')             AS dow_name,
    EXTRACT(hour FROM order_ts)          AS hour,
    COUNT(*)                             AS orders,
    SUM(order_value)                     AS sales
FROM fct_orders
GROUP BY ALL
ORDER BY iso_dow, hour;
