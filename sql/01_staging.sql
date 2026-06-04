-- 01_staging.sql
-- Land the cleaned, line-level Parquet file as the single staging table.
-- Every row carries a line_type (sale / cancellation / non_product / ...);
-- downstream models filter on it explicitly so the business rules stay visible.
CREATE OR REPLACE TABLE stg_transactions AS
SELECT
    invoice,
    invoice_date                         AS invoice_ts,
    CAST(invoice_day AS DATE)            AS invoice_date,
    customer_id,
    is_guest,
    country,
    stock_code,
    description,
    quantity,
    unit_price,
    revenue,
    line_type,
    was_cancelled,
    matched_cancellation
FROM read_parquet('{{clean_parquet}}');
