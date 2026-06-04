-- 03_dim_product.sql
-- One row per merchandise SKU (non-product codes such as POSTAGE are excluded).
CREATE OR REPLACE TABLE dim_product AS
SELECT
    stock_code,
    ANY_VALUE(description)                                       AS description,  -- already canonicalised upstream
    MEDIAN(unit_price)                                           AS median_unit_price,
    CASE
        WHEN MEDIAN(unit_price) < 1    THEN '1. < £1'
        WHEN MEDIAN(unit_price) < 3    THEN '2. £1–3'
        WHEN MEDIAN(unit_price) < 10   THEN '3. £3–10'
        ELSE                                '4. £10+'
    END                                                          AS price_band,
    MIN(invoice_date)                                            AS first_sold,
    MAX(invoice_date)                                            AS last_sold
FROM stg_transactions
WHERE line_type = 'sale'
GROUP BY stock_code;
