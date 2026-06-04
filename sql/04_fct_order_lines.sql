-- 04_fct_order_lines.sql
-- Fact table at line grain: merchandise sales and their cancellations only.
-- Net revenue = SUM(revenue) over this table (cancellations carry negative revenue).
CREATE OR REPLACE TABLE fct_order_lines AS
SELECT
    t.invoice,
    t.invoice_ts,
    t.invoice_date                         AS date_key,
    t.customer_id,
    t.is_guest,
    t.country,
    t.stock_code,
    t.quantity,
    t.unit_price,
    t.revenue,
    t.line_type,
    t.was_cancelled
FROM stg_transactions t
WHERE t.line_type IN ('sale', 'cancellation');
