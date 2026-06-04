-- 02_dim_date.sql
-- Calendar dimension covering the full data window. Retail reporting here uses a
-- "trading year" of December–November so the Christmas peak is never split.
CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT MIN(invoice_date) AS d0, MAX(invoice_date) AS d1 FROM stg_transactions
)
SELECT
    CAST(d.day AS DATE)                                  AS date_key,
    EXTRACT(year FROM d.day)                             AS calendar_year,
    EXTRACT(month FROM d.day)                            AS month_num,
    STRFTIME(d.day, '%b')                                AS month_name,
    DATE_TRUNC('month', d.day)::DATE                     AS month_start,
    DATE_TRUNC('week', d.day)::DATE                      AS week_start,   -- ISO weeks start Monday
    ISODOW(d.day)                                        AS iso_dow,      -- 1 = Monday
    STRFTIME(d.day, '%a')                                AS dow_name,
    ISODOW(d.day) IN (6, 7)                              AS is_weekend,
    -- Trading year: Dec 2009–Nov 2010 = TY2010, Dec 2010–Nov 2011 = TY2011
    CASE WHEN EXTRACT(month FROM d.day) = 12
         THEN EXTRACT(year FROM d.day) + 1
         ELSE EXTRACT(year FROM d.day) END               AS trading_year
FROM bounds, RANGE(bounds.d0, bounds.d1 + INTERVAL 1 DAY, INTERVAL 1 DAY) AS d(day);
